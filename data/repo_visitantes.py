"""Dominio: visitantes."""
from data.repo_base import (
    _conn, _garantir_tabelas_visitantes, _read_sql_query_formatado, _tenant_db, inicializar_tenant,
    sanitizar
)


def salvar_visitante_culto(
    slug,
    data,
    departamento,
    nome_visitante,
    tipo_visitante,
    igreja_origem="",
    cidade="",
    estado="",
    denominacao="",
    deseja_ser_apresentado=False,
    deseja_oracao_final=False,
    observacoes="",
    congregacao="",
    id_visitante=None,
):
    tipo_visitante = str(tipo_visitante or "").strip()
    nome_visitante = sanitizar(nome_visitante)
    departamento = sanitizar(departamento)
    if not str(data or "").strip():
        raise ValueError("Informe a data do culto.")
    if not departamento:
        raise ValueError("Informe o departamento.")
    if not nome_visitante:
        raise ValueError("Informe o nome do visitante.")
    if tipo_visitante not in {"Crente", "Nao crente"}:
        raise ValueError("Tipo de visitante invalido.")
    if tipo_visitante == "Crente":
        if not str(igreja_origem or "").strip():
            raise ValueError("Informe de qual igreja o visitante crente veio.")
        if not str(cidade or "").strip():
            raise ValueError("Informe a cidade da igreja de origem.")
        if not str(estado or "").strip():
            raise ValueError("Informe o estado da igreja de origem.")
        denominacao = ""
    else:
        if not str(denominacao or "").strip():
            raise ValueError("Informe a denominacao ou contexto religioso do visitante.")
        igreja_origem = ""
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_visitantes(conn)
        dados = (
            str(data),
            departamento,
            nome_visitante,
            tipo_visitante,
            sanitizar(igreja_origem),
            sanitizar(cidade),
            sanitizar(estado),
            sanitizar(congregacao),
            sanitizar(denominacao),
            int(bool(deseja_ser_apresentado)),
            int(bool(deseja_oracao_final)),
            sanitizar(observacoes),
        )
        if id_visitante:
            conn.execute(
                """UPDATE visitantes_cultos
                   SET data=?, departamento=?, nome_visitante=?, tipo_visitante=?,
                       igreja_origem=?, cidade=?, estado=?, congregacao=?, denominacao=?,
                       deseja_ser_apresentado=?, deseja_oracao_final=?,
                       observacoes=?, atualizado_em=datetime('now')
                   WHERE id_visitante=?""",
                dados + (int(id_visitante),),
            )
            return int(id_visitante)
        cur = conn.execute(
            """INSERT INTO visitantes_cultos
               (data, departamento, nome_visitante, tipo_visitante,
                igreja_origem, cidade, estado, congregacao, denominacao,
                deseja_ser_apresentado, deseja_oracao_final, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            dados,
        )
        return cur.lastrowid


def listar_visitantes_cultos(slug, data_inicio=None, data_fim=None, departamento=""):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_visitantes(conn)
        where = []
        params = []
        if data_inicio:
            where.append("data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("data<=?")
            params.append(str(data_fim))
        if str(departamento or "").strip():
            where.append("departamento=?")
            params.append(str(departamento).strip())
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT id_visitante, data, departamento, nome_visitante,
                       tipo_visitante, igreja_origem, cidade, estado,
                       congregacao, denominacao, deseja_ser_apresentado,
                       deseja_oracao_final, observacoes, criado_em, atualizado_em
                FROM visitantes_cultos
                {filtro}
                ORDER BY data DESC, id_visitante DESC""",
            conn,
            params=params,
        )


def excluir_visitante_culto(slug, id_visitante):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_visitantes(conn)
        conn.execute(
            "DELETE FROM visitantes_cultos WHERE id_visitante=?",
            (int(id_visitante),),
        )
        return True
