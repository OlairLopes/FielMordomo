"""Dominio: pedidos_oracao."""
from data.repo_base import (
    _conn, _garantir_colunas_cadastros, _garantir_tabelas_pedidos_oracao, _read_sql_query_formatado,
    _tenant_db, inicializar_tenant, sanitizar
)


def registrar_pedido_oracao(
    slug,
    id_cadastro=None,
    pedido="",
    tipo_pedido="Pedido de oracao",
    confidencial=True,
    deseja_visita=False,
    id_slot=None,
    congregacao="",
    nome_manual="",
    telefone_manual="",
    motivo_oracao="",
    privacidade="Pastor",
):
    pedido = sanitizar(pedido)
    tipo_pedido = sanitizar(tipo_pedido or "Pedido de oracao")
    congregacao = sanitizar(congregacao)
    nome_manual = sanitizar(nome_manual)
    telefone_manual = sanitizar(telefone_manual)
    motivo_oracao = sanitizar(motivo_oracao)
    privacidade = sanitizar(privacidade or "Pastor")
    if not pedido or len(pedido) < 10:
        raise ValueError("Descreva o pedido de oracao com um pouco mais de detalhe.")
    if tipo_pedido not in {
        "Pedido de oracao",
        "Agradecimento",
        "Aconselhamento",
        "Visita pastoral",
        "Solicitacao de visita pastoral",
        "Solicitacao de atendimento no gabinete",
    }:
        raise ValueError("Tipo de pedido invalido.")
    if privacidade not in {"Pastor", "Lideres", "Toda Igreja"}:
        raise ValueError("Privacidade invalida.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_colunas_cadastros(conn)
        _garantir_tabelas_pedidos_oracao(conn)
        membro = None
        id_cadastro_final = int(id_cadastro) if id_cadastro else None
        if id_cadastro_final:
            membro = conn.execute(
                """SELECT id_cadastro, nome, telefone, congregacao
                   FROM cadastros
                   WHERE id_cadastro=? AND UPPER(TRIM(tipo_cadastro))='MEMBRO'
                         AND UPPER(TRIM(situacao))='ATIVO'
                   LIMIT 1""",
                (id_cadastro_final,),
            ).fetchone()
            if not membro:
                raise ValueError("Cadastro de membro ativo nao localizado.")
            nome_final = sanitizar(membro["nome"])
            telefone_final = sanitizar(membro["telefone"])
            congregacao_final = congregacao or sanitizar(membro["congregacao"])
        else:
            if not nome_manual:
                raise ValueError("Informe o nome do membro.")
            nome_final = nome_manual
            telefone_final = telefone_manual
            congregacao_final = congregacao

        slot_id = int(id_slot) if id_slot else None
        if deseja_visita and slot_id:
            slot = conn.execute(
                """SELECT id_slot FROM agenda_pastoral
                   WHERE id_slot=? AND disponivel=1 AND id_pedido IS NULL
                   LIMIT 1""",
                (slot_id,),
            ).fetchone()
            if not slot:
                raise ValueError("Horario pastoral indisponivel. Escolha outro horario.")
        elif deseja_visita:
            slot_id = None

        cur = conn.execute(
            """INSERT INTO pedidos_oracao
               (id_cadastro, congregacao, nome_membro, telefone, tipo_pedido,
                motivo_oracao, pedido, privacidade, confidencial, deseja_visita,
                id_slot, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Novo')""",
            (
                id_cadastro_final,
                congregacao_final,
                nome_final,
                telefone_final,
                tipo_pedido,
                motivo_oracao,
                pedido,
                privacidade,
                int(bool(confidencial)),
                int(bool(deseja_visita)),
                slot_id,
            ),
        )
        id_pedido = cur.lastrowid
        if slot_id:
            conn.execute(
                """UPDATE agenda_pastoral
                   SET id_pedido=?, disponivel=0, atualizado_em=datetime('now')
                   WHERE id_slot=?""",
                (id_pedido, slot_id),
            )
        return id_pedido


def listar_pedidos_oracao(slug, data_inicio=None, data_fim=None, status=""):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_pedidos_oracao(conn)
        where = []
        params = []
        if data_inicio:
            where.append("date(p.criado_em)>=date(?)")
            params.append(str(data_inicio))
        if data_fim:
            where.append("date(p.criado_em)<=date(?)")
            params.append(str(data_fim))
        if status:
            where.append("p.status=?")
            params.append(str(status))
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT p.id_pedido, p.id_cadastro, p.congregacao, p.nome_membro,
                       p.telefone, p.tipo_pedido, p.motivo_oracao, p.pedido,
                       p.privacidade, p.confidencial, p.deseja_visita,
                       p.id_slot, p.status, p.notificacao_status, p.criado_em,
                       a.data AS data_visita, a.hora_inicio, a.hora_fim, a.local
                FROM pedidos_oracao p
                LEFT JOIN agenda_pastoral a ON a.id_slot=p.id_slot
                {filtro}
                ORDER BY p.criado_em DESC""",
            conn,
            params=params,
        )


def atualizar_status_pedido_oracao(slug, id_pedido, status):
    status = str(status or "").strip()
    if status not in {"Novo", "Em acompanhamento", "Orado", "Visitado", "Arquivado"}:
        raise ValueError("Status de pedido invalido.")
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_pedidos_oracao(conn)
        conn.execute(
            """UPDATE pedidos_oracao
               SET status=?, atualizado_em=datetime('now')
               WHERE id_pedido=?""",
            (status, int(id_pedido)),
        )


def atualizar_notificacao_pedido_oracao(slug, id_pedido, notificacao_status):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_pedidos_oracao(conn)
        conn.execute(
            """UPDATE pedidos_oracao
               SET notificacao_status=?, atualizado_em=datetime('now')
               WHERE id_pedido=?""",
            (sanitizar(notificacao_status), int(id_pedido)),
        )
