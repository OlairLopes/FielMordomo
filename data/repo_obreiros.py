"""Dominio: obreiros."""
import pandas as pd
from data.repo_base import (
    _conn, _garantir_colunas_cadastros, _garantir_tabelas_obreiros, _read_sql_query_formatado,
    _tenant_db, inicializar_tenant, sanitizar
)


def listar_funcoes_obreiros(slug):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_colunas_cadastros(conn)
        rows = conn.execute(
            """SELECT DISTINCT TRIM(funcao) AS funcao
               FROM cadastros
               WHERE UPPER(TRIM(tipo_cadastro))='MEMBRO'
                     AND UPPER(TRIM(situacao))='ATIVO'
                     AND TRIM(COALESCE(funcao, ''))!=''
               ORDER BY funcao"""
        ).fetchall()
    return [row["funcao"] for row in rows if str(row["funcao"] or "").strip()]


def listar_obreiros_por_funcoes(slug, funcoes):
    funcoes = [sanitizar(f) for f in (funcoes or []) if str(f or "").strip()]
    if not funcoes:
        return pd.DataFrame(columns=["id_cadastro", "nome", "funcao", "telefone", "congregacao"])
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_colunas_cadastros(conn)
        placeholders = ",".join("?" for _ in funcoes)
        return _read_sql_query_formatado(
            f"""SELECT id_cadastro, nome, funcao, telefone, congregacao
                FROM cadastros
                WHERE UPPER(TRIM(tipo_cadastro))='MEMBRO'
                      AND UPPER(TRIM(situacao))='ATIVO'
                      AND TRIM(funcao) IN ({placeholders})
                ORDER BY funcao, nome""",
            conn,
            params=funcoes,
        )


def listar_obreiros_reunioes(slug, data_inicio=None, data_fim=None):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_obreiros(conn)
        where = []
        params = []
        if data_inicio:
            where.append("data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("data<=?")
            params.append(str(data_fim))
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT id_reuniao, data, tema, funcoes,
                       qtd_matriculados AS matriculados,
                       qtd_presentes AS presentes,
                       qtd_ausentes AS ausentes,
                       qtd_visitantes AS visitantes,
                       ofertas, observacoes, ata_nome,
                       CASE WHEN ata_bytes IS NULL THEN 0 ELSE 1 END AS tem_ata,
                       ata_enviada_em, criado_em, atualizado_em
                FROM obreiros_reunioes
                {filtro}
                ORDER BY data DESC""",
            conn,
            params=params,
        )


def carregar_obreiros_presencas(slug, id_reuniao):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_obreiros(conn)
        return _read_sql_query_formatado(
            """SELECT id_presenca, id_reuniao, id_cadastro, nome, funcao,
                      presente, observacao
               FROM obreiros_presencas
               WHERE id_reuniao=?
               ORDER BY funcao, nome""",
            conn,
            params=[int(id_reuniao)],
        )


def obter_obreiros_ata(slug, id_reuniao):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_obreiros(conn)
        row = conn.execute(
            """SELECT id_reuniao, data, ata_nome, ata_mime, ata_bytes
               FROM obreiros_reunioes
               WHERE id_reuniao=?""",
            (int(id_reuniao),),
        ).fetchone()
        if not row or row["ata_bytes"] is None:
            return None
        return {
            "id_reuniao": row["id_reuniao"],
            "data": row["data"],
            "nome": row["ata_nome"] or f"ata-reuniao-obreiros-{row['data']}.pdf",
            "mime": row["ata_mime"] or "application/octet-stream",
            "bytes": row["ata_bytes"],
        }


def salvar_obreiros_chamada(
    slug,
    data,
    tema="",
    funcoes=None,
    presencas=None,
    visitantes=0,
    ofertas=0.0,
    observacoes="",
    ata_nome="",
    ata_mime="",
    ata_bytes=None,
    id_reuniao=None,
):
    funcoes = [sanitizar(f) for f in (funcoes or []) if str(f or "").strip()]
    presencas = presencas or {}
    data = str(data or "").strip()
    if not data:
        raise ValueError("Informe a data da reuniao.")
    if not funcoes:
        raise ValueError("Selecione ao menos uma funcao para gerar a chamada.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_colunas_cadastros(conn)
        _garantir_tabelas_obreiros(conn)
        placeholders = ",".join("?" for _ in funcoes)
        membros = conn.execute(
            f"""SELECT id_cadastro, nome, funcao
                FROM cadastros
                WHERE UPPER(TRIM(tipo_cadastro))='MEMBRO'
                      AND UPPER(TRIM(situacao))='ATIVO'
                      AND TRIM(funcao) IN ({placeholders})
                ORDER BY funcao, nome""",
            funcoes,
        ).fetchall()
        if not membros:
            raise ValueError("Nenhum membro ativo encontrado para as funcoes selecionadas.")

        total = len(membros)
        presentes = sum(1 for row in membros if bool(presencas.get(int(row["id_cadastro"]))))
        ausentes = total - presentes
        visitantes = max(int(visitantes or 0), 0)
        ofertas = max(float(ofertas or 0), 0.0)
        funcoes_txt = "; ".join(funcoes)
        tem_ata = ata_bytes is not None
        if id_reuniao:
            id_reuniao = int(id_reuniao)
            conflito = conn.execute(
                "SELECT 1 FROM obreiros_reunioes WHERE data=? AND id_reuniao<>? LIMIT 1",
                (data, id_reuniao),
            ).fetchone()
            if conflito:
                raise ValueError("Ja existe uma reuniao de obreiros nesta data.")
            conn.execute(
                """UPDATE obreiros_reunioes
                   SET data=?, tema=?, funcoes=?, qtd_matriculados=?,
                       qtd_presentes=?, qtd_ausentes=?, qtd_visitantes=?,
                       ofertas=?, observacoes=?,
                       ata_nome=CASE WHEN ? IS NULL THEN ata_nome ELSE ? END,
                       ata_mime=CASE WHEN ? IS NULL THEN ata_mime ELSE ? END,
                       ata_bytes=CASE WHEN ? IS NULL THEN ata_bytes ELSE ? END,
                       ata_enviada_em=CASE WHEN ? IS NULL THEN ata_enviada_em ELSE datetime('now') END,
                       atualizado_em=datetime('now')
                   WHERE id_reuniao=?""",
                (
                    data, sanitizar(tema), funcoes_txt, total, presentes,
                    ausentes, visitantes, ofertas, sanitizar(observacoes),
                    ata_bytes, sanitizar(ata_nome),
                    ata_bytes, sanitizar(ata_mime),
                    ata_bytes, ata_bytes,
                    ata_bytes, id_reuniao,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO obreiros_reunioes
                   (data, tema, funcoes, qtd_matriculados, qtd_presentes,
                    qtd_ausentes, qtd_visitantes, ofertas, observacoes,
                    ata_nome, ata_mime, ata_bytes, ata_enviada_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? THEN datetime('now') ELSE '' END)
                   ON CONFLICT(data) DO UPDATE SET
                       tema=excluded.tema,
                       funcoes=excluded.funcoes,
                       qtd_matriculados=excluded.qtd_matriculados,
                       qtd_presentes=excluded.qtd_presentes,
                       qtd_ausentes=excluded.qtd_ausentes,
                       qtd_visitantes=excluded.qtd_visitantes,
                       ofertas=excluded.ofertas,
                       observacoes=excluded.observacoes,
                       ata_nome=CASE WHEN excluded.ata_bytes IS NULL THEN ata_nome ELSE excluded.ata_nome END,
                       ata_mime=CASE WHEN excluded.ata_bytes IS NULL THEN ata_mime ELSE excluded.ata_mime END,
                       ata_bytes=CASE WHEN excluded.ata_bytes IS NULL THEN ata_bytes ELSE excluded.ata_bytes END,
                       ata_enviada_em=CASE WHEN excluded.ata_bytes IS NULL THEN ata_enviada_em ELSE datetime('now') END,
                       atualizado_em=datetime('now')""",
                (
                    data, sanitizar(tema), funcoes_txt, total, presentes,
                    ausentes, visitantes, ofertas, sanitizar(observacoes),
                    sanitizar(ata_nome), sanitizar(ata_mime), ata_bytes, int(tem_ata),
                ),
            )
            id_reuniao = conn.execute(
                "SELECT id_reuniao FROM obreiros_reunioes WHERE data=?", (data,)
            ).fetchone()["id_reuniao"]
        conn.execute("DELETE FROM obreiros_presencas WHERE id_reuniao=?", (id_reuniao,))
        for row in membros:
            conn.execute(
                """INSERT INTO obreiros_presencas
                   (id_reuniao, id_cadastro, nome, funcao, presente)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    id_reuniao,
                    int(row["id_cadastro"]),
                    sanitizar(row["nome"]),
                    sanitizar(row["funcao"]),
                    int(bool(presencas.get(int(row["id_cadastro"])))),
                ),
            )
        return id_reuniao


def relatorio_obreiros_frequencia(slug, data_inicio=None, data_fim=None, funcao=""):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_obreiros(conn)
        where = []
        params = []
        if data_inicio:
            where.append("r.data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("r.data<=?")
            params.append(str(data_fim))
        if str(funcao or "").strip():
            where.append("p.funcao=?")
            params.append(str(funcao).strip())
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        df = _read_sql_query_formatado(
            f"""SELECT p.id_cadastro, p.nome, p.funcao,
                       SUM(CASE WHEN p.presente=1 THEN 1 ELSE 0 END) AS presencas,
                       SUM(CASE WHEN p.presente=0 THEN 1 ELSE 0 END) AS ausencias,
                       COUNT(*) AS reunioes
                FROM obreiros_presencas p
                JOIN obreiros_reunioes r ON r.id_reuniao=p.id_reuniao
                {filtro}
                GROUP BY p.id_cadastro, p.nome, p.funcao
                ORDER BY p.funcao, p.nome""",
            conn,
            params=params,
        )
    if df.empty:
        return df
    total = df["presencas"] + df["ausencias"]
    df["frequencia_pct"] = (df["presencas"] / total.where(total > 0, 1) * 100).round(1)
    return df
