"""Dominio: leitura_biblica."""
import pandas as pd
from data import repo_base as _base
from data.repo_base import (
    PLANOS_LEITURA_BIBLICA, PLANO_LEITURA_PADRAO, _autenticacao_bloqueada, _conn,
    _garantir_colunas_cadastros, _garantir_tabela_leitores_biblia,
    _garantir_tabela_leitura_confirmacoes, _garantir_tabela_plano_leitura,
    _normalizar_telefone_leitor, _read_sql_query_formatado, _registrar_resultado_login, _tenant_db,
    _validar_senha_leitor_biblia, _verificar_senha, buscar_igreja_por_slug, hash_senha,
    inicializar_tenant, localizar_cadastro_publico, sanitizar
)


def listar_planos_leitura_biblica():
    """Retorna os planos de leitura biblica disponiveis: [{"id":..., "nome":...}, ...]."""
    return [{"id": pid, "nome": info["nome"]} for pid, info in PLANOS_LEITURA_BIBLICA.items()]


def obter_leitura_do_dia(dia_numero, plano_id=PLANO_LEITURA_PADRAO):
    """Retorna {"dia_numero": int, "passagens": str, "tema": str} para o dia informado
    (1-365) do plano informado, ou None."""
    dia_numero = int(dia_numero)
    if plano_id not in PLANOS_LEITURA_BIBLICA:
        plano_id = PLANO_LEITURA_PADRAO
    with _conn(_base.MASTER_DB) as conn:
        _garantir_tabela_plano_leitura(conn)
        row = conn.execute(
            """SELECT dia_numero, passagens, tema FROM plano_leitura_dias
               WHERE plano_id=? AND dia_numero=?""",
            (plano_id, dia_numero),
        ).fetchone()
    return dict(row) if row else None


def cadastrar_leitor_biblia(slug, nome, telefone, senha, cpf="", data_nascimento=""):
    """Cria um leitor avulso (sem vinculo com a membresia) para o plano de leitura
    biblica, com login proprio: usuario = numero de WhatsApp, autenticado por senha."""
    nome = sanitizar(nome)
    telefone_norm = _normalizar_telefone_leitor(telefone)
    cpf_limpo = "".join(c for c in str(cpf or "") if c.isdigit())
    data_nascimento = str(data_nascimento or "").strip()

    if not nome:
        raise ValueError("Nome e obrigatorio.")
    if not telefone_norm:
        raise ValueError("Numero de WhatsApp invalido.")
    erros_senha = _validar_senha_leitor_biblia(senha)
    if erros_senha:
        raise ValueError(" ".join(erros_senha))

    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_leitores_biblia(conn)
        existente = conn.execute(
            "SELECT id_leitor FROM leitores_biblia WHERE telefone=?",
            (telefone_norm,),
        ).fetchone()
        if existente:
            raise ValueError(
                "Ja existe um cadastro de leitor com esse numero de WhatsApp. "
                "Use a opcao de login."
            )
        cur = conn.execute(
            """INSERT INTO leitores_biblia
                   (nome, cpf, data_nascimento, telefone, senha_hash)
               VALUES (?, ?, ?, ?, ?)""",
            (nome, cpf_limpo or None, data_nascimento or None, telefone_norm, hash_senha(senha)),
        )
        id_leitor = cur.lastrowid
    return {"id_leitor": id_leitor, "nome": nome, "telefone": telefone_norm}


def leitor_biblia_precisa_definir_senha(slug, telefone):
    """True se ja existe um leitor avulso com esse telefone mas sem senha
    cadastrada (por exemplo, importado em lote pela secretaria)."""
    leitor = localizar_leitor_biblia_por_telefone(slug, telefone)
    return bool(leitor) and not leitor.get("senha_hash")


def definir_senha_leitor_biblia(slug, telefone, senha):
    """Define a senha de login de um leitor avulso ja existente que ainda nao
    possui senha (por exemplo, importado em lote). Retorna o cadastro no
    mesmo formato de localizar_leitor_plano_biblico, ou levanta ValueError."""
    telefone_norm = _normalizar_telefone_leitor(telefone)
    if not telefone_norm:
        raise ValueError("Informe o numero de WhatsApp.")
    erros = _validar_senha_leitor_biblia(senha)
    if erros:
        raise ValueError(" ".join(erros))

    db = _tenant_db(slug)
    if not db.exists():
        raise ValueError("Numero nao encontrado. Confira com a secretaria da igreja.")
    with _conn(db) as conn:
        _garantir_tabela_leitores_biblia(conn)
        row = conn.execute(
            "SELECT id_leitor, nome, senha_hash FROM leitores_biblia WHERE telefone=? LIMIT 1",
            (telefone_norm,),
        ).fetchone()
        if not row:
            raise ValueError("Numero nao encontrado. Confira com a secretaria da igreja.")
        if row["senha_hash"]:
            raise ValueError("Esse numero ja possui senha cadastrada. Faca login normalmente.")
        conn.execute(
            "UPDATE leitores_biblia SET senha_hash=? WHERE id_leitor=?",
            (hash_senha(senha), row["id_leitor"]),
        )
        id_leitor, nome = row["id_leitor"], row["nome"]

    igreja = buscar_igreja_por_slug(slug)
    return {
        "origem": "leitor",
        "id_pessoa": id_leitor,
        "nome": nome,
        "igreja_nome": (igreja or {}).get("nome", ""),
    }


def autenticar_leitor_biblia(slug, telefone, senha):
    """Autentica um leitor avulso pelo login proprio (telefone + senha).
    Retorna o cadastro no mesmo formato de localizar_leitor_plano_biblico,
    ou None se as credenciais forem invalidas ou a senha ainda nao existir."""
    telefone_norm = _normalizar_telefone_leitor(telefone)
    if not telefone_norm or not senha:
        return None

    db = _tenant_db(slug)
    if not db.exists():
        return None

    chave = f"leitor_biblia:{slug}:{telefone_norm}"

    with _conn(db) as conn:
        _garantir_tabela_leitores_biblia(conn)
        if _autenticacao_bloqueada(conn, chave):
            return None
        row = conn.execute(
            """SELECT id_leitor, nome, senha_hash FROM leitores_biblia
               WHERE telefone=? LIMIT 1""",
            (telefone_norm,),
        ).fetchone()
        valido, precisa_migrar = _verificar_senha(senha, row["senha_hash"] if row else "")
        _registrar_resultado_login(conn, chave, valido)
        if not row or not valido:
            return None
        if precisa_migrar:
            conn.execute(
                "UPDATE leitores_biblia SET senha_hash=? WHERE id_leitor=?",
                (hash_senha(senha), row["id_leitor"]),
            )
        id_leitor, nome = row["id_leitor"], row["nome"]

    igreja = buscar_igreja_por_slug(slug)
    return {
        "origem": "leitor",
        "id_pessoa": id_leitor,
        "nome": nome,
        "igreja_nome": (igreja or {}).get("nome", ""),
    }


def localizar_leitor_biblia(slug, cpf, data_nascimento):
    cpf_limpo = "".join(c for c in str(cpf or "") if c.isdigit())
    data_nascimento = str(data_nascimento or "").strip()
    if len(cpf_limpo) != 11 or not data_nascimento:
        return None
    db = _tenant_db(slug)
    if not db.exists():
        return None
    with _conn(db) as conn:
        _garantir_tabela_leitores_biblia(conn)
        row = conn.execute(
            """SELECT id_leitor, nome, cpf, data_nascimento, telefone
               FROM leitores_biblia WHERE cpf=? AND data_nascimento=? LIMIT 1""",
            (cpf_limpo, data_nascimento),
        ).fetchone()
    return dict(row) if row else None


def localizar_leitor_plano_biblico(slug, cpf, data_nascimento):
    """Busca a pessoa para o plano de leitura biblica: primeiro entre os membros
    cadastrados, depois entre os leitores avulsos. Retorna um dict com "origem"
    ('membro' ou 'leitor'), "id_pessoa", "nome" e "igreja_nome", ou None."""
    membro = localizar_cadastro_publico(slug, cpf, data_nascimento)
    if membro:
        return {
            "origem": "membro",
            "id_pessoa": membro["id_cadastro"],
            "nome": membro.get("nome", ""),
            "igreja_nome": membro.get("igreja_nome", ""),
        }
    leitor = localizar_leitor_biblia(slug, cpf, data_nascimento)
    if leitor:
        igreja = buscar_igreja_por_slug(slug)
        return {
            "origem": "leitor",
            "id_pessoa": leitor["id_leitor"],
            "nome": leitor.get("nome", ""),
            "igreja_nome": (igreja or {}).get("nome", ""),
        }
    return None


def localizar_leitor_biblia_por_telefone(slug, telefone):
    """Busca um leitor avulso pelo telefone (usado por leitores importados em
    lote, sem CPF cadastrado)."""
    telefone_norm = _normalizar_telefone_leitor(telefone)
    if not telefone_norm:
        return None
    db = _tenant_db(slug)
    if not db.exists():
        return None
    with _conn(db) as conn:
        _garantir_tabela_leitores_biblia(conn)
        row = conn.execute(
            """SELECT id_leitor, nome, telefone, senha_hash FROM leitores_biblia
               WHERE telefone=? LIMIT 1""",
            (telefone_norm,),
        ).fetchone()
    return dict(row) if row else None


def localizar_leitor_plano_biblico_por_telefone(slug, telefone):
    """Equivalente a localizar_leitor_plano_biblico, mas identificando o leitor
    avulso pelo telefone em vez de CPF/data de nascimento."""
    leitor = localizar_leitor_biblia_por_telefone(slug, telefone)
    if not leitor:
        return None
    igreja = buscar_igreja_por_slug(slug)
    return {
        "origem": "leitor",
        "id_pessoa": leitor["id_leitor"],
        "nome": leitor.get("nome", ""),
        "igreja_nome": (igreja or {}).get("nome", ""),
    }


def leitura_ja_confirmada(slug, origem, id_pessoa, dia_numero, plano_id=PLANO_LEITURA_PADRAO):
    db = _tenant_db(slug)
    if not db.exists():
        return False
    with _conn(db) as conn:
        _garantir_tabela_leitura_confirmacoes(conn)
        row = conn.execute(
            """SELECT 1 FROM leitura_biblica_confirmacoes
               WHERE origem=? AND id_pessoa=? AND plano_id=? AND dia_numero=? LIMIT 1""",
            (origem, int(id_pessoa), plano_id, int(dia_numero)),
        ).fetchone()
    return row is not None


def confirmar_leitura_biblica(slug, origem, id_pessoa, dia_numero, plano_id=PLANO_LEITURA_PADRAO):
    """Registra a confirmacao de leitura do dia num plano especifico. Retorna True se foi
    confirmada agora, False se ja existia uma confirmacao para essa pessoa/plano/dia."""
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_leitura_confirmacoes(conn)
        cur = conn.execute(
            """INSERT OR IGNORE INTO leitura_biblica_confirmacoes
               (origem, id_pessoa, plano_id, dia_numero) VALUES (?, ?, ?, ?)""",
            (origem, int(id_pessoa), plano_id, int(dia_numero)),
        )
        return cur.rowcount > 0


def listar_confirmacoes_leitura_biblica(slug, dia_numero=None, plano_id=None):
    """Retorna as confirmacoes de leitura biblica do tenant, com nome e origem de quem
    confirmou. Se dia_numero/plano_id forem informados, filtra por eles."""
    colunas = ["nome", "origem", "id_pessoa", "plano_id", "dia_numero", "confirmado_em"]
    db = _tenant_db(slug)
    if not db.exists():
        return pd.DataFrame(columns=colunas)
    with _conn(db) as conn:
        _garantir_tabela_leitura_confirmacoes(conn)
        _garantir_tabela_leitores_biblia(conn)
        _garantir_colunas_cadastros(conn)
        condicoes = []
        params = []
        if dia_numero is not None:
            condicoes.append("c.dia_numero=?")
            params.append(int(dia_numero))
        if plano_id is not None:
            condicoes.append("c.plano_id=?")
            params.append(plano_id)
        where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
        return _read_sql_query_formatado(
            f"""SELECT COALESCE(m.nome, l.nome) AS nome, c.origem, c.id_pessoa,
                       c.plano_id, c.dia_numero, c.confirmado_em
                FROM leitura_biblica_confirmacoes c
                LEFT JOIN cadastros m ON c.origem='membro' AND m.id_cadastro=c.id_pessoa
                LEFT JOIN leitores_biblia l ON c.origem='leitor' AND l.id_leitor=c.id_pessoa
                {where}
                ORDER BY c.confirmado_em DESC""",
            conn,
            params=params,
        )


def resumo_leitores_biblia(slug, plano_id=None):
    """Retorna, por leitor (e por plano), o total de dias confirmados e a data da
    ultima confirmacao. Se plano_id for informado, filtra apenas esse plano."""
    colunas = ["nome", "origem", "id_pessoa", "plano_id", "total_confirmacoes", "ultima_confirmacao"]
    db = _tenant_db(slug)
    if not db.exists():
        return pd.DataFrame(columns=colunas)
    with _conn(db) as conn:
        _garantir_tabela_leitura_confirmacoes(conn)
        _garantir_tabela_leitores_biblia(conn)
        _garantir_colunas_cadastros(conn)
        where = "WHERE c.plano_id=?" if plano_id is not None else ""
        params = (plano_id,) if plano_id is not None else ()
        return _read_sql_query_formatado(
            f"""SELECT COALESCE(m.nome, l.nome) AS nome, c.origem, c.id_pessoa, c.plano_id,
                      COUNT(*) AS total_confirmacoes, MAX(c.confirmado_em) AS ultima_confirmacao
               FROM leitura_biblica_confirmacoes c
               LEFT JOIN cadastros m ON c.origem='membro' AND m.id_cadastro=c.id_pessoa
               LEFT JOIN leitores_biblia l ON c.origem='leitor' AND l.id_leitor=c.id_pessoa
               {where}
               GROUP BY c.origem, c.id_pessoa, c.plano_id
               ORDER BY total_confirmacoes DESC""",
            conn,
            params=params,
        )
