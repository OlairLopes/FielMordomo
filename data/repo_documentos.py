"""Dominio: documentos."""
import datetime
from data.repo_base import (
    TIPOS_DOCUMENTO_MEMBRO, _conn, _garantir_tabela_documentos_emitidos, _tenant_db,
    inicializar_tenant, sanitizar
)


def registrar_documento_emitido(slug, codigo, tipo, id_cadastro, nome_titular, descricao):
    if tipo not in TIPOS_DOCUMENTO_MEMBRO:
        raise ValueError("Tipo de documento invalido.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_documentos_emitidos(conn)
        conn.execute(
            """INSERT INTO documentos_emitidos
               (codigo, tipo, id_cadastro, nome_titular, descricao, emitido_em)
               VALUES (?,?,?,?,?,?)""",
            (codigo, tipo, id_cadastro, sanitizar(nome_titular)[:120], sanitizar(descricao)[:200],
             datetime.datetime.now().isoformat(timespec="seconds")),
        )


def buscar_documento_emitido(slug, codigo):
    db = _tenant_db(slug)
    if not db.exists():
        return None
    with _conn(db) as conn:
        _garantir_tabela_documentos_emitidos(conn)
        row = conn.execute(
            "SELECT * FROM documentos_emitidos WHERE codigo=?", (codigo,)
        ).fetchone()
    return dict(row) if row else None


def listar_documentos_emitidos(slug, id_cadastro=None):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_documentos_emitidos(conn)
        if id_cadastro:
            rows = conn.execute(
                "SELECT * FROM documentos_emitidos WHERE id_cadastro=? ORDER BY emitido_em DESC",
                (id_cadastro,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM documentos_emitidos ORDER BY emitido_em DESC LIMIT 200"
            ).fetchall()
    return [dict(r) for r in rows]
