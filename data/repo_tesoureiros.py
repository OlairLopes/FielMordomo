"""Dominio: tesoureiros."""
from data.repo_base import (
    _autenticacao_bloqueada, _conn, _garantir_tabela_tesoureiros, _normalizar_usuario_tesoureiro,
    _read_sql_query_formatado, _registrar_resultado_login, _tenant_db, _validar_slug,
    _validar_tesoureiro, _verificar_senha, buscar_igreja_por_slug, hash_senha, inicializar_tenant,
    sanitizar, validar_nova_senha
)


def carregar_tesoureiros(slug):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_tesoureiros(conn)
        return _read_sql_query_formatado(
            """SELECT * FROM tesoureiros
               ORDER BY CASE WHEN situacao='Ativo' THEN 0 ELSE 1 END,
                        principal DESC, nome""",
            conn,
        )


def cpf_tesoureiro_existe(slug, cpf, id_excluir=None):
    cpf_limpo = "".join(c for c in str(cpf or "") if c.isdigit())
    if not cpf_limpo:
        return False
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabela_tesoureiros(conn)
        if id_excluir:
            row = conn.execute(
                "SELECT 1 FROM tesoureiros WHERE cpf=? AND id_tesoureiro!=? LIMIT 1",
                (cpf_limpo, int(id_excluir)),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM tesoureiros WHERE cpf=? LIMIT 1", (cpf_limpo,)
            ).fetchone()
    return row is not None


def inserir_tesoureiro(slug, tesoureiro):
    _validar_tesoureiro(tesoureiro)
    erros_senha = validar_nova_senha(tesoureiro.senha)
    if erros_senha:
        raise ValueError(" ".join(erros_senha))
    db = _tenant_db(slug)
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_tabela_tesoureiros(conn)
        duplicado = conn.execute(
            "SELECT 1 FROM tesoureiros WHERE cpf=? LIMIT 1",
            ("".join(c for c in str(tesoureiro.cpf or "") if c.isdigit()),),
        ).fetchone()
        if duplicado:
            raise ValueError("Ja existe um tesoureiro cadastrado com este CPF.")
        usuario = _normalizar_usuario_tesoureiro(tesoureiro.usuario)
        if conn.execute(
            "SELECT 1 FROM tesoureiros WHERE usuario=? LIMIT 1", (usuario,)
        ).fetchone():
            raise ValueError("Ja existe um tesoureiro com este usuario.")
        if tesoureiro.principal:
            conn.execute(
                "UPDATE tesoureiros SET principal=0, atualizado_em=datetime('now') "
                "WHERE principal=1"
            )
        cur = conn.execute(
            """INSERT INTO tesoureiros
               (nome, cpf, usuario, senha_hash, telefone, email, data_inicio,
                data_fim, situacao, principal, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            _dados_tesoureiro(tesoureiro, incluir_credenciais=True),
        )
        return cur.lastrowid


def atualizar_tesoureiro(slug, tesoureiro):
    _validar_tesoureiro(tesoureiro)
    if not tesoureiro.id_tesoureiro:
        raise ValueError("Tesoureiro nao informado.")
    db = _tenant_db(slug)
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_tabela_tesoureiros(conn)
        existe = conn.execute(
            "SELECT 1 FROM tesoureiros WHERE id_tesoureiro=?",
            (int(tesoureiro.id_tesoureiro),),
        ).fetchone()
        if not existe:
            raise ValueError("Tesoureiro nao encontrado.")
        duplicado = conn.execute(
            """SELECT 1 FROM tesoureiros
               WHERE cpf=? AND id_tesoureiro!=? LIMIT 1""",
            (
                "".join(c for c in str(tesoureiro.cpf or "") if c.isdigit()),
                int(tesoureiro.id_tesoureiro),
            ),
        ).fetchone()
        if duplicado:
            raise ValueError("Ja existe um tesoureiro cadastrado com este CPF.")
        usuario = _normalizar_usuario_tesoureiro(tesoureiro.usuario)
        if conn.execute(
            """SELECT 1 FROM tesoureiros
               WHERE usuario=? AND id_tesoureiro!=? LIMIT 1""",
            (usuario, int(tesoureiro.id_tesoureiro)),
        ).fetchone():
            raise ValueError("Ja existe um tesoureiro com este usuario.")
        if tesoureiro.principal:
            conn.execute(
                """UPDATE tesoureiros SET principal=0, atualizado_em=datetime('now')
                   WHERE principal=1 AND id_tesoureiro!=?""",
                (int(tesoureiro.id_tesoureiro),),
            )
        dados = _dados_tesoureiro(tesoureiro)
        if tesoureiro.senha:
            erros_senha = validar_nova_senha(tesoureiro.senha)
            if erros_senha:
                raise ValueError(" ".join(erros_senha))
            conn.execute(
                """UPDATE tesoureiros
                   SET nome=?, cpf=?, usuario=?, telefone=?, email=?, data_inicio=?,
                       data_fim=?, situacao=?, principal=?, observacoes=?,
                       senha_hash=?, atualizado_em=datetime('now')
                   WHERE id_tesoureiro=?""",
                dados + (hash_senha(tesoureiro.senha), int(tesoureiro.id_tesoureiro)),
            )
        else:
            conn.execute(
                """UPDATE tesoureiros
                   SET nome=?, cpf=?, usuario=?, telefone=?, email=?, data_inicio=?,
                       data_fim=?, situacao=?, principal=?, observacoes=?,
                       atualizado_em=datetime('now')
                   WHERE id_tesoureiro=?""",
                dados + (int(tesoureiro.id_tesoureiro),),
            )


def _dados_tesoureiro(tesoureiro, incluir_credenciais=False):
    cpf_limpo = "".join(c for c in str(tesoureiro.cpf or "") if c.isdigit())
    dados = (
        sanitizar(tesoureiro.nome),
        cpf_limpo,
        _normalizar_usuario_tesoureiro(tesoureiro.usuario),
        sanitizar(tesoureiro.telefone),
        sanitizar(tesoureiro.email),
        str(tesoureiro.data_inicio or ""),
        str(tesoureiro.data_fim or ""),
        tesoureiro.situacao,
        int(bool(tesoureiro.principal)),
        sanitizar(tesoureiro.observacoes),
    )
    if incluir_credenciais:
        return dados[:3] + (hash_senha(tesoureiro.senha),) + dados[3:]
    return dados


def autenticar_tesoureiro(slug, usuario, senha):
    try:
        slug = _validar_slug(slug)
        usuario = _normalizar_usuario_tesoureiro(usuario)
    except ValueError:
        return None
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    chave = f"tesoureiro:{usuario}"
    with _conn(db) as conn:
        _garantir_tabela_tesoureiros(conn)
        if _autenticacao_bloqueada(conn, chave):
            return None
        row = conn.execute(
            """SELECT id_tesoureiro, nome, usuario, senha_hash
               FROM tesoureiros
               WHERE usuario=? AND situacao='Ativo'""",
            (usuario,),
        ).fetchone()
        valido, migrar = _verificar_senha(senha, row["senha_hash"] if row else "")
        _registrar_resultado_login(conn, chave, valido)
        if valido and migrar:
            conn.execute(
                "UPDATE tesoureiros SET senha_hash=? WHERE id_tesoureiro=?",
                (hash_senha(senha), row["id_tesoureiro"]),
            )
    if not row or not valido:
        return None
    igreja_publica = {
        chave: igreja[chave]
        for chave in ("id", "nome", "slug", "email_admin", "plano", "ativa", "criada_em")
    }
    return {
        "igreja": igreja_publica,
        "tesoureiro": {
            "id": row["id_tesoureiro"],
            "nome": row["nome"],
            "usuario": row["usuario"],
        },
    }
