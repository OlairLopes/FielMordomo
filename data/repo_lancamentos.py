"""Dominio: lancamentos."""
import datetime
from data.repo_base import (
    _conn, _dados_lancamento_validados, _fazer_backup, _garantir_colunas_lancamentos,
    _garantir_tabela_leitores_biblia, _garantir_tabelas_ebd, _normalizar_telefone_leitor,
    _tenant_db, inicializar_tenant, sanitizar
)


def excluir_ebd_escala_lote(slug, ids_escala):
    ids = [int(i) for i in ids_escala]
    if not ids:
        return
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"DELETE FROM ebd_escala_professores WHERE id_escala IN ({placeholders})",
            ids,
        )


def inserir_lancamentos_lote(slug, lancamentos, lote_id=None):
    lancamentos = list(lancamentos)
    if not lancamentos:
        raise ValueError("O lote deve possuir ao menos um lancamento.")
    lote_id = str(lote_id or f"LOTE-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}")
    db = _tenant_db(slug)
    ids = []
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_colunas_lancamentos(conn)
        dados_lote = [_dados_lancamento_validados(conn, l, lote_id) for l in lancamentos]
        for dados in dados_lote:
            cur = conn.execute(
                """INSERT INTO lancamentos
                   (data, tipo, categoria, subcategoria, id_cadastro, nome_cadastro, tipo_cadastro,
                    descricao, forma_pagamento, lote_id, valor)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                dados,
            )
            ids.append(cur.lastrowid)
    return lote_id, ids


def atualizar_lancamento(slug, l):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_colunas_lancamentos(conn)
        row = conn.execute(
            "SELECT lote_id FROM lancamentos WHERE id_lancamento=?", (l.id_lancamento,)
        ).fetchone()
        if not row:
            raise ValueError("Lancamento nao encontrado.")
        dados = _dados_lancamento_validados(conn, l, row["lote_id"] or "")
        conn.execute(
            """UPDATE lancamentos SET data=?, tipo=?, categoria=?, subcategoria=?, id_cadastro=?,
               nome_cadastro=?, tipo_cadastro=?, descricao=?, forma_pagamento=?, lote_id=?, valor=?
               WHERE id_lancamento=?""",
            dados + (l.id_lancamento,),
        )


def excluir_lancamento(slug, id_lancamento):
    _fazer_backup(_tenant_db(slug))
    db = _tenant_db(slug)
    with _conn(db) as conn:
        conn.execute("DELETE FROM lancamentos WHERE id_lancamento=?", (id_lancamento,))


def importar_leitores_biblia_em_lote(slug, entradas):
    """Cria leitores avulsos em lote a partir de {"nome":..., "telefone":...}
    (ex.: lista extraida de um grupo do WhatsApp). Sem CPF/data de nascimento:
    esses leitores confirmam a leitura diaria informando o telefone.
    Retorna {"importados": int, "duplicados": [nomes], "invalidos": [nomes]}."""
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    importados = 0
    duplicados = []
    invalidos = []
    with _conn(db) as conn:
        _garantir_tabela_leitores_biblia(conn)
        existentes = {
            row[0] for row in conn.execute(
                "SELECT telefone FROM leitores_biblia WHERE telefone != ''"
            ).fetchall()
        }
        for item in entradas:
            nome = sanitizar(item.get("nome", ""))
            telefone = _normalizar_telefone_leitor(item.get("telefone", ""))
            if not nome or not telefone:
                invalidos.append(item.get("nome") or item.get("telefone") or "(linha vazia)")
                continue
            if telefone in existentes:
                duplicados.append(nome)
                continue
            conn.execute(
                """INSERT INTO leitores_biblia (nome, cpf, data_nascimento, telefone)
                   VALUES (?, NULL, NULL, ?)""",
                (nome, telefone),
            )
            existentes.add(telefone)
            importados += 1
    return {"importados": importados, "duplicados": duplicados, "invalidos": invalidos}
