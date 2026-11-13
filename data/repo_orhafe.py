"""Dominio: orhafe."""
import datetime
from data.repo_base import (
    _autenticacao_bloqueada, _conn, _garantir_colunas_cadastros, _garantir_tabelas_orhafe,
    _normalizar_usuario_orhafe, _read_sql_query_formatado, _registrar_resultado_login, _tenant_db,
    _validar_pin_orhafe, _validar_slug, _verificar_senha, buscar_igreja_por_slug, hash_senha,
    inicializar_tenant, sanitizar
)


def listar_orhafe_coordenadoras(slug, incluir_inativas=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        where = "" if incluir_inativas else "WHERE ativa=1"
        return _read_sql_query_formatado(
            f"""SELECT id_coordenadora, id_cadastro, nome, telefone, funcao, ordem,
                       ativa, observacoes, criado_em, atualizado_em
                FROM orhafe_coordenadoras
                {where}
                ORDER BY ordem, nome""",
            conn,
        )


def salvar_orhafe_coordenadora(
    slug,
    nome,
    id_cadastro=None,
    telefone="",
    funcao="Coordenadora",
    ordem=0,
    ativa=True,
    observacoes="",
    id_coordenadora=None,
):
    nome = sanitizar(nome)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone, funcao FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
                funcao = sanitizar(funcao or row["funcao"] or "Coordenadora")
        if not nome:
            raise ValueError("Nome da coordenadora e obrigatorio.")
        dados = (
            id_cadastro, nome, sanitizar(telefone), sanitizar(funcao or "Coordenadora"),
            int(ordem or 0), int(bool(ativa)), sanitizar(observacoes),
        )
        if id_coordenadora:
            conn.execute(
                """UPDATE orhafe_coordenadoras
                   SET id_cadastro=?, nome=?, telefone=?, funcao=?, ordem=?, ativa=?,
                       observacoes=?, atualizado_em=datetime('now')
                   WHERE id_coordenadora=?""",
                dados + (int(id_coordenadora),),
            )
            return int(id_coordenadora)
        cur = conn.execute(
            """INSERT INTO orhafe_coordenadoras
               (id_cadastro, nome, telefone, funcao, ordem, ativa, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            dados,
        )
        return cur.lastrowid


def excluir_orhafe_coordenadora(slug, id_coordenadora):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        conn.execute(
            "DELETE FROM orhafe_coordenadoras WHERE id_coordenadora=?",
            (int(id_coordenadora),),
        )
        return True


def listar_orhafe_lideres(slug, incluir_inativos=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        where = "" if incluir_inativos else "WHERE ativo=1"
        return _read_sql_query_formatado(
            f"""SELECT id_lider, id_cadastro, nome, telefone, funcao, ordem, ativo,
                       observacoes, criado_em, atualizado_em
                FROM orhafe_lideres
                {where}
                ORDER BY ordem, nome""",
            conn,
        )


def salvar_orhafe_lider(
    slug,
    nome,
    id_cadastro=None,
    telefone="",
    funcao="Lider",
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
        _garantir_tabelas_orhafe(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone, funcao FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
                funcao = sanitizar(funcao or row["funcao"] or "Lider")
        if not nome:
            raise ValueError("Nome da lider e obrigatorio.")
        dados = (
            id_cadastro, nome, sanitizar(telefone), sanitizar(funcao or "Lider"),
            int(ordem or 0), int(bool(ativo)), sanitizar(observacoes),
        )
        if id_lider:
            conn.execute(
                """UPDATE orhafe_lideres
                   SET id_cadastro=?, nome=?, telefone=?, funcao=?, ordem=?, ativo=?,
                       observacoes=?, atualizado_em=datetime('now')
                   WHERE id_lider=?""",
                dados + (int(id_lider),),
            )
            return int(id_lider)
        cur = conn.execute(
            """INSERT INTO orhafe_lideres
               (id_cadastro, nome, telefone, funcao, ordem, ativo, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            dados,
        )
        return cur.lastrowid


def excluir_orhafe_lider(slug, id_lider):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        usos = conn.execute(
            "SELECT COUNT(*) AS total FROM orhafe_reunioes WHERE id_lider=?",
            (int(id_lider),),
        ).fetchone()["total"]
        if usos:
            conn.execute(
                """UPDATE orhafe_lideres
                   SET ativo=0, atualizado_em=datetime('now')
                   WHERE id_lider=?""",
                (int(id_lider),),
            )
            return False
        conn.execute("DELETE FROM orhafe_lideres WHERE id_lider=?", (int(id_lider),))
        return True


def listar_orhafe_matriculas(slug, incluir_inativas=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        where = "" if incluir_inativas else "WHERE m.ativa=1"
        return _read_sql_query_formatado(
            f"""SELECT m.id_matricula, m.id_cadastro, m.nome, m.telefone,
                       m.ativa, m.data_inicio, m.data_fim, m.observacoes,
                       c.funcao, c.congregacao, c.situacao
                FROM orhafe_matriculas m
                LEFT JOIN cadastros c ON c.id_cadastro=m.id_cadastro
                {where}
                ORDER BY m.ativa DESC, m.nome""",
            conn,
        )


def salvar_orhafe_matricula(
    slug,
    nome,
    id_cadastro=None,
    telefone="",
    data_inicio="",
    observacoes="",
    id_matricula=None,
    ativa=True,
):
    nome = sanitizar(nome)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
        if not nome:
            raise ValueError("Nome da matriculada e obrigatorio.")
        dados = (
            id_cadastro, nome, sanitizar(telefone), int(bool(ativa)),
            str(data_inicio or ""), sanitizar(observacoes),
        )
        if id_matricula:
            conn.execute(
                """UPDATE orhafe_matriculas
                   SET id_cadastro=?, nome=?, telefone=?, ativa=?,
                       data_inicio=?, observacoes=?, atualizado_em=datetime('now')
                   WHERE id_matricula=?""",
                dados + (int(id_matricula),),
            )
            return int(id_matricula)
        cur = conn.execute(
            """INSERT INTO orhafe_matriculas
               (id_cadastro, nome, telefone, ativa, data_inicio, observacoes)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id_cadastro) DO UPDATE SET
                   nome=excluded.nome,
                   telefone=excluded.telefone,
                   ativa=1,
                   data_fim='',
                   observacoes=excluded.observacoes,
                   atualizado_em=datetime('now')""",
            dados,
        )
        if id_cadastro:
            row = conn.execute(
                "SELECT id_matricula FROM orhafe_matriculas WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            return int(row["id_matricula"])
        return cur.lastrowid


def encerrar_orhafe_matricula(slug, id_matricula, data_fim=""):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        conn.execute(
            """UPDATE orhafe_matriculas
               SET ativa=0, data_fim=?, atualizado_em=datetime('now')
               WHERE id_matricula=?""",
            (str(data_fim or ""), int(id_matricula)),
        )


def excluir_orhafe_matricula(slug, id_matricula, data_fim=""):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        usos = conn.execute(
            "SELECT COUNT(*) AS total FROM orhafe_presencas WHERE id_matricula=?",
            (int(id_matricula),),
        ).fetchone()["total"]
        if usos:
            conn.execute(
                """UPDATE orhafe_matriculas
                   SET ativa=0, data_fim=?, atualizado_em=datetime('now')
                   WHERE id_matricula=?""",
                (str(data_fim or ""), int(id_matricula)),
            )
            return False
        conn.execute(
            "DELETE FROM orhafe_matriculas WHERE id_matricula=?",
            (int(id_matricula),),
        )
        return True


def listar_orhafe_reunioes(slug, data_inicio=None, data_fim=None):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        where = []
        params = []
        if data_inicio:
            where.append("r.data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("r.data<=?")
            params.append(str(data_fim))
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT r.id_reuniao, r.data, r.tema, r.id_lider,
                       COALESCE(l.nome, r.lider_nome) AS lider,
                       r.qtd_matriculadas AS matriculadas,
                       r.qtd_presentes AS presentes,
                       r.qtd_ausentes AS ausentes,
                       r.qtd_visitantes AS visitantes,
                       r.ofertas, r.observacoes, r.criado_em, r.atualizado_em
                FROM orhafe_reunioes r
                LEFT JOIN orhafe_lideres l ON l.id_lider=r.id_lider
                {filtro}
                ORDER BY r.data DESC""",
            conn,
            params=params,
        )


def carregar_orhafe_presencas(slug, id_reuniao):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        return _read_sql_query_formatado(
            """SELECT id_presenca, id_reuniao, id_matricula, nome,
                      presente, visitante, observacao
               FROM orhafe_presencas
               WHERE id_reuniao=?
               ORDER BY visitante, nome""",
            conn,
            params=(int(id_reuniao),),
        )


def salvar_orhafe_chamada(
    slug,
    data,
    id_lider=None,
    lider_nome="",
    tema="",
    observacoes="",
    presencas=None,
    visitantes=None,
    ofertas=0,
    id_reuniao=None,
):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    presencas = presencas or {}
    visitantes = visitantes or []
    try:
        ofertas = max(float(ofertas or 0), 0.0)
    except (TypeError, ValueError) as ex:
        raise ValueError("Informe um valor valido para ofertas.") from ex
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        data_ref = str(data or "").strip()

        def normalizar_data_texto(valor):
            texto = str(valor or "").strip()
            if not texto:
                return ""
            for formato in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.datetime.strptime(texto, formato).date().isoformat()
                except ValueError:
                    continue
            return texto

        data_ref = normalizar_data_texto(data_ref)

        def matricula_valida_na_data(row):
            if not row:
                return False
            inicio = normalizar_data_texto(row["data_inicio"])
            fim = normalizar_data_texto(row["data_fim"])
            if inicio and data_ref and inicio > data_ref:
                return False
            if fim and data_ref and fim < data_ref:
                return False
            return True

        id_lider = int(id_lider) if id_lider else None
        if id_lider:
            row_lider = conn.execute(
                "SELECT nome FROM orhafe_lideres WHERE id_lider=?",
                (id_lider,),
            ).fetchone()
            if row_lider:
                lider_nome = row_lider["nome"]
        dados_presenca = []
        for id_matricula, marcado in presencas.items():
            row = conn.execute(
                """SELECT nome, ativa, data_inicio, data_fim
                   FROM orhafe_matriculas
                   WHERE id_matricula=?""",
                (int(id_matricula),),
            ).fetchone()
            if matricula_valida_na_data(row):
                dados_presenca.append((int(id_matricula), row["nome"], bool(marcado), False))
        nomes_visitantes = [
            sanitizar(nome)
            for nome in visitantes
            if str(nome or "").strip()
        ]
        qtd_matriculadas = len(dados_presenca)
        qtd_presentes = sum(1 for _, _, marcado, _ in dados_presenca if marcado)
        qtd_ausentes = max(qtd_matriculadas - qtd_presentes, 0)
        qtd_visitantes = len(nomes_visitantes)

        if id_reuniao:
            id_reuniao = int(id_reuniao)
            conflito = conn.execute(
                "SELECT 1 FROM orhafe_reunioes WHERE data=? AND id_reuniao<>? LIMIT 1",
                (str(data), id_reuniao),
            ).fetchone()
            if conflito:
                raise ValueError("Ja existe uma chamada do Circulo de Oracao nesta data.")
            conn.execute(
                """UPDATE orhafe_reunioes
                   SET data=?, tema=?, id_lider=?, lider_nome=?,
                       qtd_matriculadas=?, qtd_presentes=?, qtd_ausentes=?,
                       qtd_visitantes=?, ofertas=?, observacoes=?,
                       atualizado_em=datetime('now')
                   WHERE id_reuniao=?""",
                (
                    str(data), sanitizar(tema), id_lider, sanitizar(lider_nome),
                    qtd_matriculadas, qtd_presentes, qtd_ausentes, qtd_visitantes,
                    ofertas, sanitizar(observacoes), id_reuniao,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO orhafe_reunioes
                   (data, tema, id_lider, lider_nome, qtd_matriculadas,
                    qtd_presentes, qtd_ausentes, qtd_visitantes, ofertas, observacoes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(data) DO UPDATE SET
                       tema=excluded.tema,
                       id_lider=excluded.id_lider,
                       lider_nome=excluded.lider_nome,
                       qtd_matriculadas=excluded.qtd_matriculadas,
                       qtd_presentes=excluded.qtd_presentes,
                       qtd_ausentes=excluded.qtd_ausentes,
                       qtd_visitantes=excluded.qtd_visitantes,
                       ofertas=excluded.ofertas,
                       observacoes=excluded.observacoes,
                       atualizado_em=datetime('now')""",
                (
                    str(data), sanitizar(tema), id_lider, sanitizar(lider_nome),
                    qtd_matriculadas, qtd_presentes, qtd_ausentes, qtd_visitantes,
                    ofertas, sanitizar(observacoes),
                ),
            )
            row_reuniao = conn.execute(
                "SELECT id_reuniao FROM orhafe_reunioes WHERE data=?",
                (str(data),),
            ).fetchone()
            id_reuniao = int(row_reuniao["id_reuniao"])
        conn.execute("DELETE FROM orhafe_presencas WHERE id_reuniao=?", (id_reuniao,))
        for id_matricula, nome, presente, visitante in dados_presenca:
            conn.execute(
                """INSERT INTO orhafe_presencas
                   (id_reuniao, id_matricula, nome, presente, visitante)
                   VALUES (?, ?, ?, ?, ?)""",
                (id_reuniao, id_matricula, sanitizar(nome), int(presente), int(visitante)),
            )
        for nome in nomes_visitantes:
            conn.execute(
                """INSERT INTO orhafe_presencas
                   (id_reuniao, id_matricula, nome, presente, visitante)
                   VALUES (?, NULL, ?, 1, 1)""",
                (id_reuniao, nome),
            )
        return id_reuniao


def relatorio_orhafe_frequencia(slug, data_inicio=None, data_fim=None):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        where = ["p.visitante=0"]
        params = []
        if data_inicio:
            where.append("r.data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("r.data<=?")
            params.append(str(data_fim))
        filtro = f"WHERE {' AND '.join(where)}"
        return _read_sql_query_formatado(
            f"""SELECT p.nome,
                       COUNT(p.id_presenca) AS reunioes,
                       SUM(CASE WHEN p.presente=1 THEN 1 ELSE 0 END) AS presencas,
                       SUM(CASE WHEN p.presente=0 THEN 1 ELSE 0 END) AS ausencias
                FROM orhafe_presencas p
                JOIN orhafe_reunioes r ON r.id_reuniao=p.id_reuniao
                {filtro}
                GROUP BY p.nome
                ORDER BY p.nome""",
            conn,
            params=params,
        )


def relatorio_orhafe_visitantes(slug, data_inicio=None, data_fim=None):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        where = ["p.visitante=1", "TRIM(COALESCE(p.nome, ''))<>''"]
        params = []
        if data_inicio:
            where.append("r.data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("r.data<=?")
            params.append(str(data_fim))
        filtro = f"WHERE {' AND '.join(where)}"
        return _read_sql_query_formatado(
            f"""SELECT TRIM(p.nome) AS nome,
                       COALESCE(NULLIF(TRIM(l.nome), ''), 'Sem lider') AS lider,
                       COUNT(p.id_presenca) AS visitas
                FROM orhafe_presencas p
                JOIN orhafe_reunioes r ON r.id_reuniao=p.id_reuniao
                LEFT JOIN orhafe_lideres l ON l.id_lider=r.id_lider
                {filtro}
                GROUP BY LOWER(TRIM(p.nome)), COALESCE(NULLIF(TRIM(l.nome), ''), 'Sem lider')
                ORDER BY nome""",
            conn,
            params=params,
        )


def listar_orhafe_secretarias(slug, incluir_inativas=True):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        where = "" if incluir_inativas else "WHERE situacao='Ativo'"
        return _read_sql_query_formatado(
            f"""SELECT id_secretaria, id_cadastro, nome, usuario, perfil, telefone, email,
                       situacao, observacoes, criado_em, atualizado_em
                FROM orhafe_secretarias
                {where}
                ORDER BY situacao, nome""",
            conn,
        )


def salvar_orhafe_secretaria(
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
    usuario = _normalizar_usuario_orhafe(usuario)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    perfil = str(perfil or "").strip().lower()
    situacao = str(situacao or "Ativo").strip()
    if perfil not in {"chamada", "geral"}:
        raise ValueError("Perfil de secretaria invalido.")
    if situacao not in {"Ativo", "Inativo"}:
        raise ValueError("Situacao invalida.")
    if not id_secretaria:
        senha = _validar_pin_orhafe(senha)
    elif senha:
        senha = _validar_pin_orhafe(senha)

    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome, telefone FROM cadastros WHERE id_cadastro=?",
                (id_cadastro,),
            ).fetchone()
            if row:
                nome = sanitizar(row["nome"])
                telefone = sanitizar(telefone or row["telefone"] or "")
        if not nome:
            raise ValueError("Nome da secretaria e obrigatorio.")
        duplicado = conn.execute(
            """SELECT 1 FROM orhafe_secretarias
               WHERE usuario=? AND (? IS NULL OR id_secretaria!=?) LIMIT 1""",
            (
                usuario,
                int(id_secretaria) if id_secretaria else None,
                int(id_secretaria) if id_secretaria else None,
            ),
        ).fetchone()
        if duplicado:
            raise ValueError("Já existe uma secretária do Círculo de Oração com este usuário.")
        dados = (
            id_cadastro, nome, usuario, perfil, sanitizar(telefone), sanitizar(email),
            situacao, sanitizar(observacoes),
        )
        if id_secretaria:
            if senha:
                conn.execute(
                    """UPDATE orhafe_secretarias
                       SET id_cadastro=?, nome=?, usuario=?, perfil=?, telefone=?, email=?,
                           situacao=?, observacoes=?, senha_hash=?,
                           atualizado_em=datetime('now')
                       WHERE id_secretaria=?""",
                    dados + (hash_senha(senha), int(id_secretaria)),
                )
            else:
                conn.execute(
                    """UPDATE orhafe_secretarias
                       SET id_cadastro=?, nome=?, usuario=?, perfil=?, telefone=?, email=?,
                           situacao=?, observacoes=?, atualizado_em=datetime('now')
                       WHERE id_secretaria=?""",
                    dados + (int(id_secretaria),),
                )
            return int(id_secretaria)
        cur = conn.execute(
            """INSERT INTO orhafe_secretarias
               (id_cadastro, nome, usuario, senha_hash, perfil, telefone, email,
                situacao, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id_cadastro, nome, usuario, hash_senha(senha), perfil, sanitizar(telefone),
                sanitizar(email), situacao, sanitizar(observacoes),
            ),
        )
        return cur.lastrowid


def inativar_orhafe_secretaria(slug, id_secretaria):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        conn.execute(
            """UPDATE orhafe_secretarias
               SET situacao='Inativo', atualizado_em=datetime('now')
               WHERE id_secretaria=?""",
            (int(id_secretaria),),
        )


def autenticar_orhafe_secretaria(slug, usuario, senha):
    try:
        slug = _validar_slug(slug)
        usuario = _normalizar_usuario_orhafe(usuario)
    except ValueError:
        return None
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None
    chave = f"orhafe:{slug}:{usuario}"
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        if _autenticacao_bloqueada(conn, chave):
            return None
        row = conn.execute(
            """SELECT id_secretaria, nome, usuario, senha_hash, perfil
               FROM orhafe_secretarias
               WHERE usuario=? AND situacao='Ativo'""",
            (usuario,),
        ).fetchone()
        valido, migrar = _verificar_senha(senha, row["senha_hash"] if row else "")
        _registrar_resultado_login(conn, chave, valido)
        if valido and migrar:
            conn.execute(
                "UPDATE orhafe_secretarias SET senha_hash=? WHERE id_secretaria=?",
                (hash_senha(senha), row["id_secretaria"]),
            )
    if not row or not valido:
        return None
    return {
        "igreja": igreja,
        "secretaria_orhafe": {
            "id": row["id_secretaria"],
            "nome": row["nome"],
            "usuario": row["usuario"],
            "perfil": row["perfil"],
        },
    }


def autenticar_orhafe_secretaria_por_cpf4(slug, usuario, cpf4):
    try:
        slug = _validar_slug(slug)
        usuario = _normalizar_usuario_orhafe(usuario)
    except ValueError:
        return None

    cpf4 = "".join(c for c in str(cpf4 or "") if c.isdigit())
    if len(cpf4) != 4:
        return None

    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None

    chave = f"orhafe_cpf4:{slug}:{usuario}"
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)

    with _conn(db) as conn:
        _garantir_tabelas_orhafe(conn)
        _garantir_colunas_cadastros(conn)
        if _autenticacao_bloqueada(conn, chave):
            return None

        row = conn.execute(
            """SELECT s.id_secretaria, s.nome, s.usuario, s.perfil
                 FROM orhafe_secretarias s
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
        "secretaria_orhafe": {
            "id": row["id_secretaria"],
            "nome": row["nome"],
            "usuario": row["usuario"],
            "perfil": row["perfil"],
        },
    }
