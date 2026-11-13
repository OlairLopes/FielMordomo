"""Dominio: eventos."""
import datetime
from data.repo_base import (
    SITUACOES_EVENTO, VISIBILIDADES_EVENTO, _conn, _garantir_tabelas_eventos,
    _garantir_tabelas_geo_frequencia, _read_sql_query_formatado, _tenant_db, formatar_telefone,
    inicializar_tenant, sanitizar
)


def listar_eventos_igreja(
    slug,
    data_inicio=None,
    data_fim=None,
    visibilidade="",
    situacao="",
    somente_publicavel=False,
):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_eventos(conn)
        where = []
        params = []
        if data_inicio:
            where.append("data>=?")
            params.append(str(data_inicio))
        if data_fim:
            where.append("data<=?")
            params.append(str(data_fim))
        if visibilidade:
            where.append("visibilidade=?")
            params.append(str(visibilidade))
        if situacao:
            where.append("situacao=?")
            params.append(str(situacao))
        if somente_publicavel:
            where.append("visibilidade IN ('Publico', 'Membros')")
            where.append("situacao='Programado'")
        filtro = f"WHERE {' AND '.join(where)}" if where else ""
        return _read_sql_query_formatado(
            f"""SELECT id_evento, titulo, data, hora_inicio, hora_fim, local,
                       departamento, descricao, responsavel, contato,
                       visibilidade, situacao, cartaz_nome,
                       CASE WHEN cartaz_bytes IS NULL THEN 0 ELSE 1 END AS tem_cartaz,
                       cartaz_enviado_em, criado_em, atualizado_em
                FROM eventos_igreja
                {filtro}
                ORDER BY data ASC, hora_inicio ASC, titulo ASC""",
            conn,
            params=params,
        )


def listar_eventos_publicos(slug, incluir_membros=False, data_inicio=None, data_fim=None):
    data_inicio = data_inicio or datetime.date.today().isoformat()
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    visibilidades = ["Publico", "Membros"] if incluir_membros else ["Publico"]
    placeholders = ",".join("?" for _ in visibilidades)
    params = list(visibilidades) + [str(data_inicio)]
    filtro_fim = ""
    if data_fim:
        filtro_fim = "AND data<=?"
        params.append(str(data_fim))
    with _conn(db) as conn:
        _garantir_tabelas_eventos(conn)
        return _read_sql_query_formatado(
            f"""SELECT id_evento, titulo, data, hora_inicio, hora_fim, local,
                       departamento, descricao, responsavel, contato,
                       visibilidade, situacao, cartaz_nome,
                       CASE WHEN cartaz_bytes IS NULL THEN 0 ELSE 1 END AS tem_cartaz
                FROM eventos_igreja
                WHERE visibilidade IN ({placeholders})
                      AND situacao='Programado'
                      AND data>=?
                      {filtro_fim}
                ORDER BY data ASC, hora_inicio ASC, titulo ASC""",
            conn,
            params=params,
        )


def salvar_evento_igreja(
    slug,
    titulo,
    data,
    hora_inicio="",
    hora_fim="",
    local="",
    departamento="",
    descricao="",
    responsavel="",
    contato="",
    visibilidade="Publico",
    situacao="Programado",
    cartaz_nome="",
    cartaz_mime="",
    cartaz_bytes=None,
    id_evento=None,
):
    titulo = sanitizar(titulo)
    data = str(data or "").strip()
    visibilidade = sanitizar(visibilidade or "Publico")
    situacao = sanitizar(situacao or "Programado")
    if not titulo:
        raise ValueError("Informe o titulo do evento.")
    if not data:
        raise ValueError("Informe a data do evento.")
    if visibilidade not in VISIBILIDADES_EVENTO:
        raise ValueError("Visibilidade invalida.")
    if situacao not in SITUACOES_EVENTO:
        raise ValueError("Situacao invalida.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    dados = (
        titulo,
        data,
        sanitizar(hora_inicio),
        sanitizar(hora_fim),
        sanitizar(local),
        sanitizar(departamento),
        sanitizar(descricao),
        sanitizar(responsavel),
        sanitizar(contato),
        visibilidade,
        situacao,
    )
    tem_cartaz = cartaz_bytes is not None
    with _conn(db) as conn:
        _garantir_tabelas_eventos(conn)
        if id_evento:
            conn.execute(
                """UPDATE eventos_igreja
                   SET titulo=?, data=?, hora_inicio=?, hora_fim=?, local=?,
                       departamento=?, descricao=?, responsavel=?, contato=?,
                       visibilidade=?, situacao=?,
                       cartaz_nome=CASE WHEN ? THEN ? ELSE cartaz_nome END,
                       cartaz_mime=CASE WHEN ? THEN ? ELSE cartaz_mime END,
                       cartaz_bytes=CASE WHEN ? THEN ? ELSE cartaz_bytes END,
                       cartaz_enviado_em=CASE WHEN ? THEN datetime('now') ELSE cartaz_enviado_em END,
                       atualizado_em=datetime('now')
                   WHERE id_evento=?""",
                dados + (
                    int(tem_cartaz), sanitizar(cartaz_nome),
                    int(tem_cartaz), sanitizar(cartaz_mime),
                    int(tem_cartaz), cartaz_bytes,
                    int(tem_cartaz),
                    int(id_evento),
                ),
            )
            return int(id_evento)
        cur = conn.execute(
            """INSERT INTO eventos_igreja
               (titulo, data, hora_inicio, hora_fim, local, departamento,
                descricao, responsavel, contato, visibilidade, situacao,
                cartaz_nome, cartaz_mime, cartaz_bytes, cartaz_enviado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? THEN datetime('now') ELSE '' END)""",
            dados + (
                sanitizar(cartaz_nome),
                sanitizar(cartaz_mime),
                cartaz_bytes,
                int(tem_cartaz),
            ),
        )
        return int(cur.lastrowid)


def obter_evento_cartaz(slug, id_evento):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_eventos(conn)
        row = conn.execute(
            """SELECT id_evento, titulo, data, cartaz_nome, cartaz_mime, cartaz_bytes
               FROM eventos_igreja
               WHERE id_evento=?""",
            (int(id_evento),),
        ).fetchone()
    if not row or row["cartaz_bytes"] is None:
        return None
    nome = row["cartaz_nome"] or f"cartaz-evento-{row['id_evento']}.bin"
    return {
        "id_evento": row["id_evento"],
        "titulo": row["titulo"],
        "data": row["data"],
        "nome": nome,
        "mime": row["cartaz_mime"] or "application/octet-stream",
        "bytes": row["cartaz_bytes"],
    }


def excluir_evento_igreja(slug, id_evento):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_eventos(conn)
        conn.execute("DELETE FROM eventos_igreja WHERE id_evento=?", (int(id_evento),))


def salvar_geo_evento(
    slug,
    nome,
    data,
    latitude,
    longitude,
    endereco="",
    raio_metros=30,
    captura_habilitada=False,
    ativo=True,
    mensagem_presentes="",
    mensagem_ausentes="",
    observacoes="",
    id_evento=None,
):
    nome = sanitizar(nome).strip()
    data = str(data or "").strip()
    if not nome:
        raise ValueError("Informe o nome do evento.")
    if not data:
        raise ValueError("Informe a data do evento.")

    latitude = float(latitude or 0)
    longitude = float(longitude or 0)
    raio_metros = max(1, int(raio_metros or 30))

    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_geo_frequencia(conn)
        dados = (
            nome,
            data,
            sanitizar(endereco),
            latitude,
            longitude,
            raio_metros,
            int(bool(captura_habilitada)),
            int(bool(ativo)),
            sanitizar(mensagem_presentes),
            sanitizar(mensagem_ausentes),
            sanitizar(observacoes),
        )
        if id_evento:
            conn.execute(
                """UPDATE geo_eventos
                   SET nome=?, data=?, endereco=?, latitude=?, longitude=?, raio_metros=?,
                       captura_habilitada=?, ativo=?, mensagem_presentes=?,
                       mensagem_ausentes=?, observacoes=?,
                       atualizado_em=datetime('now')
                   WHERE id_evento=?""",
                dados + (int(id_evento),),
            )
            return int(id_evento)

        cur = conn.execute(
            """INSERT INTO geo_eventos
               (nome, data, endereco, latitude, longitude, raio_metros,
                captura_habilitada, ativo, mensagem_presentes,
                mensagem_ausentes, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            dados,
        )
        return cur.lastrowid


def listar_geo_eventos(slug, incluir_inativos=True):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_geo_frequencia(conn)
        filtro = "" if incluir_inativos else "WHERE ativo=1"
        return _read_sql_query_formatado(
            f"""SELECT id_evento, nome, data, endereco, latitude, longitude, raio_metros,
                       captura_habilitada, ativo, mensagem_presentes,
                       mensagem_ausentes, observacoes, criado_em, atualizado_em
                FROM geo_eventos
                {filtro}
                ORDER BY data DESC, id_evento DESC""",
            conn,
        )


def obter_geo_evento(slug, id_evento):
    try:
        id_evento = int(id_evento)
    except (TypeError, ValueError):
        return None

    eventos = listar_geo_eventos(slug, incluir_inativos=True)
    if eventos.empty:
        return None

    filtro = eventos[eventos["id_evento"].astype(int) == id_evento]
    if filtro.empty:
        return None
    return filtro.iloc[0].to_dict()


def excluir_geo_evento(slug, id_evento):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_geo_frequencia(conn)
        conn.execute("DELETE FROM geo_eventos WHERE id_evento=?", (int(id_evento),))
        return True


def registrar_geo_presenca(
    slug,
    id_evento,
    id_cadastro,
    latitude,
    longitude,
    distancia_m,
    dentro_raio,
    presente,
    status="",
):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_geo_frequencia(conn)
        cadastro = conn.execute(
            """SELECT id_cadastro, nome, telefone
               FROM cadastros
               WHERE id_cadastro=?""",
            (int(id_cadastro),),
        ).fetchone()
        if not cadastro:
            raise ValueError("Membro nao encontrado no cadastro.")

        dados = (
            int(id_evento),
            int(id_cadastro),
            sanitizar(cadastro["nome"]),
            formatar_telefone(cadastro["telefone"]),
            float(latitude or 0),
            float(longitude or 0),
            float(distancia_m or 0),
            int(bool(dentro_raio)),
            int(bool(presente)),
            sanitizar(status),
        )
        conn.execute(
            """INSERT INTO geo_presencas
               (id_evento, id_cadastro, nome, telefone, latitude, longitude,
                distancia_m, dentro_raio, presente, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id_evento, id_cadastro) DO UPDATE SET
                   nome=excluded.nome,
                   telefone=excluded.telefone,
                   latitude=excluded.latitude,
                   longitude=excluded.longitude,
                   distancia_m=excluded.distancia_m,
                   dentro_raio=excluded.dentro_raio,
                   presente=excluded.presente,
                   status=excluded.status,
                   registrado_em=datetime('now')""",
            dados,
        )
        return True


def listar_geo_presencas(slug, id_evento):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_geo_frequencia(conn)
        return _read_sql_query_formatado(
            """SELECT id_presenca, id_evento, id_cadastro, nome, telefone,
                      latitude, longitude, distancia_m, dentro_raio,
                      presente, status, registrado_em
               FROM geo_presencas
               WHERE id_evento=?
               ORDER BY nome""",
            conn,
            params=(int(id_evento),),
        )
