"""Dominio: acesso."""
import datetime
from pathlib import Path
import pandas as pd
from data import repo_base as _base
from data.repo_base import (
    LOGGER, SITUACOES_ACESSO, TABELAS_ACESSO_USUARIOS, _autenticacao_bloqueada, _conn,
    _contar_membros_ativos_dashboard, _df_detalhes_dashboard, _fazer_backup,
    _garantir_ministerio_padrao, _garantir_tabela_config, _garantir_tabela_permissoes_usuarios,
    _garantir_tabela_tentativas_login, _garantir_tabelas_acesso_usuarios,
    _normalizar_lancamentos_dashboard, _read_sql_query_formatado, _registrar_resultado_login,
    _sincronizar_recepcao_automatica_conn, _tenant_db, _validar_senha_por_tipo_login, _validar_slug,
    _verificar_senha, autenticar_igreja, carregar_cadastros, carregar_lancamentos, hash_senha,
    inicializar_tenant, sanitizar, validar_nova_senha
)


def listar_acessos_usuarios(slug):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    linhas = []
    with _conn(db) as conn:
        _garantir_tabelas_acesso_usuarios(conn)
        _sincronizar_recepcao_automatica_conn(conn)
        for tipo_login, (tabela, id_col, rotulo) in TABELAS_ACESSO_USUARIOS.items():
            rows = conn.execute(
                f"""SELECT {id_col} AS id_usuario, nome, usuario, situacao
                    FROM {tabela}
                    ORDER BY situacao, nome"""
            ).fetchall()
            for row in rows:
                linhas.append({
                    "tipo_login": tipo_login,
                    "tipo": rotulo,
                    "id_usuario": row["id_usuario"],
                    "nome": row["nome"],
                    "usuario": row["usuario"],
                    "situacao": row["situacao"],
                })
    return pd.DataFrame(
        linhas,
        columns=["tipo_login", "tipo", "id_usuario", "nome", "usuario", "situacao"],
    )


def atualizar_situacao_acesso_usuario(slug, tipo_login, id_usuario, situacao):
    tipo_login = str(tipo_login or "").strip()
    situacao = str(situacao or "").strip()
    if tipo_login not in TABELAS_ACESSO_USUARIOS:
        raise ValueError("Tipo de login invalido.")
    if situacao not in SITUACOES_ACESSO:
        raise ValueError("Situacao de acesso invalida.")
    tabela, id_col, _ = TABELAS_ACESSO_USUARIOS[tipo_login]
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_acesso_usuarios(conn)
        conn.execute(
            f"""UPDATE {tabela}
                SET situacao=?, atualizado_em=datetime('now')
                WHERE {id_col}=?""",
            (situacao, int(id_usuario)),
        )


def redefinir_senha_acesso_usuario(slug, tipo_login, id_usuario, nova_senha):
    """
    Redefine a senha/PIN de um usuario sem expor a senha anterior.

    Use esta funcao apenas em telas administrativas ja autenticadas/autorizadas.
    Para Gestor/Pastor, informe tipo_login='igreja' e id_usuario=id da igreja.
    Para Administrador do sistema, informe tipo_login='admin' e id_usuario=usuario.
    Para os demais perfis, informe o id_usuario retornado em listar_acessos_usuarios().
    """
    tipo_login = str(tipo_login or "").strip()
    nova_senha = _validar_senha_por_tipo_login(tipo_login, nova_senha)

    if tipo_login == "igreja":
        id_igreja = int(id_usuario)
        with _conn(_base.MASTER_DB) as conn:
            row = conn.execute(
                "SELECT slug FROM igrejas WHERE id=? LIMIT 1",
                (id_igreja,),
            ).fetchone()
            if not row:
                raise ValueError("Igreja nao encontrada.")
            conn.execute(
                "UPDATE igrejas SET senha_hash=? WHERE id=?",
                (hash_senha(nova_senha), id_igreja),
            )
            _garantir_tabela_tentativas_login(conn)
            conn.execute(
                "DELETE FROM tentativas_login WHERE chave=?",
                (f"igreja:{row['slug']}",),
            )
        return True

    if tipo_login == "admin":
        usuario = str(id_usuario or "").strip()
        if not usuario:
            raise ValueError("Usuario administrador invalido.")
        with _conn(_base.MASTER_DB) as conn:
            cur = conn.execute(
                "UPDATE super_admin SET senha_hash=? WHERE usuario=?",
                (hash_senha(nova_senha), usuario),
            )
            if cur.rowcount == 0:
                raise ValueError("Usuario administrador nao encontrado.")
            _garantir_tabela_tentativas_login(conn)
            conn.execute(
                "DELETE FROM tentativas_login WHERE chave=?",
                (f"admin:{usuario.lower()}",),
            )
        return True

    if tipo_login not in TABELAS_ACESSO_USUARIOS:
        raise ValueError("Tipo de login invalido.")

    tabela, id_col, _ = TABELAS_ACESSO_USUARIOS[tipo_login]
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)

    with _conn(db) as conn:
        _garantir_tabelas_acesso_usuarios(conn)
        row = conn.execute(
            f"SELECT usuario FROM {tabela} WHERE {id_col}=? LIMIT 1",
            (int(id_usuario),),
        ).fetchone()
        if not row:
            raise ValueError("Usuario nao encontrado.")

        conn.execute(
            f"""UPDATE {tabela}
                SET senha_hash=?, atualizado_em=datetime('now')
                WHERE {id_col}=?""",
            (hash_senha(nova_senha), int(id_usuario)),
        )

        usuario = str(row["usuario"] or "").strip().lower()
        _garantir_tabela_tentativas_login(conn)
        chaves = [f"{tipo_login}:{slug}:{usuario}"]
        if tipo_login == "tesoureiro":
            chaves.append(f"tesoureiro:{usuario}")
        for chave in chaves:
            conn.execute("DELETE FROM tentativas_login WHERE chave=?", (chave,))

    return True


def obter_permissoes_usuario(slug, tipo_login, id_usuario):
    tipo_login = str(tipo_login or "").strip()
    if tipo_login not in TABELAS_ACESSO_USUARIOS or not id_usuario:
        return []
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_permissoes_usuarios(conn)
        rows = conn.execute(
            """SELECT modulo
               FROM permissoes_usuarios
               WHERE tipo_login=? AND id_usuario=? AND permitido=1
               ORDER BY modulo""",
            (tipo_login, int(id_usuario)),
        ).fetchall()
    return [row["modulo"] for row in rows]


def salvar_permissoes_usuario(slug, tipo_login, id_usuario, modulos):
    tipo_login = str(tipo_login or "").strip()
    if tipo_login not in TABELAS_ACESSO_USUARIOS:
        raise ValueError("Tipo de login invalido.")
    id_usuario = int(id_usuario)
    modulos = sorted({sanitizar(m) for m in (modulos or []) if str(m or "").strip()})
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_permissoes_usuarios(conn)
        conn.execute(
            "DELETE FROM permissoes_usuarios WHERE tipo_login=? AND id_usuario=?",
            (tipo_login, id_usuario),
        )
        for modulo in modulos:
            conn.execute(
                """INSERT INTO permissoes_usuarios
                   (tipo_login, id_usuario, modulo, permitido)
                   VALUES (?, ?, ?, 1)""",
                (tipo_login, id_usuario, modulo),
            )


def listar_igrejas():
    with _conn(_base.MASTER_DB) as conn:
        return _read_sql_query_formatado(
            "SELECT id, nome, slug, email_admin, plano, ativa, criada_em FROM igrejas ORDER BY nome",
            conn,
        )


def vincular_igreja_ministerio(ministerio_id, igreja_id, tipo_unidade="congregacao"):
    tipo_unidade = str(tipo_unidade or "").strip().lower()
    if tipo_unidade not in {"sede", "congregacao"}:
        raise ValueError("Tipo de unidade invalido.")
    with _conn(_base.MASTER_DB) as conn:
        existe_ministerio = conn.execute(
            "SELECT 1 FROM ministerios WHERE id=?", (int(ministerio_id),)
        ).fetchone()
        existe_igreja = conn.execute(
            "SELECT 1 FROM igrejas WHERE id=?", (int(igreja_id),)
        ).fetchone()
        if not existe_ministerio or not existe_igreja:
            raise ValueError("Ministerio ou igreja nao encontrado.")
        conn.execute("DELETE FROM ministerio_igrejas WHERE igreja_id=?", (int(igreja_id),))
        conn.execute(
            """INSERT INTO ministerio_igrejas (ministerio_id, igreja_id, tipo_unidade)
               VALUES (?, ?, ?)""",
            (int(ministerio_id), int(igreja_id), tipo_unidade),
        )


def listar_igrejas_ministerio(ministerio_id, incluir_inativas=False):
    with _conn(_base.MASTER_DB) as conn:
        where_ativa = "" if incluir_inativas else "AND i.ativa=1"
        return _read_sql_query_formatado(
            f"""SELECT i.id, i.nome, i.slug, i.email_admin, i.plano, i.ativa,
                       i.criada_em, mi.tipo_unidade
                FROM ministerio_igrejas mi
                JOIN igrejas i ON i.id=mi.igreja_id
                WHERE mi.ministerio_id=? {where_ativa}
                ORDER BY CASE WHEN mi.tipo_unidade='sede' THEN 0 ELSE 1 END, i.nome""",
            conn,
            params=(int(ministerio_id),),
        )


def criar_igreja(igreja):
    slug = _validar_slug(igreja.slug)
    with _conn(_base.MASTER_DB) as conn:
        cur = conn.execute(
            """INSERT INTO igrejas (nome, slug, email_admin, senha_hash, plano)
               VALUES (?, ?, ?, ?, ?)""",
            (sanitizar(igreja.nome), slug, sanitizar(igreja.email_admin),
             igreja.senha_hash, igreja.plano),
        )
        _garantir_ministerio_padrao(conn)
    inicializar_tenant(slug)
    return cur.lastrowid


def atualizar_igreja(id_igreja, nome, email, plano, ativa):
    with _conn(_base.MASTER_DB) as conn:
        conn.execute(
            "UPDATE igrejas SET nome=?, email_admin=?, plano=?, ativa=? WHERE id=?",
            (sanitizar(nome), sanitizar(email), plano, int(ativa), id_igreja),
        )


def redefinir_senha_igreja(id_igreja, nova_senha):
    erros = validar_nova_senha(nova_senha)
    if erros:
        raise ValueError(" ".join(erros))
    with _conn(_base.MASTER_DB) as conn:
        conn.execute("UPDATE igrejas SET senha_hash=? WHERE id=?",
                     (hash_senha(nova_senha), id_igreja))


def excluir_igreja(id_igreja, slug):
    slug = _validar_slug(slug)
    tenant_db = _tenant_db(slug)
    _fazer_backup(_base.MASTER_DB)
    _fazer_backup(tenant_db)
    with _conn(_base.MASTER_DB) as conn:
        conn.execute("DELETE FROM igrejas WHERE id=?", (id_igreja,))
    for caminho in (
        tenant_db,
        Path(f"{tenant_db}-wal"),
        Path(f"{tenant_db}-shm"),
    ):
        caminho.unlink(missing_ok=True)
    for padrao in (f"{slug}.*", f"sidebar_{slug}.*"):
        for caminho in _base.LOGOS_DIR.glob(padrao):
            caminho.unlink()


def autenticar_super_admin(usuario, senha):
    usuario = str(usuario or "").strip()
    chave = f"admin:{usuario.lower()}"
    with _conn(_base.MASTER_DB) as conn:
        if _autenticacao_bloqueada(conn, chave):
            return False
        row = conn.execute(
            "SELECT id, senha_hash FROM super_admin WHERE usuario=?",
            (usuario,),
        ).fetchone()
        valido, migrar = _verificar_senha(senha, row["senha_hash"] if row else "")
        _registrar_resultado_login(conn, chave, valido)
        if valido and migrar:
            conn.execute(
                "UPDATE super_admin SET senha_hash=? WHERE id=?",
                (hash_senha(senha), row["id"]),
            )
    return valido


def alterar_senha_super_admin(usuario, nova_senha):
    erros = validar_nova_senha(nova_senha)
    if erros:
        raise ValueError(" ".join(erros))
    with _conn(_base.MASTER_DB) as conn:
        conn.execute("UPDATE super_admin SET senha_hash=? WHERE usuario=?",
                     (hash_senha(nova_senha), usuario))


def carregar_dashboard_ministerio(ministerio_id, data_inicio, data_fim, incluir_inativas=False):
    """Consolida dados validados das igrejas vinculadas a um ministerio."""
    inicio = pd.Timestamp(data_inicio).normalize()
    fim = pd.Timestamp(data_fim).normalize()
    if pd.isna(inicio) or pd.isna(fim) or inicio > fim:
        raise ValueError("Periodo de consolidacao invalido.")

    igrejas = listar_igrejas_ministerio(ministerio_id, incluir_inativas)
    resumo_igrejas = []
    detalhes = []
    qualidade = []

    for _, igreja in igrejas.iterrows():
        slug = igreja["slug"]
        status = "ok"
        mensagem = ""
        cadastros_invalidos = 0
        lancamentos_invalidos = 0
        try:
            cad = carregar_cadastros(slug)
            lanc = carregar_lancamentos(slug)
            membros_ativos = _contar_membros_ativos_dashboard(cad)
            validos, lancamentos_invalidos = _normalizar_lancamentos_dashboard(lanc)
            periodo = validos[validos["data"].between(inicio, fim, inclusive="both")].copy()
            if not periodo.empty:
                periodo["igreja_id"] = int(igreja["id"])
                periodo["igreja"] = igreja["nome"]
                periodo["slug_igreja"] = slug
                detalhes.append(periodo)
            entradas = float(periodo.loc[periodo["tipo"] == "Entrada", "valor"].sum())
            saidas = float(periodo.loc[periodo["tipo"] == "Saida", "valor"].sum())
            if lancamentos_invalidos:
                status = "incompleto"
                mensagem = "Existem lancamentos invalidos excluidos dos indicadores."
        except Exception as ex:
            LOGGER.exception("Falha ao consolidar dados da igreja %s", slug)
            membros_ativos = 0
            entradas = saidas = 0.0
            status = "erro"
            mensagem = str(ex)

        resumo_igrejas.append({
            "igreja_id": int(igreja["id"]),
            "igreja": igreja["nome"],
            "slug": slug,
            "tipo_unidade": igreja["tipo_unidade"],
            "ativa": bool(igreja["ativa"]),
            "plano": igreja["plano"],
            "membros_ativos": membros_ativos,
            "entradas": entradas,
            "saidas": saidas,
            "resultado": entradas - saidas,
            "status_qualidade": status,
        })
        qualidade.append({
            "igreja": igreja["nome"],
            "slug": slug,
            "status": status,
            "lancamentos_invalidos": lancamentos_invalidos,
            "cadastros_invalidos": cadastros_invalidos,
            "mensagem": mensagem,
        })

    detalhe = pd.concat(detalhes, ignore_index=True) if detalhes else _df_detalhes_dashboard()
    por_igreja = pd.DataFrame(resumo_igrejas)
    df_qualidade = pd.DataFrame(qualidade)
    if detalhe.empty:
        mensal = pd.DataFrame(columns=["mes", "entradas", "saidas", "resultado"])
    else:
        detalhe["mes"] = detalhe["data"].dt.to_period("M").astype(str)
        mensal = (
            detalhe.pivot_table(
                index="mes", columns="tipo", values="valor", aggfunc="sum", fill_value=0.0
            )
            .rename(columns={"Entrada": "entradas", "Saida": "saidas"})
            .reset_index()
        )
        for coluna in ("entradas", "saidas"):
            if coluna not in mensal.columns:
                mensal[coluna] = 0.0
        mensal["resultado"] = mensal["entradas"] - mensal["saidas"]
        mensal = mensal[["mes", "entradas", "saidas", "resultado"]].sort_values("mes")

    return {
        "igrejas": igrejas,
        "por_igreja": por_igreja,
        "mensal": mensal,
        "detalhes": detalhe,
        "qualidade": df_qualidade,
        "totais": {
            "igrejas": int(len(igrejas)),
            "membros_ativos": int(por_igreja["membros_ativos"].sum()) if not por_igreja.empty else 0,
            "entradas": float(por_igreja["entradas"].sum()) if not por_igreja.empty else 0.0,
            "saidas": float(por_igreja["saidas"].sum()) if not por_igreja.empty else 0.0,
            "resultado": float(por_igreja["resultado"].sum()) if not por_igreja.empty else 0.0,
            "igrejas_com_pendencias": int((df_qualidade["status"] != "ok").sum())
            if not df_qualidade.empty else 0,
        },
        "atualizado_em": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def obter_config(chave: str, padrao: str = "") -> str:
    with _conn(_base.MASTER_DB) as conn:
        _garantir_tabela_config(conn)
        row = conn.execute(
            "SELECT valor FROM config_sistema WHERE chave=?", (chave,)
        ).fetchone()
    return row["valor"] if row else padrao


def salvar_config(chave: str, valor: str):
    with _conn(_base.MASTER_DB) as conn:
        _garantir_tabela_config(conn)
        conn.execute(
            "INSERT OR REPLACE INTO config_sistema (chave, valor) VALUES (?, ?)",
            (chave, valor),
        )


def igreja_alterar_senha(slug: str, senha_atual: str, nova_senha: str) -> bool:
    erros = validar_nova_senha(nova_senha)
    if erros:
        raise ValueError(" ".join(erros))
    igreja = autenticar_igreja(slug, senha_atual)
    if not igreja:
        return False
    with _conn(_base.MASTER_DB) as conn:
        conn.execute(
            "UPDATE igrejas SET senha_hash=? WHERE slug=?",
            (hash_senha(nova_senha), slug),
        )
    return True
