"""Dominio: ebd."""
import datetime
import pandas as pd
from data.repo_base import (
    _autenticacao_bloqueada, _conn, _garantir_tabelas_ebd, _normalizar_usuario_ebd,
    _read_sql_query_formatado, _registrar_resultado_login, _tenant_db, _validar_pin_ebd,
    _validar_slug, _verificar_senha, buscar_igreja_por_slug, hash_senha, inicializar_tenant,
    sanitizar
)


def listar_ebd_classes(slug, incluir_inativas=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        where = "" if incluir_inativas else "WHERE ativa=1"
        return _read_sql_query_formatado(
            f"""SELECT id_classe, nome, faixa_etaria, professor_principal,
                       sala, ativa, observacoes, criado_em, atualizado_em
                FROM ebd_classes
                {where}
                ORDER BY ativa DESC, nome""",
            conn,
        )


def salvar_ebd_classe(slug, nome, faixa_etaria="", professor_principal="", sala="", observacoes="", ativa=True, id_classe=None):
    nome = sanitizar(nome)
    if not nome:
        raise ValueError("Nome da classe e obrigatorio.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        dados = (
            nome,
            sanitizar(faixa_etaria),
            sanitizar(professor_principal),
            sanitizar(sala),
            int(bool(ativa)),
            sanitizar(observacoes),
        )
        if id_classe:
            conn.execute(
                """UPDATE ebd_classes
                   SET nome=?, faixa_etaria=?, professor_principal=?, sala=?,
                       ativa=?, observacoes=?, atualizado_em=datetime('now')
                   WHERE id_classe=?""",
                (*dados, int(id_classe)),
            )
            return int(id_classe)
        cur = conn.execute(
            """INSERT INTO ebd_classes
               (nome, faixa_etaria, professor_principal, sala, ativa, observacoes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            dados,
        )
        return cur.lastrowid


def excluir_ebd_classe(slug, id_classe):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        usados = conn.execute(
            """SELECT
                   (SELECT COUNT(*) FROM ebd_matriculas WHERE id_classe=?) +
                   (SELECT COUNT(*) FROM ebd_aulas WHERE id_classe=?)""",
            (int(id_classe), int(id_classe)),
        ).fetchone()[0]
        if usados:
            conn.execute("UPDATE ebd_classes SET ativa=0 WHERE id_classe=?", (int(id_classe),))
            return False
        conn.execute("DELETE FROM ebd_classes WHERE id_classe=?", (int(id_classe),))
        return True


def listar_ebd_matriculas(slug, id_classe=None, incluir_inativas=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        where = []
        params = []
        if id_classe:
            where.append("m.id_classe=?")
            params.append(int(id_classe))
        if not incluir_inativas:
            where.append("m.ativa=1")
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT m.id_matricula, m.id_classe, c.nome AS classe,
                       m.id_cadastro, m.nome_aluno, m.ativa, m.data_inicio,
                       m.data_fim, m.observacoes
                FROM ebd_matriculas m
                JOIN ebd_classes c ON c.id_classe=m.id_classe
                {filtro}
                ORDER BY c.nome, m.nome_aluno""",
            conn,
            params=params,
        )


def salvar_ebd_matricula(slug, id_classe, nome_aluno, id_cadastro=None, data_inicio="", observacoes="", id_matricula=None, ativa=True, data_fim=None):
    nome_aluno = sanitizar(nome_aluno)
    if not nome_aluno:
        raise ValueError("Nome do aluno e obrigatorio.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    id_cadastro = None if id_cadastro is None or pd.isna(id_cadastro) else int(id_cadastro)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome FROM cadastros WHERE id_cadastro=?", (id_cadastro,)
            ).fetchone()
            if row:
                nome_aluno = sanitizar(row["nome"])
        if id_matricula:
            if data_fim is None:
                conn.execute(
                    """UPDATE ebd_matriculas
                       SET id_classe=?, id_cadastro=?, nome_aluno=?, ativa=?,
                           data_inicio=?, observacoes=?
                       WHERE id_matricula=?""",
                    (
                        int(id_classe), id_cadastro, nome_aluno, int(bool(ativa)),
                        str(data_inicio or ""), sanitizar(observacoes), int(id_matricula),
                    ),
                )
            else:
                conn.execute(
                    """UPDATE ebd_matriculas
                       SET id_classe=?, id_cadastro=?, nome_aluno=?, ativa=?,
                           data_inicio=?, observacoes=?, data_fim=?
                       WHERE id_matricula=?""",
                    (
                        int(id_classe), id_cadastro, nome_aluno, int(bool(ativa)),
                        str(data_inicio or ""), sanitizar(observacoes), str(data_fim or ""),
                        int(id_matricula),
                    ),
                )
            return int(id_matricula)
        cur = conn.execute(
            """INSERT INTO ebd_matriculas
               (id_classe, id_cadastro, nome_aluno, ativa, data_inicio, observacoes, data_fim)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                int(id_classe), id_cadastro, nome_aluno, int(bool(ativa)),
                str(data_inicio or ""), sanitizar(observacoes), str(data_fim or ""),
            ),
        )
        return cur.lastrowid


def encerrar_ebd_matricula(slug, id_matricula, data_fim=""):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        conn.execute(
            "UPDATE ebd_matriculas SET ativa=0, data_fim=? WHERE id_matricula=?",
            (str(data_fim or ""), int(id_matricula)),
        )


def listar_ebd_aulas(slug, data_inicio=None, data_fim=None, id_classe=None):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        where = []
        params = []
        if data_inicio:
            where.append("a.data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("a.data<=?")
            params.append(str(data_fim))
        if id_classe:
            where.append("a.id_classe=?")
            params.append(int(id_classe))
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT a.id_aula, a.id_classe, c.nome AS classe, a.data,
                       a.tema, a.professor,
                       CASE WHEN a.qtd_matriculados > 0
                            THEN a.qtd_matriculados
                            ELSE COUNT(p.id_presenca)
                       END AS matriculados,
                       CASE WHEN a.qtd_presentes > 0
                            THEN a.qtd_presentes
                            ELSE SUM(CASE WHEN p.presente=1 THEN 1 ELSE 0 END)
                       END AS presentes,
                       CASE WHEN a.qtd_ausentes > 0
                            THEN a.qtd_ausentes
                            ELSE SUM(CASE WHEN p.presente=0 THEN 1 ELSE 0 END)
                       END AS ausentes,
                       a.qtd_visitantes AS visitantes,
                       a.qtd_assistentes AS assistentes,
                       a.qtd_revistas, a.qtd_biblias,
                       a.qtd_harpas, a.ofertas, a.observacoes,
                       COUNT(p.id_presenca) AS matriculados_lista,
                       SUM(CASE WHEN p.presente=1 THEN 1 ELSE 0 END) AS presentes_lista
                FROM ebd_aulas a
                JOIN ebd_classes c ON c.id_classe=a.id_classe
                LEFT JOIN ebd_presencas p ON p.id_aula=a.id_aula
                {filtro}
                GROUP BY a.id_aula, a.id_classe, c.nome, a.data, a.tema,
                         a.professor, a.qtd_matriculados, a.qtd_presentes,
                         a.qtd_ausentes, a.qtd_visitantes, a.qtd_assistentes,
                         a.qtd_revistas, a.qtd_biblias,
                         a.qtd_harpas, a.ofertas, a.observacoes
                ORDER BY a.data DESC, c.nome""",
            conn,
            params=params,
        )


def salvar_ebd_chamada(
    slug,
    id_classe,
    data,
    tema="",
    professor="",
    observacoes="",
    presencas=None,
    qtd_matriculados=0,
    qtd_presentes=0,
    qtd_ausentes=0,
    qtd_visitantes=0,
    qtd_assistentes=0,
    qtd_revistas=0,
    qtd_biblias=0,
    qtd_harpas=0,
    ofertas=0,
    id_aula=None,
):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    presencas = presencas or {}
    try:
        qtd_matriculados = max(int(qtd_matriculados or 0), 0)
        qtd_presentes = max(int(qtd_presentes or 0), 0)
        qtd_ausentes = max(int(qtd_ausentes or 0), 0)
        qtd_visitantes = max(int(qtd_visitantes or 0), 0)
        qtd_assistentes = max(int(qtd_assistentes or 0), 0)
        qtd_revistas = max(int(qtd_revistas or 0), 0)
        qtd_biblias = max(int(qtd_biblias or 0), 0)
        qtd_harpas = max(int(qtd_harpas or 0), 0)
        ofertas = max(float(ofertas or 0), 0.0)
    except (TypeError, ValueError) as ex:
        raise ValueError("Informe valores validos para a chamada da Escola Bíblica.") from ex
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
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

        presencas_validas = []
        for id_matricula, presente in presencas.items():
            row_matricula = conn.execute(
                """SELECT id_matricula, id_classe, data_inicio, data_fim
                   FROM ebd_matriculas
                   WHERE id_matricula=? AND id_classe=?""",
                (int(id_matricula), int(id_classe)),
            ).fetchone()
            if matricula_valida_na_data(row_matricula):
                presencas_validas.append((int(id_matricula), int(bool(presente))))

        qtd_matriculados = len(presencas_validas)
        qtd_presentes = sum(presente for _, presente in presencas_validas)
        qtd_ausentes = max(qtd_matriculados - qtd_presentes, 0)

        if id_aula:
            id_aula = int(id_aula)
            conflito = conn.execute(
                """SELECT 1 FROM ebd_aulas
                   WHERE id_classe=? AND data=? AND id_aula<>?
                   LIMIT 1""",
                (int(id_classe), str(data), id_aula),
            ).fetchone()
            if conflito:
                raise ValueError("Ja existe uma chamada desta classe nesta data.")
            conn.execute(
                """UPDATE ebd_aulas
                   SET id_classe=?, data=?, tema=?, professor=?,
                       qtd_matriculados=?, qtd_presentes=?, qtd_ausentes=?,
                       qtd_visitantes=?, qtd_assistentes=?, qtd_revistas=?, qtd_biblias=?,
                       qtd_harpas=?, ofertas=?, observacoes=?
                   WHERE id_aula=?""",
                (
                    int(id_classe), str(data), sanitizar(tema),
                    sanitizar(professor), qtd_matriculados, qtd_presentes,
                    qtd_ausentes, qtd_visitantes, qtd_assistentes, qtd_revistas, qtd_biblias,
                    qtd_harpas, ofertas, sanitizar(observacoes), id_aula,
                ),
            )
        else:
            cur = conn.execute(
                """INSERT INTO ebd_aulas
                   (id_classe, data, tema, professor, qtd_matriculados, qtd_presentes,
                    qtd_ausentes, qtd_visitantes, qtd_assistentes, qtd_revistas, qtd_biblias,
                    qtd_harpas, ofertas, observacoes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id_classe, data) DO UPDATE SET
                       tema=excluded.tema,
                       professor=excluded.professor,
                       qtd_matriculados=excluded.qtd_matriculados,
                       qtd_presentes=excluded.qtd_presentes,
                       qtd_ausentes=excluded.qtd_ausentes,
                       qtd_visitantes=excluded.qtd_visitantes,
                       qtd_assistentes=excluded.qtd_assistentes,
                       qtd_revistas=excluded.qtd_revistas,
                       qtd_biblias=excluded.qtd_biblias,
                       qtd_harpas=excluded.qtd_harpas,
                       ofertas=excluded.ofertas,
                       observacoes=excluded.observacoes""",
                (
                    int(id_classe), str(data), sanitizar(tema),
                    sanitizar(professor), qtd_matriculados, qtd_presentes,
                    qtd_ausentes, qtd_visitantes, qtd_assistentes, qtd_revistas, qtd_biblias,
                    qtd_harpas, ofertas, sanitizar(observacoes),
                ),
            )
            row = conn.execute(
                "SELECT id_aula FROM ebd_aulas WHERE id_classe=? AND data=?",
                (int(id_classe), str(data)),
            ).fetchone()
            id_aula = int(row["id_aula"] if row else cur.lastrowid)
        conn.execute("DELETE FROM ebd_presencas WHERE id_aula=?", (id_aula,))
        for id_matricula, presente in presencas_validas:
            conn.execute(
                """INSERT INTO ebd_presencas (id_aula, id_matricula, presente)
                   VALUES (?, ?, ?)
                   ON CONFLICT(id_aula, id_matricula) DO UPDATE SET
                       presente=excluded.presente""",
                (id_aula, id_matricula, presente),
            )
        return id_aula


def carregar_ebd_presencas(slug, id_aula):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        return _read_sql_query_formatado(
            """SELECT p.id_presenca, p.id_aula, p.id_matricula, p.presente,
                      m.nome_aluno, c.nome AS classe
               FROM ebd_presencas p
               JOIN ebd_matriculas m ON m.id_matricula=p.id_matricula
               JOIN ebd_classes c ON c.id_classe=m.id_classe
               WHERE p.id_aula=?
               ORDER BY m.nome_aluno""",
            conn,
            params=(int(id_aula),),
        )


def relatorio_ebd_frequencia(slug, data_inicio=None, data_fim=None, id_classe=None):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        where = []
        params = []
        if data_inicio:
            where.append("a.data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("a.data<=?")
            params.append(str(data_fim))
        if id_classe:
            where.append("a.id_classe=?")
            params.append(int(id_classe))
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT c.nome AS classe, m.nome_aluno,
                       COUNT(p.id_presenca) AS aulas,
                       SUM(CASE WHEN p.presente=1 THEN 1 ELSE 0 END) AS presencas,
                       SUM(CASE WHEN p.presente=0 THEN 1 ELSE 0 END) AS faltas
                FROM ebd_presencas p
                JOIN ebd_aulas a ON a.id_aula=p.id_aula
                JOIN ebd_matriculas m ON m.id_matricula=p.id_matricula
                JOIN ebd_classes c ON c.id_classe=a.id_classe
                {filtro}
                GROUP BY c.nome, m.nome_aluno
                ORDER BY c.nome, m.nome_aluno""",
            conn,
            params=params,
        )


def relatorio_ebd_resumo_classes(slug, data_inicio=None, data_fim=None):
    freq = relatorio_ebd_frequencia(slug, data_inicio, data_fim)
    if freq.empty:
        return pd.DataFrame(columns=["classe", "alunos", "aulas", "presencas", "faltas", "frequencia_pct"])
    resumo = freq.groupby("classe", as_index=False).agg(
        alunos=("nome_aluno", "nunique"),
        aulas=("aulas", "max"),
        presencas=("presencas", "sum"),
        faltas=("faltas", "sum"),
    )
    total = resumo["presencas"] + resumo["faltas"]
    resumo["frequencia_pct"] = (resumo["presencas"] / total.where(total > 0, 1) * 100).round(1)
    return resumo


def listar_ebd_escala(slug, data_inicio=None, data_fim=None, id_classe=None):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        where = []
        params = []
        if data_inicio:
            where.append("e.data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("e.data<=?")
            params.append(str(data_fim))
        if id_classe:
            where.append("e.id_classe=?")
            params.append(int(id_classe))
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT e.id_escala, e.data, e.id_classe,
                       COALESCE(c.nome, e.classe_nome) AS classe,
                       e.professor, e.funcao_professor, e.telefone_professor,
                       e.superintendente, e.telefone_superintendente,
                       e.auxiliar, e.telefone_auxiliar, e.tema, e.observacoes
                FROM ebd_escala_professores e
                LEFT JOIN ebd_classes c ON c.id_classe=e.id_classe
                {filtro}
                ORDER BY e.data, classe, e.professor""",
            conn,
            params=params,
        )


def salvar_ebd_escala(
    slug,
    data,
    professor,
    id_classe=None,
    classe_nome="",
    auxiliar="",
    tema="",
    observacoes="",
    id_escala=None,
    telefone_professor="",
    funcao_professor="",
    superintendente="",
    telefone_superintendente="",
    telefone_auxiliar="",
):
    professor = sanitizar(professor)
    if not professor:
        raise ValueError("Professor e obrigatorio.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        id_classe = int(id_classe) if id_classe else None
        dados = (
            str(data),
            id_classe,
            sanitizar(classe_nome),
            professor,
            sanitizar(funcao_professor),
            sanitizar(telefone_professor),
            sanitizar(superintendente),
            sanitizar(telefone_superintendente),
            sanitizar(auxiliar),
            sanitizar(telefone_auxiliar),
            sanitizar(tema),
            sanitizar(observacoes),
        )
        if id_escala:
            conn.execute(
                """UPDATE ebd_escala_professores
                   SET data=?, id_classe=?, classe_nome=?, professor=?,
                       funcao_professor=?, telefone_professor=?,
                       superintendente=?, telefone_superintendente=?,
                       auxiliar=?, telefone_auxiliar=?,
                       tema=?, observacoes=?
                   WHERE id_escala=?""",
                (*dados, int(id_escala)),
            )
            return int(id_escala)
        cur = conn.execute(
            """INSERT INTO ebd_escala_professores
               (data, id_classe, classe_nome, professor, funcao_professor,
                telefone_professor, superintendente, telefone_superintendente,
                auxiliar, telefone_auxiliar, tema, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            dados,
        )
        return cur.lastrowid


def excluir_ebd_escala(slug, id_escala):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        conn.execute("DELETE FROM ebd_escala_professores WHERE id_escala=?", (int(id_escala),))


def listar_ebd_professores_classe(slug, id_classe=None, funcao=None, incluir_inativos=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        where = []
        params = []
        if id_classe is None:
            where.append("p.id_classe IS NULL")
        else:
            where.append("p.id_classe=?")
            params.append(int(id_classe))
        if funcao:
            where.append("p.funcao=?")
            params.append(str(funcao))
        if not incluir_inativos:
            where.append("p.ativo=1")
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT p.id_professor_classe, p.id_classe, c.nome AS classe,
                       p.funcao, p.nome, p.telefone, p.ativo, p.ordem
                FROM ebd_professores_classe p
                LEFT JOIN ebd_classes c ON c.id_classe=p.id_classe
                {filtro}
                ORDER BY p.ordem, p.nome""",
            conn,
            params=params,
        )


def salvar_ebd_professor_classe(
    slug, nome, id_classe=None, funcao="Professor", telefone="",
    ativo=True, ordem=0, id_professor_classe=None,
):
    nome = sanitizar(nome)
    if not nome:
        raise ValueError("Nome do professor e obrigatorio.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        dados = (
            int(id_classe) if id_classe else None,
            sanitizar(funcao) or "Professor",
            nome,
            sanitizar(telefone),
            int(bool(ativo)),
            int(ordem),
        )
        if id_professor_classe:
            conn.execute(
                """UPDATE ebd_professores_classe
                   SET id_classe=?, funcao=?, nome=?, telefone=?, ativo=?, ordem=?
                   WHERE id_professor_classe=?""",
                (*dados, int(id_professor_classe)),
            )
            return int(id_professor_classe)
        cur = conn.execute(
            """INSERT INTO ebd_professores_classe
               (id_classe, funcao, nome, telefone, ativo, ordem)
               VALUES (?, ?, ?, ?, ?, ?)""",
            dados,
        )
        return cur.lastrowid


def excluir_ebd_professor_classe(slug, id_professor_classe):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        conn.execute(
            "DELETE FROM ebd_professores_classe WHERE id_professor_classe=?",
            (int(id_professor_classe),),
        )


def listar_ebd_secretarios(slug, incluir_inativos=True):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        where = "" if incluir_inativos else "WHERE s.situacao='Ativo'"
        return _read_sql_query_formatado(
            f"""SELECT s.id_secretario, s.nome, s.usuario, s.perfil,
                       s.id_classe, c.nome AS classe, s.telefone, s.email,
                       s.situacao, s.observacoes, s.criado_em, s.atualizado_em
                FROM ebd_secretarios s
                LEFT JOIN ebd_classes c ON c.id_classe=s.id_classe
                {where}
                ORDER BY s.situacao, s.nome""",
            conn,
        )


def salvar_ebd_secretario(
    slug,
    nome,
    usuario,
    senha="",
    perfil="classe",
    id_classe=None,
    telefone="",
    email="",
    situacao="Ativo",
    observacoes="",
    id_secretario=None,
):
    nome = sanitizar(nome)
    usuario = _normalizar_usuario_ebd(usuario)
    perfil = str(perfil or "").strip().lower()
    situacao = str(situacao or "Ativo").strip()
    if not nome:
        raise ValueError("Nome do secretario e obrigatorio.")
    if perfil not in {"classe", "geral"}:
        raise ValueError("Perfil de secretario invalido.")
    if situacao not in {"Ativo", "Inativo"}:
        raise ValueError("Situacao invalida.")
    id_classe = int(id_classe) if id_classe else None
    if perfil == "classe" and not id_classe:
        raise ValueError("Secretario de classe precisa estar vinculado a uma classe.")
    if not id_secretario:
        senha = _validar_pin_ebd(senha)
    elif senha:
        senha = _validar_pin_ebd(senha)

    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        duplicado = conn.execute(
            """SELECT 1 FROM ebd_secretarios
               WHERE usuario=? AND (? IS NULL OR id_secretario!=?) LIMIT 1""",
            (usuario, int(id_secretario) if id_secretario else None, int(id_secretario) if id_secretario else None),
        ).fetchone()
        if duplicado:
            raise ValueError("Ja existe um secretario da Escola Bíblica com este usuario.")
        dados = (
            nome, usuario, perfil, id_classe, sanitizar(telefone),
            sanitizar(email), situacao, sanitizar(observacoes),
        )
        if id_secretario:
            if senha:
                conn.execute(
                    """UPDATE ebd_secretarios
                       SET nome=?, usuario=?, perfil=?, id_classe=?, telefone=?,
                           email=?, situacao=?, observacoes=?,
                           senha_hash=?, atualizado_em=datetime('now')
                       WHERE id_secretario=?""",
                    dados + (hash_senha(senha), int(id_secretario)),
                )
            else:
                conn.execute(
                    """UPDATE ebd_secretarios
                       SET nome=?, usuario=?, perfil=?, id_classe=?, telefone=?,
                           email=?, situacao=?, observacoes=?,
                           atualizado_em=datetime('now')
                       WHERE id_secretario=?""",
                    dados + (int(id_secretario),),
                )
            return int(id_secretario)
        cur = conn.execute(
            """INSERT INTO ebd_secretarios
               (nome, usuario, senha_hash, perfil, id_classe, telefone, email,
                situacao, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (nome, usuario, hash_senha(senha), perfil, id_classe, sanitizar(telefone),
             sanitizar(email), situacao, sanitizar(observacoes)),
        )
        return cur.lastrowid


def inativar_ebd_secretario(slug, id_secretario):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        conn.execute(
            """UPDATE ebd_secretarios
               SET situacao='Inativo', atualizado_em=datetime('now')
               WHERE id_secretario=?""",
            (int(id_secretario),),
        )


def autenticar_ebd_secretario(slug, usuario, senha):
    try:
        slug = _validar_slug(slug)
        usuario = _normalizar_usuario_ebd(usuario)
    except ValueError:
        return None
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None
    chave = f"ebd:{slug}:{usuario}"
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        if _autenticacao_bloqueada(conn, chave):
            return None
        row = conn.execute(
            """SELECT s.id_secretario, s.nome, s.usuario, s.senha_hash,
                      s.perfil, s.id_classe, c.nome AS classe
               FROM ebd_secretarios s
               LEFT JOIN ebd_classes c ON c.id_classe=s.id_classe
               WHERE s.usuario=? AND s.situacao='Ativo'""",
            (usuario,),
        ).fetchone()
        valido, migrar = _verificar_senha(senha, row["senha_hash"] if row else "")
        _registrar_resultado_login(conn, chave, valido)
        if valido and migrar:
            conn.execute(
                "UPDATE ebd_secretarios SET senha_hash=? WHERE id_secretario=?",
                (hash_senha(senha), row["id_secretario"]),
            )
    if not row or not valido:
        return None
    return {
        "igreja": igreja,
        "secretario_ebd": {
            "id": row["id_secretario"],
            "nome": row["nome"],
            "usuario": row["usuario"],
            "perfil": row["perfil"],
            "id_classe": row["id_classe"],
            "classe": row["classe"] or "",
        },
    }
