"""Dominio: equipe."""
import sqlite3
from data import repo_base as _base
from data.repo_base import (
    CHAVE_SENHA_PASTORAL, _autenticacao_bloqueada, _conn, _garantir_colunas_cadastros,
    _garantir_tabela_config_igreja, _garantir_tabela_pastores_auxiliares, _garantir_tabela_recepcao,
    _garantir_tabela_secretarios_gerais, _garantir_tabelas_pedidos_oracao,
    _normalizar_usuario_login_secretario_geral, _normalizar_usuario_pastor_auxiliar,
    _normalizar_usuario_recepcao, _normalizar_usuario_secretario_geral, _read_sql_query_formatado,
    _registrar_resultado_login, _sincronizar_recepcao_automatica_conn, _tenant_db,
    _validar_pin_recepcao, _validar_senha_pastor_auxiliar, _validar_senha_secretario_geral,
    _validar_slug, _verificar_senha, autenticar_igreja, buscar_igreja_por_slug, hash_senha,
    inicializar_tenant, obter_config_igreja, salvar_config_igreja, sanitizar, validar_nova_senha
)


def salvar_horario_visita_pastoral(
    slug,
    data,
    hora_inicio,
    hora_fim,
    local="",
    observacoes="",
    disponivel=True,
    id_slot=None,
):
    data = str(data or "").strip()
    hora_inicio = str(hora_inicio or "").strip()
    hora_fim = str(hora_fim or "").strip()
    if not data:
        raise ValueError("Informe a data do horario pastoral.")
    if not hora_inicio or not hora_fim:
        raise ValueError("Informe o horario inicial e final.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_pedidos_oracao(conn)
        dados = (
            data,
            hora_inicio,
            hora_fim,
            sanitizar(local),
            sanitizar(observacoes),
            int(bool(disponivel)),
        )
        if id_slot:
            conn.execute(
                """UPDATE agenda_pastoral
                   SET data=?, hora_inicio=?, hora_fim=?, local=?, observacoes=?,
                       disponivel=?, atualizado_em=datetime('now')
                   WHERE id_slot=?""",
                dados + (int(id_slot),),
            )
            return int(id_slot)
        cur = conn.execute(
            """INSERT INTO agenda_pastoral
               (data, hora_inicio, hora_fim, local, observacoes, disponivel)
               VALUES (?, ?, ?, ?, ?, ?)""",
            dados,
        )
        return cur.lastrowid


def listar_horarios_visita_pastoral(
    slug,
    data_inicio=None,
    data_fim=None,
    somente_disponiveis=False,
):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_pedidos_oracao(conn)
        where = []
        params = []
        if data_inicio:
            where.append("a.data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("a.data<=?")
            params.append(str(data_fim))
        if somente_disponiveis:
            where.append("a.disponivel=1 AND a.id_pedido IS NULL")
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT a.id_slot, a.data, a.hora_inicio, a.hora_fim, a.local,
                       a.observacoes, a.disponivel, a.id_pedido,
                       p.nome_membro AS membro_agendado, p.status AS status_pedido
                FROM agenda_pastoral a
                LEFT JOIN pedidos_oracao p ON p.id_pedido=a.id_pedido
                {filtro}
                ORDER BY a.data, a.hora_inicio""",
            conn,
            params=params,
        )


def excluir_horario_visita_pastoral(slug, id_slot):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_pedidos_oracao(conn)
        em_uso = conn.execute(
            "SELECT id_pedido FROM agenda_pastoral WHERE id_slot=? AND id_pedido IS NOT NULL",
            (int(id_slot),),
        ).fetchone()
        if em_uso:
            conn.execute(
                """UPDATE agenda_pastoral
                   SET disponivel=0, atualizado_em=datetime('now')
                   WHERE id_slot=?""",
                (int(id_slot),),
            )
            return False
        conn.execute("DELETE FROM agenda_pastoral WHERE id_slot=?", (int(id_slot),))
        return True


def listar_pastores_auxiliares(slug, incluir_inativos=True):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_pastores_auxiliares(conn)
        where = "" if incluir_inativos else "WHERE situacao='Ativo'"
        return _read_sql_query_formatado(
            f"""SELECT id_pastor_auxiliar, id_cadastro, nome, usuario,
                       telefone, email, situacao, observacoes, criado_em, atualizado_em
                FROM pastores_auxiliares
                {where}
                ORDER BY situacao, nome""",
            conn,
        )


def salvar_pastor_auxiliar(
    slug,
    nome,
    usuario,
    senha="",
    id_cadastro=None,
    telefone="",
    email="",
    situacao="Ativo",
    observacoes="",
    id_pastor_auxiliar=None,
):
    nome = sanitizar(nome)
    usuario = _normalizar_usuario_pastor_auxiliar(usuario)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    situacao = str(situacao or "Ativo").strip()
    if situacao not in {"Ativo", "Inativo"}:
        raise ValueError("Situacao invalida.")
    if not id_pastor_auxiliar:
        senha = _validar_senha_pastor_auxiliar(senha)
    elif senha:
        senha = _validar_senha_pastor_auxiliar(senha)

    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_pastores_auxiliares(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
        if not nome:
            raise ValueError("Nome do Pastor Auxiliar e obrigatorio.")
        duplicado = conn.execute(
            """SELECT 1 FROM pastores_auxiliares
               WHERE usuario=? AND (? IS NULL OR id_pastor_auxiliar!=?) LIMIT 1""",
            (
                usuario,
                int(id_pastor_auxiliar) if id_pastor_auxiliar else None,
                int(id_pastor_auxiliar) if id_pastor_auxiliar else None,
            ),
        ).fetchone()
        if duplicado:
            raise ValueError("Ja existe um Pastor Auxiliar com este usuario.")
        dados = (
            id_cadastro, nome, usuario, sanitizar(telefone),
            sanitizar(email), situacao, sanitizar(observacoes),
        )
        if id_pastor_auxiliar:
            if senha:
                conn.execute(
                    """UPDATE pastores_auxiliares
                       SET id_cadastro=?, nome=?, usuario=?, telefone=?, email=?,
                           situacao=?, observacoes=?, senha_hash=?,
                           atualizado_em=datetime('now')
                       WHERE id_pastor_auxiliar=?""",
                    dados + (hash_senha(senha), int(id_pastor_auxiliar)),
                )
            else:
                conn.execute(
                    """UPDATE pastores_auxiliares
                       SET id_cadastro=?, nome=?, usuario=?, telefone=?, email=?,
                           situacao=?, observacoes=?, atualizado_em=datetime('now')
                       WHERE id_pastor_auxiliar=?""",
                    dados + (int(id_pastor_auxiliar),),
                )
            return int(id_pastor_auxiliar)
        cur = conn.execute(
            """INSERT INTO pastores_auxiliares
               (id_cadastro, nome, usuario, senha_hash, telefone, email,
                situacao, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id_cadastro, nome, usuario, hash_senha(senha),
                sanitizar(telefone), sanitizar(email), situacao,
                sanitizar(observacoes),
            ),
        )
        return cur.lastrowid


def inativar_pastor_auxiliar(slug, id_pastor_auxiliar):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabela_pastores_auxiliares(conn)
        conn.execute(
            """UPDATE pastores_auxiliares
               SET situacao='Inativo', atualizado_em=datetime('now')
               WHERE id_pastor_auxiliar=?""",
            (int(id_pastor_auxiliar),),
        )


def autenticar_pastor_auxiliar(slug, usuario, senha):
    try:
        slug = _validar_slug(slug)
        usuario = _normalizar_usuario_pastor_auxiliar(usuario)
    except ValueError:
        return None
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None
    chave = f"pastor_auxiliar:{slug}:{usuario}"
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_pastores_auxiliares(conn)
        if _autenticacao_bloqueada(conn, chave):
            return None
        row = conn.execute(
            """SELECT id_pastor_auxiliar, nome, usuario, senha_hash
               FROM pastores_auxiliares
               WHERE usuario=? AND situacao='Ativo'""",
            (usuario,),
        ).fetchone()
        valido, migrar = _verificar_senha(senha, row["senha_hash"] if row else "")
        _registrar_resultado_login(conn, chave, valido)
        if valido and migrar:
            conn.execute(
                "UPDATE pastores_auxiliares SET senha_hash=? WHERE id_pastor_auxiliar=?",
                (hash_senha(senha), row["id_pastor_auxiliar"]),
            )
    if not row or not valido:
        return None
    return {
        "igreja": igreja,
        "pastor_auxiliar": {
            "id": row["id_pastor_auxiliar"],
            "nome": row["nome"],
            "usuario": row["usuario"],
        },
    }


def listar_secretarios_gerais(slug, incluir_inativos=True):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_secretarios_gerais(conn)
        where = "" if incluir_inativos else "WHERE situacao='Ativo'"
        return _read_sql_query_formatado(
            f"""SELECT id_secretario_geral, id_cadastro, nome, usuario,
                       telefone, email, situacao, observacoes, criado_em, atualizado_em
                FROM secretarios_gerais
                {where}
                ORDER BY situacao, nome""",
            conn,
        )


def salvar_secretario_geral(
    slug,
    nome,
    usuario,
    senha="",
    id_cadastro=None,
    telefone="",
    email="",
    situacao="Ativo",
    observacoes="",
    id_secretario_geral=None,
):
    nome = sanitizar(nome)
    usuario = _normalizar_usuario_secretario_geral(usuario)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    situacao = str(situacao or "Ativo").strip()
    if situacao not in {"Ativo", "Inativo"}:
        raise ValueError("Situacao invalida.")
    if not id_secretario_geral:
        senha = _validar_senha_secretario_geral(senha)
    elif senha:
        senha = _validar_senha_secretario_geral(senha)
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_secretarios_gerais(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
        if not nome:
            raise ValueError("Nome do Secretario Geral e obrigatorio.")
        duplicado = conn.execute(
            """SELECT 1 FROM secretarios_gerais
               WHERE usuario=? AND (? IS NULL OR id_secretario_geral!=?) LIMIT 1""",
            (
                usuario,
                int(id_secretario_geral) if id_secretario_geral else None,
                int(id_secretario_geral) if id_secretario_geral else None,
            ),
        ).fetchone()
        if duplicado:
            raise ValueError("Ja existe um Secretario Geral com este usuario.")
        dados = (
            id_cadastro, nome, usuario, sanitizar(telefone),
            sanitizar(email), situacao, sanitizar(observacoes),
        )
        if id_secretario_geral:
            if senha:
                conn.execute(
                    """UPDATE secretarios_gerais
                       SET id_cadastro=?, nome=?, usuario=?, telefone=?, email=?,
                           situacao=?, observacoes=?, senha_hash=?,
                           atualizado_em=datetime('now')
                       WHERE id_secretario_geral=?""",
                    dados + (hash_senha(senha), int(id_secretario_geral)),
                )
            else:
                conn.execute(
                    """UPDATE secretarios_gerais
                       SET id_cadastro=?, nome=?, usuario=?, telefone=?, email=?,
                           situacao=?, observacoes=?, atualizado_em=datetime('now')
                       WHERE id_secretario_geral=?""",
                    dados + (int(id_secretario_geral),),
                )
            return int(id_secretario_geral)
        cur = conn.execute(
            """INSERT INTO secretarios_gerais
               (id_cadastro, nome, usuario, senha_hash, telefone, email,
                situacao, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id_cadastro, nome, usuario, hash_senha(senha),
                sanitizar(telefone), sanitizar(email), situacao,
                sanitizar(observacoes),
            ),
        )
        return cur.lastrowid


def inativar_secretario_geral(slug, id_secretario_geral):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabela_secretarios_gerais(conn)
        conn.execute(
            """UPDATE secretarios_gerais
               SET situacao='Inativo', atualizado_em=datetime('now')
               WHERE id_secretario_geral=?""",
            (int(id_secretario_geral),),
        )


def autenticar_secretario_geral(slug, usuario, senha):
    try:
        slug = _validar_slug(slug)
        usuario = _normalizar_usuario_login_secretario_geral(usuario)
    except ValueError:
        return None
    if not usuario:
        return None
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None
    chave = f"secretario_geral:{slug}:{usuario}"
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_secretarios_gerais(conn)
        if _autenticacao_bloqueada(conn, chave):
            return None
        row = conn.execute(
            """SELECT id_secretario_geral, nome, usuario, senha_hash
               FROM secretarios_gerais
               WHERE LOWER(TRIM(usuario))=? AND situacao='Ativo'""",
            (usuario,),
        ).fetchone()
        valido, migrar = _verificar_senha(senha, row["senha_hash"] if row else "")
        _registrar_resultado_login(conn, chave, valido)
        if valido and migrar:
            conn.execute(
                "UPDATE secretarios_gerais SET senha_hash=? WHERE id_secretario_geral=?",
                (hash_senha(senha), row["id_secretario_geral"]),
            )
    if not row or not valido:
        return None
    return {
        "igreja": igreja,
        "secretario_geral": {
            "id": row["id_secretario_geral"],
            "nome": row["nome"],
            "usuario": row["usuario"],
        },
    }


def listar_recepcao_usuarios(slug, incluir_inativos=True):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_recepcao(conn)
        _sincronizar_recepcao_automatica_conn(conn)
        where = "" if incluir_inativos else "WHERE situacao='Ativo'"
        return _read_sql_query_formatado(
            f"""SELECT id_recepcao, id_cadastro, nome, usuario, telefone,
                       email, situacao, automatico, observacoes, criado_em, atualizado_em
                FROM recepcao_usuarios
                {where}
                ORDER BY situacao, nome""",
            conn,
        )


def salvar_recepcao_usuario(
    slug,
    nome,
    usuario,
    senha="",
    id_cadastro=None,
    telefone="",
    email="",
    situacao="Ativo",
    observacoes="",
    id_recepcao=None,
):
    nome = sanitizar(nome)
    usuario = _normalizar_usuario_recepcao(usuario)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    situacao = str(situacao or "Ativo").strip()
    if situacao not in {"Ativo", "Inativo"}:
        raise ValueError("Situacao invalida.")
    if not id_recepcao:
        senha = _validar_pin_recepcao(senha)
    elif senha:
        senha = _validar_pin_recepcao(senha)
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_recepcao(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
        if not nome:
            raise ValueError("Nome da Recepcao e obrigatorio.")
        duplicado = conn.execute(
            """SELECT 1 FROM recepcao_usuarios
               WHERE usuario=? AND (? IS NULL OR id_recepcao!=?) LIMIT 1""",
            (
                usuario,
                int(id_recepcao) if id_recepcao else None,
                int(id_recepcao) if id_recepcao else None,
            ),
        ).fetchone()
        if duplicado:
            raise ValueError("Ja existe um usuario da Recepcao com este usuario.")
        dados = (
            id_cadastro, nome, usuario, sanitizar(telefone),
            sanitizar(email), situacao, 0, sanitizar(observacoes),
        )
        if id_recepcao:
            if senha:
                conn.execute(
                    """UPDATE recepcao_usuarios
                       SET id_cadastro=?, nome=?, usuario=?, telefone=?, email=?,
                           situacao=?, automatico=?, observacoes=?, senha_hash=?,
                           atualizado_em=datetime('now')
                       WHERE id_recepcao=?""",
                    dados + (hash_senha(senha), int(id_recepcao)),
                )
            else:
                conn.execute(
                    """UPDATE recepcao_usuarios
                       SET id_cadastro=?, nome=?, usuario=?, telefone=?, email=?,
                           situacao=?, automatico=?, observacoes=?, atualizado_em=datetime('now')
                       WHERE id_recepcao=?""",
                    dados + (int(id_recepcao),),
                )
            return int(id_recepcao)
        cur = conn.execute(
            """INSERT INTO recepcao_usuarios
               (id_cadastro, nome, usuario, senha_hash, telefone, email,
                situacao, automatico, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id_cadastro, nome, usuario, hash_senha(senha),
                sanitizar(telefone), sanitizar(email), situacao,
                0,
                sanitizar(observacoes),
            ),
        )
        return cur.lastrowid


def inativar_recepcao_usuario(slug, id_recepcao):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabela_recepcao(conn)
        conn.execute(
            """UPDATE recepcao_usuarios
               SET situacao='Inativo', atualizado_em=datetime('now')
               WHERE id_recepcao=?""",
            (int(id_recepcao),),
        )


def autenticar_recepcao(slug, usuario, senha):
    try:
        slug = _validar_slug(slug)
        usuario = _normalizar_usuario_recepcao(usuario)
    except ValueError:
        return None
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None
    chave = f"recepcao:{slug}:{usuario}"
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_recepcao(conn)
        _sincronizar_recepcao_automatica_conn(conn)
        if _autenticacao_bloqueada(conn, chave):
            return None
        row = conn.execute(
            """SELECT id_recepcao, nome, usuario, senha_hash
               FROM recepcao_usuarios
               WHERE usuario=? AND situacao='Ativo'""",
            (usuario,),
        ).fetchone()
        valido, migrar = _verificar_senha(senha, row["senha_hash"] if row else "")
        _registrar_resultado_login(conn, chave, valido)
        if valido and migrar:
            conn.execute(
                "UPDATE recepcao_usuarios SET senha_hash=? WHERE id_recepcao=?",
                (hash_senha(senha), row["id_recepcao"]),
            )
    if not row or not valido:
        return None
    return {
        "igreja": igreja,
        "recepcao": {
            "id": row["id_recepcao"],
            "nome": row["nome"],
            "usuario": row["usuario"],
        },
    }


def autenticar_recepcao_por_cpf4(slug, cpf4):
    try:
        slug = _validar_slug(slug)
    except ValueError:
        return None

    cpf4 = "".join(c for c in str(cpf4 or "") if c.isdigit())
    if len(cpf4) != 4:
        return None

    db = _tenant_db(slug)
    if not db.exists():
        return None

    chave = f"recepcao_cpf4:{slug}"

    with _conn(db) as conn:
        if _autenticacao_bloqueada(conn, chave):
            return None

        try:
            rows = conn.execute(
                """SELECT r.id_recepcao, r.nome, r.usuario
                     FROM recepcao_usuarios r
                     JOIN cadastros c ON c.id_cadastro = r.id_cadastro
                    WHERE r.situacao='Ativo'
                      AND UPPER(TRIM(c.tipo_cadastro))='MEMBRO'
                      AND UPPER(TRIM(c.situacao))='ATIVO'
                      AND substr(
                            replace(replace(replace(COALESCE(c.cpf, ''), '.', ''), '-', ''), ' ', ''),
                            -4
                          ) = ?
                    ORDER BY r.nome
                    LIMIT 2""",
                (cpf4,),
            ).fetchall()
        except sqlite3.OperationalError:
            _garantir_tabela_recepcao(conn)
            _garantir_colunas_cadastros(conn)
            rows = conn.execute(
                """SELECT r.id_recepcao, r.nome, r.usuario
                     FROM recepcao_usuarios r
                     JOIN cadastros c ON c.id_cadastro = r.id_cadastro
                    WHERE r.situacao='Ativo'
                      AND UPPER(TRIM(c.tipo_cadastro))='MEMBRO'
                      AND UPPER(TRIM(c.situacao))='ATIVO'
                      AND substr(
                            replace(replace(replace(COALESCE(c.cpf, ''), '.', ''), '-', ''), ' ', ''),
                            -4
                          ) = ?
                    ORDER BY r.nome
                    LIMIT 2""",
                (cpf4,),
            ).fetchall()

        row = rows[0] if len(rows) == 1 else None
        _registrar_resultado_login(conn, chave, row is not None)

    if not row:
        return None

    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None

    return {
        "igreja": igreja,
        "recepcao": {
            "id": row["id_recepcao"],
            "nome": row["nome"],
            "usuario": row["usuario"],
        },
    }


def senha_pastoral_configurada(slug: str) -> bool:
    return bool(obter_config_igreja(slug, CHAVE_SENHA_PASTORAL, ""))


def definir_senha_pastoral(slug: str, senha_igreja: str, nova_senha: str) -> bool:
    erros = validar_nova_senha(nova_senha)
    if erros:
        raise ValueError(" ".join(erros))
    igreja = autenticar_igreja(slug, senha_igreja)
    if not igreja:
        return False

    slug = _validar_slug(slug)
    with _conn(_base.MASTER_DB) as conn:
        row = conn.execute(
            "SELECT senha_hash FROM igrejas WHERE slug=? AND ativa=1",
            (slug,),
        ).fetchone()
    igual_principal, _ = _verificar_senha(
        nova_senha, row["senha_hash"] if row else ""
    )
    if igual_principal:
        raise ValueError("A senha pastoral deve ser diferente da senha principal.")

    salvar_config_igreja(slug, CHAVE_SENHA_PASTORAL, hash_senha(nova_senha))
    return True


def autenticar_senha_pastoral(slug: str, senha: str) -> bool:
    try:
        db = _tenant_db(slug)
    except ValueError:
        return False
    if not db.exists():
        inicializar_tenant(slug)

    chave_login = "pastoral"
    with _conn(db) as conn:
        _garantir_tabela_config_igreja(conn)
        if _autenticacao_bloqueada(conn, chave_login):
            return False
        row = conn.execute(
            "SELECT valor FROM config_igreja WHERE chave=?",
            (CHAVE_SENHA_PASTORAL,),
        ).fetchone()
        valido, _ = _verificar_senha(senha, row["valor"] if row else "")
        _registrar_resultado_login(conn, chave_login, valido)
    return valido
