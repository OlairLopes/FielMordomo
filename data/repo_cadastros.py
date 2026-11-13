"""Dominio: cadastros."""
import hmac
from data import repo_base as _base
from data.repo_base import (
    LIMITES_MEMBROS_PLANO, LimiteMembrosExcedido, _conn, _fazer_backup, _garantir_colunas_cadastros,
    _garantir_tabela_pre_cadastros, _garantir_tabela_recepcao, _read_sql_query_formatado,
    _sincronizar_recepcao_cadastro_conn, _tenant_db, _validar_slug, buscar_igreja_por_slug,
    cpf_existe, inicializar_tenant, obter_config_igreja, sanitizar
)


def validar_membro_eventos_por_cpf(slug, cpf):
    return localizar_membro_por_pin_cpf(slug, cpf)


def localizar_membro_por_pin_cpf(slug, pin_cpf):
    cpf = "".join(c for c in str(pin_cpf or "") if c.isdigit())
    if len(cpf) != 11:
        raise ValueError("Informe o CPF completo com 11 digitos, sem pontos e sem hifen.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_colunas_cadastros(conn)
        rows = conn.execute(
            """SELECT id_cadastro, nome, telefone, congregacao
               FROM cadastros
               WHERE UPPER(TRIM(tipo_cadastro))='MEMBRO'
                     AND UPPER(TRIM(situacao))='ATIVO'
                     AND cpf=?
               ORDER BY nome""",
            (cpf,),
        ).fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError(
            "Ha mais de um membro com este CPF. Procure a secretaria para registrar o pedido."
        )
    return dict(rows[0])


def _limite_membros_da_igreja(slug: str):
    with _conn(_base.MASTER_DB) as conn:
        row = conn.execute(
            "SELECT plano FROM igrejas WHERE slug=? AND ativa=1", (slug,)
        ).fetchone()
    plano = str(row["plano"] if row else "basico").strip().lower()
    return LIMITES_MEMBROS_PLANO.get(plano, LIMITES_MEMBROS_PLANO["basico"])


def _garantir_limite_membros(conn, slug: str, id_excluir=None):
    limite = _limite_membros_da_igreja(slug)
    if limite is None:
        return
    if id_excluir is None:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM cadastros WHERE UPPER(TRIM(tipo_cadastro))='MEMBRO'"
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT COUNT(*) AS n FROM cadastros
               WHERE UPPER(TRIM(tipo_cadastro))='MEMBRO' AND id_cadastro!=?""",
            (id_excluir,),
        ).fetchone()
    if row["n"] >= limite:
        raise LimiteMembrosExcedido(
            f"O plano atual permite no maximo {limite} membros."
        )


def inserir_cadastro(slug, c):
    db = _tenant_db(slug)
    cpf_limpo = "".join(d for d in c.cpf if d.isdigit()) if c.cpf else ""
    cep_limpo = "".join(d for d in c.cep if d.isdigit()) if c.cep else ""
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_colunas_cadastros(conn)
        if c.tipo_cadastro == "Membro":
            _garantir_limite_membros(conn, slug)
        cur = conn.execute(
            """INSERT INTO cadastros
               (tipo_cadastro, nome, funcao, congregacao, cpf,
                data_nascimento, sexo, telefone, logradouro, numero, bairro, cidade, cep, situacao, foto)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.tipo_cadastro, sanitizar(c.nome), sanitizar(c.funcao),
             sanitizar(c.congregacao), cpf_limpo,
             sanitizar(getattr(c, "data_nascimento", "")),
             sanitizar(getattr(c, "sexo", "")),
             sanitizar(c.telefone), sanitizar(c.logradouro),
             sanitizar(c.numero), sanitizar(c.bairro),
             sanitizar(c.cidade), cep_limpo, c.situacao,
             getattr(c, "foto", "") or ""),
        )
        id_cadastro = cur.lastrowid
        if c.tipo_cadastro == "Membro":
            _sincronizar_recepcao_cadastro_conn(conn, id_cadastro)
        return id_cadastro


def atualizar_cadastro(slug, c):
    db = _tenant_db(slug)
    cpf_limpo = "".join(d for d in c.cpf if d.isdigit()) if c.cpf else ""
    cep_limpo = "".join(d for d in c.cep if d.isdigit()) if c.cep else ""
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_colunas_cadastros(conn)
        if c.tipo_cadastro == "Membro":
            _garantir_limite_membros(conn, slug, id_excluir=c.id_cadastro)
        conn.execute(
            """UPDATE cadastros
               SET tipo_cadastro=?, nome=?, funcao=?, congregacao=?, cpf=?,
                   data_nascimento=?, sexo=?, telefone=?, logradouro=?, numero=?,
                   bairro=?, cidade=?, cep=?, situacao=?, foto=?
               WHERE id_cadastro=?""",
            (c.tipo_cadastro, sanitizar(c.nome), sanitizar(c.funcao),
             sanitizar(c.congregacao), cpf_limpo,
             sanitizar(getattr(c, "data_nascimento", "")),
             sanitizar(getattr(c, "sexo", "")),
             sanitizar(c.telefone), sanitizar(c.logradouro),
             sanitizar(c.numero), sanitizar(c.bairro),
             sanitizar(c.cidade), cep_limpo,
             c.situacao, getattr(c, "foto", "") or "", c.id_cadastro),
        )
        _sincronizar_recepcao_cadastro_conn(conn, c.id_cadastro)


def atualizar_cadastro_publico(slug, id_cadastro, cpf, data_nascimento, dados):
    slug = _validar_slug(slug)
    cpf_limpo = "".join(c for c in str(cpf or "") if c.isdigit())
    data_nascimento = str(data_nascimento or "").strip()
    if len(cpf_limpo) != 11 or not data_nascimento:
        raise ValueError("CPF e data de nascimento sao obrigatorios.")
    nome = sanitizar(dados.get("nome", ""))
    if not nome:
        raise ValueError("Nome e obrigatorio.")
    cep_limpo = "".join(c for c in str(dados.get("cep", "")) if c.isdigit())
    if cep_limpo and len(cep_limpo) != 8:
        raise ValueError("CEP invalido. Informe 8 digitos.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_colunas_cadastros(conn)
        row = conn.execute(
            """SELECT id_cadastro FROM cadastros
               WHERE id_cadastro=? AND cpf=? AND data_nascimento=?
                     AND UPPER(TRIM(tipo_cadastro))='MEMBRO'
               LIMIT 1""",
            (int(id_cadastro), cpf_limpo, data_nascimento),
        ).fetchone()
        if not row:
            raise ValueError("Cadastro nao localizado para os dados informados.")
        conn.execute(
            """UPDATE cadastros
               SET nome=?, sexo=?, estado_civil=?, tipo_membro=?, funcao=?,
                   data_batismo_aguas=?, data_batismo_espirito_santo=?,
                   telefone=?, logradouro=?, numero=?, bairro=?, cidade=?, cep=?
               WHERE id_cadastro=?""",
            (
                nome,
                sanitizar(dados.get("sexo", "")),
                sanitizar(dados.get("estado_civil", "")),
                sanitizar(dados.get("tipo_membro", "")),
                sanitizar(dados.get("funcao", "")),
                sanitizar(dados.get("data_batismo_aguas", "")),
                sanitizar(dados.get("data_batismo_espirito_santo", "")),
                sanitizar(dados.get("telefone", "")),
                sanitizar(dados.get("logradouro", "")),
                sanitizar(dados.get("numero", "")),
                sanitizar(dados.get("bairro", "")),
                sanitizar(dados.get("cidade", "")),
                cep_limpo,
                int(id_cadastro),
            ),
        )
        _sincronizar_recepcao_cadastro_conn(conn, int(id_cadastro))


def validar_codigo_atualizacao_cadastral(slug, codigo):
    try:
        slug = _validar_slug(slug)
    except ValueError:
        return False
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return False
    codigo_config = obter_config_igreja(slug, "codigo_atualizacao_cadastral", "")
    if not codigo_config:
        return False
    return hmac.compare_digest(str(codigo_config).strip(), str(codigo or "").strip())


def criar_pre_cadastro_publico(slug, dados):
    slug = _validar_slug(slug)
    nome = sanitizar(dados.get("nome", ""))
    cpf_limpo = "".join(c for c in str(dados.get("cpf", "")) if c.isdigit())
    data_nascimento = str(dados.get("data_nascimento", "") or "").strip()
    if not nome:
        raise ValueError("Nome e obrigatorio.")
    if len(cpf_limpo) != 11:
        raise ValueError("CPF invalido.")
    if not data_nascimento:
        raise ValueError("Data de nascimento e obrigatoria.")
    cep_limpo = "".join(c for c in str(dados.get("cep", "")) if c.isdigit())
    if cep_limpo and len(cep_limpo) != 8:
        raise ValueError("CEP invalido. Informe 8 digitos.")
    if cpf_existe(slug, cpf_limpo):
        raise ValueError("Ja existe cadastro com este CPF. Use a atualizacao cadastral.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_tabela_pre_cadastros(conn)
        pendente = conn.execute(
            """SELECT 1 FROM pre_cadastros_membros
               WHERE cpf=? AND status='Pendente' LIMIT 1""",
            (cpf_limpo,),
        ).fetchone()
        if pendente:
            raise ValueError("Ja existe um pre-cadastro pendente para este CPF.")
        cur = conn.execute(
            """INSERT INTO pre_cadastros_membros
               (nome, cpf, data_nascimento, sexo, estado_civil, tipo_membro,
                funcao, data_batismo_aguas, data_batismo_espirito_santo,
                telefone, logradouro, numero, bairro, cidade, cep, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                nome,
                cpf_limpo,
                data_nascimento,
                sanitizar(dados.get("sexo", "")),
                sanitizar(dados.get("estado_civil", "")),
                sanitizar(dados.get("tipo_membro", "")),
                sanitizar(dados.get("funcao", "")),
                sanitizar(dados.get("data_batismo_aguas", "")),
                sanitizar(dados.get("data_batismo_espirito_santo", "")),
                sanitizar(dados.get("telefone", "")),
                sanitizar(dados.get("logradouro", "")),
                sanitizar(dados.get("numero", "")),
                sanitizar(dados.get("bairro", "")),
                sanitizar(dados.get("cidade", "")),
                cep_limpo,
                sanitizar(dados.get("observacoes", "")),
            ),
        )
        return cur.lastrowid


def listar_pre_cadastros_membros(slug, status="Pendente"):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_pre_cadastros(conn)
        where = ""
        params = []
        if status:
            where = "WHERE status=?"
            params.append(status)
        return _read_sql_query_formatado(
            f"""SELECT * FROM pre_cadastros_membros
                {where}
                ORDER BY criado_em DESC""",
            conn,
            params=params,
        )


def atualizar_status_pre_cadastro(slug, id_pre_cadastro, status, observacoes=""):
    status = str(status or "").strip()
    if status not in {"Pendente", "Aprovado", "Rejeitado", "Duplicado"}:
        raise ValueError("Status de pre-cadastro invalido.")
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabela_pre_cadastros(conn)
        conn.execute(
            """UPDATE pre_cadastros_membros
               SET status=?, observacoes=?, atualizado_em=datetime('now')
               WHERE id_pre_cadastro=?""",
            (status, sanitizar(observacoes), int(id_pre_cadastro)),
        )


def aprovar_pre_cadastro_membro(slug, id_pre_cadastro):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_colunas_cadastros(conn)
        _garantir_tabela_pre_cadastros(conn)
        row = conn.execute(
            """SELECT * FROM pre_cadastros_membros
               WHERE id_pre_cadastro=? AND status='Pendente'""",
            (int(id_pre_cadastro),),
        ).fetchone()
        if not row:
            raise ValueError("Pre-cadastro pendente nao localizado.")
        cpf_ja_cadastrado = conn.execute(
            "SELECT 1 FROM cadastros WHERE cpf=? LIMIT 1", (row["cpf"],)
        ).fetchone()
        if cpf_ja_cadastrado:
            conn.execute(
                """UPDATE pre_cadastros_membros
                   SET status='Duplicado', atualizado_em=datetime('now')
                   WHERE id_pre_cadastro=?""",
                (int(id_pre_cadastro),),
            )
            raise ValueError("CPF ja cadastrado. Pre-cadastro marcado como duplicado.")
        _garantir_limite_membros(conn, slug)
        cur = conn.execute(
            """INSERT INTO cadastros
               (tipo_cadastro, nome, funcao, congregacao, cpf, data_nascimento,
                sexo, estado_civil, tipo_membro, data_batismo_aguas,
                data_batismo_espirito_santo, telefone, logradouro, numero,
                bairro, cidade, cep, situacao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Ativo')""",
            (
                "Membro",
                sanitizar(row["nome"]),
                sanitizar(row["funcao"]),
                slug,
                row["cpf"],
                row["data_nascimento"],
                sanitizar(row["sexo"]),
                sanitizar(row["estado_civil"]),
                sanitizar(row["tipo_membro"]),
                sanitizar(row["data_batismo_aguas"]),
                sanitizar(row["data_batismo_espirito_santo"]),
                sanitizar(row["telefone"]),
                sanitizar(row["logradouro"]),
                sanitizar(row["numero"]),
                sanitizar(row["bairro"]),
                sanitizar(row["cidade"]),
                row["cep"],
            ),
        )
        _sincronizar_recepcao_cadastro_conn(conn, cur.lastrowid)
        conn.execute(
            """UPDATE pre_cadastros_membros
               SET status='Aprovado', atualizado_em=datetime('now')
               WHERE id_pre_cadastro=?""",
            (int(id_pre_cadastro),),
        )


def excluir_cadastro(slug, id_cadastro):
    _fazer_backup(_tenant_db(slug))
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabela_recepcao(conn)
        conn.execute(
            """UPDATE recepcao_usuarios
               SET situacao='Inativo', atualizado_em=datetime('now')
               WHERE id_cadastro=? AND automatico=1""",
            (int(id_cadastro),),
        )
        conn.execute("DELETE FROM cadastros WHERE id_cadastro=?", (id_cadastro,))


def cadastro_em_uso(slug, id_cadastro):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        row = conn.execute(
            "SELECT 1 FROM lancamentos WHERE id_cadastro=? LIMIT 1", (id_cadastro,)
        ).fetchone()
    return row is not None
