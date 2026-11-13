"""Dominio: gfc."""
from data.repo_base import (
    _autenticacao_bloqueada, _conn, _garantir_colunas_cadastros, _garantir_tabelas_gfc,
    _normalizar_tipo_culto_gfc, _normalizar_usuario_gfc, _read_sql_query_formatado,
    _registrar_resultado_login, _tenant_db, _validar_pin_gfc, _validar_slug, _verificar_senha,
    buscar_igreja_por_slug, hash_senha, inicializar_tenant, sanitizar
)


def listar_gfc_grupos(slug, incluir_inativos=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        where = "" if incluir_inativos else "WHERE ativo=1"
        return _read_sql_query_formatado(
            f"""SELECT id_grupo, nome, setor, responsavel, telefone,
                       ativo, observacoes, criado_em, atualizado_em
                FROM gfc_grupos
                {where}
                ORDER BY ativo DESC, setor, nome""",
            conn,
        )


def salvar_gfc_grupo(
    slug,
    nome,
    setor="",
    responsavel="",
    telefone="",
    observacoes="",
    ativo=True,
    id_grupo=None,
):
    nome = sanitizar(nome).strip()
    setor = sanitizar(setor).strip()
    if not nome:
        raise ValueError("Informe o nome do grupo familiar.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        if id_grupo:
            conflito = conn.execute(
                """SELECT 1 FROM gfc_grupos
                   WHERE LOWER(TRIM(nome))=LOWER(TRIM(?))
                     AND LOWER(TRIM(setor))=LOWER(TRIM(?))
                     AND id_grupo<>?
                   LIMIT 1""",
                (nome, setor, int(id_grupo)),
            ).fetchone()
            if conflito:
                raise ValueError("Ja existe um grupo familiar com este nome e setor.")
            conn.execute(
                """UPDATE gfc_grupos
                   SET nome=?, setor=?, responsavel=?, telefone=?,
                       ativo=?, observacoes=?, atualizado_em=datetime('now')
                   WHERE id_grupo=?""",
                (
                    nome, setor, sanitizar(responsavel), sanitizar(telefone),
                    int(bool(ativo)), sanitizar(observacoes), int(id_grupo),
                ),
            )
            return int(id_grupo)
        cur = conn.execute(
            """INSERT INTO gfc_grupos
               (nome, setor, responsavel, telefone, ativo, observacoes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                nome, setor, sanitizar(responsavel), sanitizar(telefone),
                int(bool(ativo)), sanitizar(observacoes),
            ),
        )
        return int(cur.lastrowid)


def excluir_gfc_grupo(slug, id_grupo):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        usos = conn.execute(
            "SELECT COUNT(*) AS total FROM gfc_reunioes WHERE id_grupo=?",
            (int(id_grupo),),
        ).fetchone()["total"]
        if usos:
            conn.execute(
                "UPDATE gfc_grupos SET ativo=0, atualizado_em=datetime('now') WHERE id_grupo=?",
                (int(id_grupo),),
            )
            return False
        conn.execute("DELETE FROM gfc_grupos WHERE id_grupo=?", (int(id_grupo),))
        return True


def listar_gfc_coordenadores(slug, incluir_inativos=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        where = "" if incluir_inativos else "WHERE gc.ativo=1"
        return _read_sql_query_formatado(
            f"""SELECT gc.id_coordenador, gc.id_cadastro,
                       COALESCE(c.nome, gc.nome) AS nome,
                       COALESCE(NULLIF(c.telefone, ''), gc.telefone) AS telefone,
                       COALESCE(NULLIF(c.funcao, ''), gc.funcao) AS funcao,
                       COALESCE(NULLIF(c.congregacao, ''), gc.setor) AS setor,
                       gc.ordem, gc.ativo, gc.observacoes, gc.criado_em, gc.atualizado_em
                FROM gfc_coordenadores gc
                LEFT JOIN cadastros c ON c.id_cadastro=gc.id_cadastro
                {where}
                ORDER BY gc.ativo DESC, gc.ordem, nome""",
            conn,
        )


def salvar_gfc_coordenador(
    slug,
    nome,
    id_cadastro=None,
    telefone="",
    funcao="Coordenador",
    setor="",
    ordem=0,
    ativo=True,
    observacoes="",
    id_coordenador=None,
):
    nome = sanitizar(nome)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        _garantir_colunas_cadastros(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone, funcao, congregacao FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
                funcao = sanitizar(funcao or row["funcao"] or "Coordenador")
                setor = sanitizar(setor or row["congregacao"] or "")
        if not nome:
            raise ValueError("Nome do coordenador e obrigatorio.")
        dados = (
            id_cadastro, nome, sanitizar(telefone), sanitizar(funcao or "Coordenador"),
            sanitizar(setor), int(ordem or 0), int(bool(ativo)), sanitizar(observacoes),
        )
        if id_coordenador:
            conn.execute(
                """UPDATE gfc_coordenadores
                   SET id_cadastro=?, nome=?, telefone=?, funcao=?, setor=?,
                       ordem=?, ativo=?, observacoes=?, atualizado_em=datetime('now')
                   WHERE id_coordenador=?""",
                dados + (int(id_coordenador),),
            )
            return int(id_coordenador)
        cur = conn.execute(
            """INSERT INTO gfc_coordenadores
               (id_cadastro, nome, telefone, funcao, setor, ordem, ativo, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            dados,
        )
        return int(cur.lastrowid)


def excluir_gfc_coordenador(slug, id_coordenador):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        conn.execute(
            "DELETE FROM gfc_coordenadores WHERE id_coordenador=?",
            (int(id_coordenador),),
        )
        return True


def listar_gfc_lideres(slug, incluir_inativos=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        where = "" if incluir_inativos else "WHERE gl.ativo=1"
        return _read_sql_query_formatado(
            f"""SELECT gl.id_lider, gl.id_cadastro,
                       COALESCE(c.nome, gl.nome) AS nome,
                       COALESCE(NULLIF(c.telefone, ''), gl.telefone) AS telefone,
                       COALESCE(NULLIF(c.funcao, ''), gl.funcao) AS funcao,
                       COALESCE(NULLIF(c.congregacao, ''), gl.setor) AS setor,
                       gl.ordem, gl.ativo, gl.observacoes, gl.criado_em, gl.atualizado_em
                FROM gfc_lideres gl
                LEFT JOIN cadastros c ON c.id_cadastro=gl.id_cadastro
                {where}
                ORDER BY gl.ativo DESC, gl.ordem, nome""",
            conn,
        )


def salvar_gfc_lider(
    slug,
    nome,
    id_cadastro=None,
    telefone="",
    funcao="Lider",
    setor="",
    ordem=0,
    ativo=True,
    observacoes="",
    id_lider=None,
):
    nome = sanitizar(nome)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        _garantir_colunas_cadastros(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone, funcao, congregacao FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
                funcao = sanitizar(funcao or row["funcao"] or "Lider")
                setor = sanitizar(setor or row["congregacao"] or "")
        if not nome:
            raise ValueError("Nome do lider e obrigatorio.")
        dados = (
            id_cadastro, nome, sanitizar(telefone), sanitizar(funcao or "Lider"),
            sanitizar(setor), int(ordem or 0), int(bool(ativo)), sanitizar(observacoes),
        )
        if id_lider:
            conn.execute(
                """UPDATE gfc_lideres
                   SET id_cadastro=?, nome=?, telefone=?, funcao=?, setor=?,
                       ordem=?, ativo=?, observacoes=?, atualizado_em=datetime('now')
                   WHERE id_lider=?""",
                dados + (int(id_lider),),
            )
            return int(id_lider)
        cur = conn.execute(
            """INSERT INTO gfc_lideres
               (id_cadastro, nome, telefone, funcao, setor, ordem, ativo, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            dados,
        )
        return int(cur.lastrowid)


def excluir_gfc_lider(slug, id_lider):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        conn.execute(
            """UPDATE gfc_lideres
               SET ativo=0, atualizado_em=datetime('now')
               WHERE id_lider=?""",
            (int(id_lider),),
        )
        return False


def listar_gfc_matriculas(slug, id_grupo=None, incluir_inativas=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        where = []
        params = []
        if id_grupo:
            where.append("m.id_grupo=?")
            params.append(int(id_grupo))
        if not incluir_inativas:
            where.append("m.ativa=1")
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT m.id_matricula, m.id_grupo, g.nome AS grupo, g.setor,
                       m.id_cadastro, m.nome, m.telefone, m.ativa,
                       m.data_inicio, m.data_fim, m.observacoes,
                       c.funcao, c.congregacao, c.situacao
                FROM gfc_matriculas m
                LEFT JOIN gfc_grupos g ON g.id_grupo=m.id_grupo
                LEFT JOIN cadastros c ON c.id_cadastro=m.id_cadastro
                {filtro}
                ORDER BY g.setor, g.nome, m.ativa DESC, m.nome""",
            conn,
            params=params,
        )


def salvar_gfc_matricula(
    slug,
    id_grupo,
    nome="",
    id_cadastro=None,
    telefone="",
    data_inicio="",
    observacoes="",
    id_matricula=None,
    ativa=True,
):
    id_grupo = int(id_grupo)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    nome = sanitizar(nome)
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        grupo = conn.execute(
            "SELECT 1 FROM gfc_grupos WHERE id_grupo=?",
            (id_grupo,),
        ).fetchone()
        if not grupo:
            raise ValueError("Grupo familiar nao encontrado.")
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
        if not nome:
            raise ValueError("Nome do matriculado e obrigatorio.")
        dados = (
            id_grupo, id_cadastro, nome, sanitizar(telefone), int(bool(ativa)),
            str(data_inicio or ""), sanitizar(observacoes),
        )
        if id_matricula:
            conn.execute(
                """UPDATE gfc_matriculas
                   SET id_grupo=?, id_cadastro=?, nome=?, telefone=?, ativa=?,
                       data_inicio=?, observacoes=?, atualizado_em=datetime('now')
                   WHERE id_matricula=?""",
                dados + (int(id_matricula),),
            )
            return int(id_matricula)
        cur = conn.execute(
            """INSERT INTO gfc_matriculas
               (id_grupo, id_cadastro, nome, telefone, ativa, data_inicio, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id_grupo, id_cadastro) DO UPDATE SET
                   nome=excluded.nome,
                   telefone=excluded.telefone,
                   ativa=1,
                   data_inicio=excluded.data_inicio,
                   data_fim='',
                   observacoes=excluded.observacoes,
                   atualizado_em=datetime('now')""",
            dados,
        )
        if id_cadastro:
            row = conn.execute(
                "SELECT id_matricula FROM gfc_matriculas WHERE id_grupo=? AND id_cadastro=?",
                (id_grupo, id_cadastro),
            ).fetchone()
            return int(row["id_matricula"])
        return int(cur.lastrowid)


def encerrar_gfc_matricula(slug, id_matricula, data_fim=""):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        conn.execute(
            """UPDATE gfc_matriculas
               SET ativa=0, data_fim=?, atualizado_em=datetime('now')
               WHERE id_matricula=?""",
            (str(data_fim or ""), int(id_matricula)),
        )


def excluir_gfc_matricula(slug, id_matricula, data_fim=""):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        usos = conn.execute(
            "SELECT COUNT(*) AS total FROM gfc_presencas WHERE id_matricula=?",
            (int(id_matricula),),
        ).fetchone()["total"]
        if usos:
            conn.execute(
                """UPDATE gfc_matriculas
                   SET ativa=0, data_fim=?, atualizado_em=datetime('now')
                   WHERE id_matricula=?""",
                (str(data_fim or ""), int(id_matricula)),
            )
            return False
        conn.execute(
            "DELETE FROM gfc_matriculas WHERE id_matricula=?",
            (int(id_matricula),),
        )
        return True


def listar_gfc_reunioes(slug, data_inicio=None, data_fim=None, id_grupo=None, setor="", tipo_culto=""):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        where = []
        params = []
        if data_inicio:
            where.append("r.data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("r.data<=?")
            params.append(str(data_fim))
        if id_grupo:
            where.append("r.id_grupo=?")
            params.append(int(id_grupo))
        if str(setor or "").strip():
            where.append("LOWER(TRIM(r.setor))=LOWER(TRIM(?))")
            params.append(str(setor).strip())
        if str(tipo_culto or "").strip():
            where.append("r.tipo_culto=?")
            params.append(_normalizar_tipo_culto_gfc(tipo_culto))
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT r.id_reuniao, r.data, r.id_grupo,
                       COALESCE(g.nome, r.grupo_nome) AS grupo,
                       r.grupo_nome, r.setor, r.tipo_culto, r.tema,
                       r.coordenador1_nome, r.coordenador2_nome, r.lider_nome,
                       r.qtd_pessoas, r.qtd_participantes, r.qtd_presentes,
                       r.qtd_ausentes, r.qtd_nao_crentes, r.qtd_conversoes,
                       r.observacoes, r.criado_em, r.atualizado_em
                FROM gfc_reunioes r
                LEFT JOIN gfc_grupos g ON g.id_grupo=r.id_grupo
                {filtro}
                ORDER BY r.data DESC, r.setor, grupo""",
            conn,
            params=params,
        )


def listar_gfc_presencas(slug, id_reuniao):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        return _read_sql_query_formatado(
            """SELECT id_presenca, id_reuniao, id_matricula, id_cadastro, nome, presente, observacao
               FROM gfc_presencas
               WHERE id_reuniao=?
               ORDER BY nome""",
            conn,
            params=(int(id_reuniao),),
        )


def salvar_gfc_reuniao(
    slug,
    data,
    id_grupo,
    tipo_culto,
    tema="",
    coordenador1_nome="",
    coordenador2_nome="",
    lider_nome="",
    qtd_pessoas=0,
    qtd_nao_crentes=0,
    qtd_conversoes=0,
    observacoes="",
    presencas=None,
    id_reuniao=None,
):
    data = str(data or "").strip()
    if not data:
        raise ValueError("Informe a data do culto do GFC.")
    tipo_culto = _normalizar_tipo_culto_gfc(tipo_culto)
    try:
        qtd_pessoas = max(int(qtd_pessoas or 0), 0)
        qtd_nao_crentes = max(int(qtd_nao_crentes or 0), 0)
        qtd_conversoes = max(int(qtd_conversoes or 0), 0)
    except (TypeError, ValueError) as ex:
        raise ValueError("Informe quantidades validas para o GFC.") from ex
    if qtd_nao_crentes > qtd_pessoas:
        raise ValueError("A quantidade de nao crentes nao pode ser maior que a quantidade de pessoas.")
    if qtd_conversoes > qtd_nao_crentes:
        raise ValueError("A quantidade de conversoes nao pode ser maior que a quantidade de nao crentes.")

    presencas = presencas or []
    qtd_participantes = len(presencas)
    qtd_presentes = sum(1 for p in presencas if bool(p.get("presente")))
    qtd_ausentes = max(qtd_participantes - qtd_presentes, 0)

    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        grupo = conn.execute(
            "SELECT nome, setor FROM gfc_grupos WHERE id_grupo=?",
            (int(id_grupo),),
        ).fetchone()
        if not grupo:
            raise ValueError("Grupo familiar nao encontrado.")
        grupo_nome = grupo["nome"]
        setor = grupo["setor"] or ""

        def _salvar_presencas(id_reuniao_final):
            conn.execute("DELETE FROM gfc_presencas WHERE id_reuniao=?", (int(id_reuniao_final),))
            for presenca in presencas:
                nome_presenca = sanitizar(str(presenca.get("nome", "") or "").strip())
                if not nome_presenca:
                    continue
                id_matricula_presenca = presenca.get("id_matricula")
                id_cadastro_presenca = presenca.get("id_cadastro")
                conn.execute(
                    """INSERT INTO gfc_presencas
                       (id_reuniao, id_matricula, id_cadastro, nome, presente, observacao)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        int(id_reuniao_final),
                        int(id_matricula_presenca) if id_matricula_presenca else None,
                        int(id_cadastro_presenca) if id_cadastro_presenca else None,
                        nome_presenca,
                        1 if bool(presenca.get("presente")) else 0,
                        sanitizar(presenca.get("observacao", "") or ""),
                    ),
                )

        if id_reuniao:
            id_reuniao = int(id_reuniao)
            conflito = conn.execute(
                """SELECT 1 FROM gfc_reunioes
                   WHERE data=? AND id_grupo=? AND tipo_culto=? AND id_reuniao<>?
                   LIMIT 1""",
                (data, int(id_grupo), tipo_culto, id_reuniao),
            ).fetchone()
            if conflito:
                raise ValueError("Ja existe um registro deste grupo, data e tipo de culto.")
            conn.execute(
                """UPDATE gfc_reunioes
                   SET data=?, id_grupo=?, grupo_nome=?, setor=?, tipo_culto=?,
                       tema=?, coordenador1_nome=?, coordenador2_nome=?, lider_nome=?,
                       qtd_pessoas=?, qtd_participantes=?, qtd_presentes=?, qtd_ausentes=?,
                       qtd_nao_crentes=?, qtd_conversoes=?, observacoes=?, atualizado_em=datetime('now')
                   WHERE id_reuniao=?""",
                (
                    data, int(id_grupo), sanitizar(grupo_nome), sanitizar(setor), tipo_culto,
                    sanitizar(tema), sanitizar(coordenador1_nome), sanitizar(coordenador2_nome),
                    sanitizar(lider_nome), qtd_pessoas, qtd_participantes,
                    qtd_presentes, qtd_ausentes, qtd_nao_crentes,
                    qtd_conversoes, sanitizar(observacoes), id_reuniao,
                ),
            )
            _salvar_presencas(id_reuniao)
            return id_reuniao
        cur = conn.execute(
            """INSERT INTO gfc_reunioes
               (data, id_grupo, grupo_nome, setor, tipo_culto, tema,
                coordenador1_nome, coordenador2_nome, lider_nome,
                qtd_pessoas, qtd_participantes, qtd_presentes, qtd_ausentes,
                qtd_nao_crentes, qtd_conversoes, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(data, id_grupo, tipo_culto) DO UPDATE SET
                   grupo_nome=excluded.grupo_nome,
                   setor=excluded.setor,
                   tema=excluded.tema,
                   coordenador1_nome=excluded.coordenador1_nome,
                   coordenador2_nome=excluded.coordenador2_nome,
                   lider_nome=excluded.lider_nome,
                   qtd_pessoas=excluded.qtd_pessoas,
                   qtd_participantes=excluded.qtd_participantes,
                   qtd_presentes=excluded.qtd_presentes,
                   qtd_ausentes=excluded.qtd_ausentes,
                   qtd_nao_crentes=excluded.qtd_nao_crentes,
                   qtd_conversoes=excluded.qtd_conversoes,
                   observacoes=excluded.observacoes,
                   atualizado_em=datetime('now')""",
            (
                data, int(id_grupo), sanitizar(grupo_nome), sanitizar(setor),
                tipo_culto, sanitizar(tema), sanitizar(coordenador1_nome),
                sanitizar(coordenador2_nome), sanitizar(lider_nome), qtd_pessoas,
                qtd_participantes, qtd_presentes, qtd_ausentes,
                qtd_nao_crentes, qtd_conversoes, sanitizar(observacoes),
            ),
        )
        row = conn.execute(
            "SELECT id_reuniao FROM gfc_reunioes WHERE data=? AND id_grupo=? AND tipo_culto=?",
            (data, int(id_grupo), tipo_culto),
        ).fetchone()
        id_final = int(row["id_reuniao"] if row else cur.lastrowid)
        _salvar_presencas(id_final)
        return id_final


def excluir_gfc_reuniao(slug, id_reuniao):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        conn.execute("DELETE FROM gfc_reunioes WHERE id_reuniao=?", (int(id_reuniao),))


def listar_gfc_secretarias(slug, incluir_inativas=True):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        where = "" if incluir_inativas else "WHERE situacao='Ativo'"
        return _read_sql_query_formatado(
            f"""SELECT id_secretaria, id_cadastro, nome, usuario, perfil, telefone, email,
                       situacao, observacoes, criado_em, atualizado_em
                FROM gfc_secretarias
                {where}
                ORDER BY situacao, nome""",
            conn,
        )


def salvar_gfc_secretaria(
    slug,
    nome,
    usuario,
    senha="",
    id_cadastro=None,
    perfil="chamada",
    telefone="",
    email="",
    situacao="Ativo",
    observacoes="",
    id_secretaria=None,
):
    nome = sanitizar(nome)
    usuario = _normalizar_usuario_gfc(usuario)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    perfil = str(perfil or "").strip().lower()
    situacao = str(situacao or "Ativo").strip()
    if perfil not in {"chamada", "geral"}:
        raise ValueError("Perfil de secretaria GFC invalido.")
    if situacao not in {"Ativo", "Inativo"}:
        raise ValueError("Situacao invalida.")
    if not id_secretaria:
        senha = _validar_pin_gfc(senha)
    elif senha:
        senha = _validar_pin_gfc(senha)

    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        _garantir_colunas_cadastros(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
        if not nome:
            raise ValueError("Nome da secretaria GFC e obrigatorio.")
        duplicado = conn.execute(
            """SELECT 1 FROM gfc_secretarias
               WHERE usuario=? AND (? IS NULL OR id_secretaria!=?) LIMIT 1""",
            (
                usuario,
                int(id_secretaria) if id_secretaria else None,
                int(id_secretaria) if id_secretaria else None,
            ),
        ).fetchone()
        if duplicado:
            raise ValueError("Ja existe uma secretaria GFC com este usuario.")
        dados = (
            id_cadastro, nome, usuario, perfil, sanitizar(telefone), sanitizar(email),
            situacao, sanitizar(observacoes),
        )
        if id_secretaria:
            if senha:
                conn.execute(
                    """UPDATE gfc_secretarias
                       SET id_cadastro=?, nome=?, usuario=?, perfil=?, telefone=?, email=?,
                           situacao=?, observacoes=?, senha_hash=?,
                           atualizado_em=datetime('now')
                       WHERE id_secretaria=?""",
                    dados + (hash_senha(senha), int(id_secretaria)),
                )
            else:
                conn.execute(
                    """UPDATE gfc_secretarias
                       SET id_cadastro=?, nome=?, usuario=?, perfil=?, telefone=?, email=?,
                           situacao=?, observacoes=?, atualizado_em=datetime('now')
                       WHERE id_secretaria=?""",
                    dados + (int(id_secretaria),),
                )
            return int(id_secretaria)
        cur = conn.execute(
            """INSERT INTO gfc_secretarias
               (id_cadastro, nome, usuario, senha_hash, perfil, telefone, email,
                situacao, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id_cadastro, nome, usuario, hash_senha(senha), perfil,
                sanitizar(telefone), sanitizar(email), situacao, sanitizar(observacoes),
            ),
        )
        return cur.lastrowid


def inativar_gfc_secretaria(slug, id_secretaria):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        conn.execute(
            """UPDATE gfc_secretarias
               SET situacao='Inativo', atualizado_em=datetime('now')
               WHERE id_secretaria=?""",
            (int(id_secretaria),),
        )


def autenticar_gfc_secretaria(slug, usuario, senha):
    try:
        slug = _validar_slug(slug)
        usuario = _normalizar_usuario_gfc(usuario)
    except ValueError:
        return None
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None
    chave = f"gfc:{slug}:{usuario}"
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        if _autenticacao_bloqueada(conn, chave):
            return None
        row = conn.execute(
            """SELECT id_secretaria, nome, usuario, senha_hash, perfil
               FROM gfc_secretarias
               WHERE usuario=? AND situacao='Ativo'""",
            (usuario,),
        ).fetchone()
        valido, migrar = _verificar_senha(senha, row["senha_hash"] if row else "")
        _registrar_resultado_login(conn, chave, valido)
        if valido and migrar:
            conn.execute(
                "UPDATE gfc_secretarias SET senha_hash=? WHERE id_secretaria=?",
                (hash_senha(senha), row["id_secretaria"]),
            )
    if not row or not valido:
        return None
    return {
        "igreja": igreja,
        "secretaria_gfc": {
            "id": row["id_secretaria"],
            "nome": row["nome"],
            "usuario": row["usuario"],
            "perfil": row["perfil"],
        },
    }


def autenticar_gfc_secretaria_por_cpf4(slug, usuario, cpf4):
    try:
        slug = _validar_slug(slug)
        usuario = _normalizar_usuario_gfc(usuario)
    except ValueError:
        return None

    cpf4 = "".join(c for c in str(cpf4 or "") if c.isdigit())
    if len(cpf4) != 4:
        return None

    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None

    chave = f"gfc_cpf4:{slug}:{usuario}"
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)

    with _conn(db) as conn:
        _garantir_tabelas_gfc(conn)
        _garantir_colunas_cadastros(conn)
        if _autenticacao_bloqueada(conn, chave):
            return None

        row = conn.execute(
            """SELECT s.id_secretaria, s.nome, s.usuario, s.perfil
                 FROM gfc_secretarias s
                 JOIN cadastros c ON c.id_cadastro=s.id_cadastro
                WHERE s.usuario=?
                  AND s.situacao='Ativo'
                  AND UPPER(TRIM(c.tipo_cadastro))='MEMBRO'
                  AND UPPER(TRIM(c.situacao))='ATIVO'
                  AND substr(
                        replace(replace(replace(COALESCE(c.cpf, ''), '.', ''), '-', ''), ' ', ''),
                        -4
                      )=?
                LIMIT 1""",
            (usuario, cpf4),
        ).fetchone()
        valido = row is not None
        _registrar_resultado_login(conn, chave, valido)

    if not row:
        return None

    return {
        "igreja": igreja,
        "secretaria_gfc": {
            "id": row["id_secretaria"],
            "nome": row["nome"],
            "usuario": row["usuario"],
            "perfil": row["perfil"],
        },
    }
