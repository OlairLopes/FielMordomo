"""
Camada de persistencia multi-tenant.
"""

import os
import re
import sqlite3
import hashlib
import hmac
import logging
import math
import secrets
import shutil
import datetime
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path

import pandas as pd


LOGGER = logging.getLogger(__name__)
PBKDF2_ITERACOES = 600_000
SENHA_MIN_CARACTERES = 15
SENHA_MAX_CARACTERES = 128
TAMANHO_MAXIMO_LOGO = 5 * 1024 * 1024
TAMANHO_MAXIMO_ZIP = 100 * 1024 * 1024
TAMANHO_MAXIMO_ARQUIVOS_ZIP = 500 * 1024 * 1024
EXTENSOES_LOGO_PERMITIDAS = {"png", "jpg", "jpeg", "webp"}
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
USUARIO_TESOUREIRO_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{2,38}[a-z0-9])?$")
USUARIO_EBD_RE = USUARIO_TESOUREIRO_RE
HASH_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LIMITES_MEMBROS_PLANO = {"basico": 50, "profissional": 250, "premium": None}
CATEGORIAS_ENTRADA = {
    "Campanha", "Dizimo", "Missao", "Oferta", "Revista EBD",
    "Saldo ano anterior",
}
FORMAS_PAGAMENTO = {
    "Pix", "Dinheiro", "Transferencia", "Boleto", "Cheque",
    "Cartao Debito", "Cartao Credito",
}
MINISTERIO_PADRAO_SLUG = "ministerio-principal"


class LimiteMembrosExcedido(ValueError):
    pass


def _data_dir() -> Path:
    # 1. Prioridade maxima: variavel de ambiente FIELMORDOMO_DATA_DIR
    env = os.environ.get("FIELMORDOMO_DATA_DIR")
    if env:
        p = Path(env)
    # 2. Render.com com disco persistente
    elif os.environ.get("RENDER_PERSISTENT_DISK", "").lower() == "true":
        p = Path("/opt/render/project/src/dados")
    # 3. Windows local
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        p = Path(base) / "FielMordomo"
    # 4. Linux/Mac local ou Streamlit Cloud
    else:
        p = Path.home() / ".fielmordomo"
    p.mkdir(parents=True, exist_ok=True)
    return p


DATA_DIR = _data_dir()
MASTER_DB = DATA_DIR / "master.db"
TENANTS_DIR = DATA_DIR / "tenants"
LOGOS_DIR = DATA_DIR / "logos"
BACKUP_DIR = DATA_DIR / "backups"

TENANTS_DIR.mkdir(exist_ok=True)
LOGOS_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)


def hash_senha(senha: str) -> str:
    """Gera um hash lento com salt individual para armazenamento."""
    if not isinstance(senha, str) or not senha:
        raise ValueError("A senha nao pode ser vazia.")
    salt = secrets.token_hex(16)
    derivado = hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERACOES
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERACOES}${salt}${derivado}"


def validar_nova_senha(senha: str) -> list[str]:
    erros = []
    if not isinstance(senha, str):
        return ["Senha invalida."]
    if len(senha) < SENHA_MIN_CARACTERES:
        erros.append(
            f"A senha deve possuir ao menos {SENHA_MIN_CARACTERES} caracteres."
        )
    if len(senha) > SENHA_MAX_CARACTERES:
        erros.append(
            f"A senha deve possuir no maximo {SENHA_MAX_CARACTERES} caracteres."
        )
    return erros


def _verificar_senha(senha: str, hash_armazenado: str) -> tuple[bool, bool]:
    """Retorna (senha_valida, precisa_migrar_hash_legado)."""
    if not isinstance(senha, str) or not isinstance(hash_armazenado, str):
        return False, False

    if hash_armazenado.startswith("pbkdf2_sha256$"):
        try:
            _, iteracoes, salt, esperado = hash_armazenado.split("$", 3)
            derivado = hashlib.pbkdf2_hmac(
                "sha256",
                senha.encode("utf-8"),
                bytes.fromhex(salt),
                int(iteracoes),
            ).hex()
            return hmac.compare_digest(derivado, esperado), False
        except (TypeError, ValueError):
            return False, False

    if HASH_SHA256_RE.fullmatch(hash_armazenado):
        legado = hashlib.sha256(senha.encode("utf-8")).hexdigest()
        valido = hmac.compare_digest(legado, hash_armazenado)
        return valido, valido

    return False, False


def slugify(texto: str) -> str:
    t = texto.lower().strip()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")[:40]


def _validar_slug(slug: str) -> str:
    slug = str(slug or "").strip().lower()
    if not SLUG_RE.fullmatch(slug):
        raise ValueError("Slug invalido. Use apenas letras minusculas, numeros e hifens.")
    return slug


def _validar_logo(dados, extensao) -> tuple[bytes, str]:
    ext = str(extensao or "").strip().lower().replace(".", "")
    if ext not in EXTENSOES_LOGO_PERMITIDAS:
        raise ValueError("Formato de logo nao permitido.")
    if not isinstance(dados, (bytes, bytearray, memoryview)):
        raise TypeError("Os dados do logo devem estar em formato binario.")
    dados = bytes(dados)
    if not dados or len(dados) > TAMANHO_MAXIMO_LOGO:
        raise ValueError("O logo deve possuir entre 1 byte e 5 MB.")
    assinatura_valida = (
        (ext == "png" and dados.startswith(b"\x89PNG\r\n\x1a\n"))
        or (ext in {"jpg", "jpeg"} and dados.startswith(b"\xff\xd8\xff"))
        or (ext == "webp" and dados.startswith(b"RIFF") and dados[8:12] == b"WEBP")
    )
    if not assinatura_valida:
        raise ValueError("O conteudo do logo nao corresponde ao formato informado.")
    return dados, ext


def sanitizar(texto: str) -> str:
    t = str(texto).strip()
    if t.startswith(("=", "+", "-", "@")):
        return "'" + t
    return t


def _fazer_backup(db_path: Path):
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = BACKUP_DIR / f"{db_path.stem}_{ts}.db"
    if db_path.exists():
        shutil.copy2(db_path, destino)
    backups = sorted(BACKUP_DIR.glob(f"{db_path.stem}_*.db"))
    for antigo in backups[:-20]:
        antigo.unlink()


def salvar_logo_sistema(dados, extensao):
    dados, extensao = _validar_logo(dados, extensao)
    for f in LOGOS_DIR.glob("sistema.*"):
        f.unlink()
    caminho = LOGOS_DIR / f"sistema.{extensao}"
    caminho.write_bytes(dados)
    return caminho


def obter_logo_sistema():
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = LOGOS_DIR / f"sistema.{ext}"
        if p.exists():
            return p.read_bytes(), ext
    return None


def salvar_logo_igreja(slug, dados, extensao):
    slug = _validar_slug(slug)
    dados, extensao = _validar_logo(dados, extensao)
    for f in LOGOS_DIR.glob(f"{slug}.*"):
        if f.stem.startswith("sidebar_"):
            continue
        f.unlink()
    caminho = LOGOS_DIR / f"{slug}.{extensao}"
    caminho.write_bytes(dados)
    return caminho


def obter_logo_igreja(slug):
    slug = _validar_slug(slug)
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = LOGOS_DIR / f"{slug}.{ext}"
        if p.exists():
            return p.read_bytes(), ext
    return None


def salvar_logo_sidebar_sistema(dados, extensao):
    dados, extensao = _validar_logo(dados, extensao)
    for f in LOGOS_DIR.glob("sidebar_sistema.*"):
        f.unlink()
    caminho = LOGOS_DIR / f"sidebar_sistema.{extensao}"
    caminho.write_bytes(dados)
    return caminho


def obter_logo_sidebar_sistema():
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = LOGOS_DIR / f"sidebar_sistema.{ext}"
        if p.exists():
            return p.read_bytes(), ext
    return None


def salvar_logo_sidebar_igreja(slug, dados, extensao):
    slug = _validar_slug(slug)
    dados, extensao = _validar_logo(dados, extensao)
    for f in LOGOS_DIR.glob(f"sidebar_{slug}.*"):
        f.unlink()
    caminho = LOGOS_DIR / f"sidebar_{slug}.{extensao}"
    caminho.write_bytes(dados)
    return caminho


def obter_logo_sidebar_igreja(slug):
    slug = _validar_slug(slug)
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = LOGOS_DIR / f"sidebar_{slug}.{ext}"
        if p.exists():
            return p.read_bytes(), ext
    return None


@contextmanager
def _conn(db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(db_path),
        detect_types=sqlite3.PARSE_DECLTYPES,
        timeout=30,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row

    try:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            try:
                conn.execute("PRAGMA journal_mode=DELETE")
            except sqlite3.OperationalError:
                pass

        conn.execute("PRAGMA foreign_keys=ON")

        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _tenant_db(slug):
    slug = _validar_slug(slug)
    return TENANTS_DIR / f"{slug}.db"


def inicializar_master():
    with _conn(MASTER_DB) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS igrejas (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                nome         TEXT NOT NULL,
                slug         TEXT NOT NULL UNIQUE,
                email_admin  TEXT NOT NULL,
                senha_hash   TEXT NOT NULL,
                plano        TEXT DEFAULT 'basico',
                ativa        INTEGER DEFAULT 1,
                criada_em    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS super_admin (
                id         INTEGER PRIMARY KEY,
                usuario    TEXT NOT NULL,
                senha_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ministerios (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                nome       TEXT NOT NULL,
                slug       TEXT NOT NULL UNIQUE,
                ativo      INTEGER NOT NULL DEFAULT 1,
                criado_em  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS ministerio_igrejas (
                ministerio_id INTEGER NOT NULL REFERENCES ministerios(id) ON DELETE CASCADE,
                igreja_id     INTEGER NOT NULL REFERENCES igrejas(id) ON DELETE CASCADE,
                tipo_unidade  TEXT NOT NULL DEFAULT 'congregacao',
                vinculada_em  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (ministerio_id, igreja_id)
            );
        """)
        _garantir_ministerio_padrao(conn)
        existe = conn.execute("SELECT 1 FROM super_admin LIMIT 1").fetchone()
        if not existe:
            senha_inicial = os.environ.get("FIELMORDOMO_MASTER_PASSWORD")
            if not senha_inicial:
                senha_inicial = secrets.token_urlsafe(18)
                LOGGER.warning(
                    "Super admin criado. Usuario: admin. Senha inicial temporaria: %s",
                    senha_inicial,
                )
            conn.execute(
                "INSERT INTO super_admin (usuario, senha_hash) VALUES (?, ?)",
                ("admin", hash_senha(senha_inicial)),
            )


def _garantir_ministerio_padrao(conn):
    conn.execute(
        """INSERT OR IGNORE INTO ministerios (nome, slug, ativo)
           VALUES (?, ?, 1)""",
        ("Ministerio Principal", MINISTERIO_PADRAO_SLUG),
    )
    ministerio = conn.execute(
        "SELECT id FROM ministerios WHERE slug=?", (MINISTERIO_PADRAO_SLUG,)
    ).fetchone()
    conn.execute(
        """INSERT OR IGNORE INTO ministerio_igrejas
           (ministerio_id, igreja_id, tipo_unidade)
           SELECT ?, i.id, 'congregacao'
           FROM igrejas i
           WHERE NOT EXISTS (
               SELECT 1 FROM ministerio_igrejas mi WHERE mi.igreja_id=i.id
           )""",
        (ministerio["id"],),
    )


def inicializar_tenant(slug):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cadastros (
                id_cadastro      INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_cadastro    TEXT NOT NULL,
                nome             TEXT NOT NULL,
                funcao           TEXT DEFAULT '',
                congregacao      TEXT DEFAULT '',
                cpf              TEXT DEFAULT '',
                data_nascimento  TEXT DEFAULT '',
                sexo             TEXT DEFAULT '',
                telefone         TEXT DEFAULT '',
                logradouro       TEXT DEFAULT '',
                numero           TEXT DEFAULT '',
                bairro           TEXT DEFAULT '',
                cidade           TEXT DEFAULT '',
                cep              TEXT DEFAULT '',
                situacao         TEXT DEFAULT 'Ativo'
            );
            CREATE TABLE IF NOT EXISTS lancamentos (
                id_lancamento   INTEGER PRIMARY KEY AUTOINCREMENT,
                data            TEXT NOT NULL,
                tipo            TEXT NOT NULL,
                categoria       TEXT NOT NULL,
                subcategoria    TEXT DEFAULT '',
                id_cadastro     INTEGER REFERENCES cadastros(id_cadastro),
                nome_cadastro   TEXT DEFAULT '',
                tipo_cadastro   TEXT DEFAULT '',
                descricao       TEXT DEFAULT '',
                forma_pagamento TEXT DEFAULT 'Dinheiro',
                lote_id         TEXT DEFAULT '',
                valor           REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS config_igreja (
                chave TEXT PRIMARY KEY,
                valor TEXT
            );
            CREATE TABLE IF NOT EXISTS tesoureiros (
                id_tesoureiro INTEGER PRIMARY KEY AUTOINCREMENT,
                nome          TEXT NOT NULL,
                cpf           TEXT NOT NULL UNIQUE,
                usuario       TEXT NOT NULL DEFAULT '',
                senha_hash    TEXT NOT NULL DEFAULT '',
                telefone      TEXT DEFAULT '',
                email         TEXT DEFAULT '',
                data_inicio   TEXT DEFAULT '',
                data_fim      TEXT DEFAULT '',
                situacao      TEXT NOT NULL DEFAULT 'Ativo',
                principal     INTEGER NOT NULL DEFAULT 0,
                observacoes   TEXT DEFAULT '',
                criado_em     TEXT DEFAULT (datetime('now')),
                atualizado_em TEXT DEFAULT (datetime('now'))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tesoureiro_principal_ativo
                ON tesoureiros(principal)
                WHERE principal=1 AND situacao='Ativo';
        """)
        _garantir_tabelas_ebd(conn)


def _garantir_colunas_lancamentos(conn):
    """Adiciona colunas novas em bancos antigos sem perder dados."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(lancamentos)").fetchall()]
    for col, tipo in [
        ("subcategoria", "TEXT DEFAULT ''"),
        ("forma_pagamento", "TEXT DEFAULT 'Dinheiro'"),
        ("lote_id", "TEXT DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE lancamentos ADD COLUMN {col} {tipo}")


def _garantir_tabelas_ebd(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ebd_classes (
            id_classe           INTEGER PRIMARY KEY AUTOINCREMENT,
            nome                TEXT NOT NULL,
            faixa_etaria        TEXT DEFAULT '',
            professor_principal TEXT DEFAULT '',
            sala                TEXT DEFAULT '',
            ativa               INTEGER NOT NULL DEFAULT 1,
            observacoes         TEXT DEFAULT '',
            criado_em           TEXT DEFAULT (datetime('now')),
            atualizado_em       TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS ebd_matriculas (
            id_matricula INTEGER PRIMARY KEY AUTOINCREMENT,
            id_classe    INTEGER NOT NULL REFERENCES ebd_classes(id_classe) ON DELETE CASCADE,
            id_cadastro  INTEGER REFERENCES cadastros(id_cadastro),
            nome_aluno   TEXT NOT NULL,
            ativa        INTEGER NOT NULL DEFAULT 1,
            data_inicio  TEXT DEFAULT '',
            data_fim     TEXT DEFAULT '',
            observacoes  TEXT DEFAULT '',
            criado_em    TEXT DEFAULT (datetime('now')),
            UNIQUE(id_classe, id_cadastro)
        );
        CREATE TABLE IF NOT EXISTS ebd_aulas (
            id_aula     INTEGER PRIMARY KEY AUTOINCREMENT,
            id_classe   INTEGER NOT NULL REFERENCES ebd_classes(id_classe) ON DELETE CASCADE,
            data        TEXT NOT NULL,
            tema        TEXT DEFAULT '',
            professor   TEXT DEFAULT '',
            qtd_matriculados INTEGER NOT NULL DEFAULT 0,
            qtd_presentes    INTEGER NOT NULL DEFAULT 0,
            qtd_ausentes     INTEGER NOT NULL DEFAULT 0,
            qtd_visitantes   INTEGER NOT NULL DEFAULT 0,
            qtd_revistas INTEGER NOT NULL DEFAULT 0,
            qtd_biblias  INTEGER NOT NULL DEFAULT 0,
            qtd_harpas   INTEGER NOT NULL DEFAULT 0,
            ofertas      REAL NOT NULL DEFAULT 0,
            observacoes TEXT DEFAULT '',
            criado_em   TEXT DEFAULT (datetime('now')),
            UNIQUE(id_classe, data)
        );
        CREATE TABLE IF NOT EXISTS ebd_presencas (
            id_presenca  INTEGER PRIMARY KEY AUTOINCREMENT,
            id_aula      INTEGER NOT NULL REFERENCES ebd_aulas(id_aula) ON DELETE CASCADE,
            id_matricula INTEGER NOT NULL REFERENCES ebd_matriculas(id_matricula) ON DELETE CASCADE,
            presente     INTEGER NOT NULL DEFAULT 0,
            observacao   TEXT DEFAULT '',
            UNIQUE(id_aula, id_matricula)
        );
        CREATE TABLE IF NOT EXISTS ebd_escala_professores (
            id_escala   INTEGER PRIMARY KEY AUTOINCREMENT,
            data        TEXT NOT NULL,
            id_classe   INTEGER REFERENCES ebd_classes(id_classe),
            classe_nome TEXT DEFAULT '',
            professor   TEXT NOT NULL,
            funcao_professor TEXT DEFAULT '',
            telefone_professor TEXT DEFAULT '',
            superintendente TEXT DEFAULT '',
            telefone_superintendente TEXT DEFAULT '',
            auxiliar    TEXT DEFAULT '',
            telefone_auxiliar TEXT DEFAULT '',
            tema        TEXT DEFAULT '',
            observacoes TEXT DEFAULT '',
            criado_em   TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ebd_matriculas_classe
            ON ebd_matriculas(id_classe, ativa);
        CREATE INDEX IF NOT EXISTS idx_ebd_aulas_classe_data
            ON ebd_aulas(id_classe, data);
        CREATE INDEX IF NOT EXISTS idx_ebd_presencas_aula
            ON ebd_presencas(id_aula);
        CREATE INDEX IF NOT EXISTS idx_ebd_escala_data
            ON ebd_escala_professores(data);
        CREATE TABLE IF NOT EXISTS ebd_secretarios (
            id_secretario INTEGER PRIMARY KEY AUTOINCREMENT,
            nome          TEXT NOT NULL,
            usuario       TEXT NOT NULL UNIQUE,
            senha_hash    TEXT NOT NULL,
            perfil        TEXT NOT NULL DEFAULT 'classe',
            id_classe     INTEGER REFERENCES ebd_classes(id_classe),
            telefone      TEXT DEFAULT '',
            email         TEXT DEFAULT '',
            situacao      TEXT NOT NULL DEFAULT 'Ativo',
            observacoes   TEXT DEFAULT '',
            criado_em     TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ebd_secretarios_usuario
            ON ebd_secretarios(usuario);
    """)
    cols_escala = [
        row[1]
        for row in conn.execute("PRAGMA table_info(ebd_escala_professores)").fetchall()
    ]
    for coluna in (
        "funcao_professor",
        "telefone_professor",
        "superintendente",
        "telefone_superintendente",
        "telefone_auxiliar",
    ):
        if coluna not in cols_escala:
            conn.execute(
                f"ALTER TABLE ebd_escala_professores ADD COLUMN {coluna} TEXT DEFAULT ''"
            )
    cols_aulas = [
        row[1]
        for row in conn.execute("PRAGMA table_info(ebd_aulas)").fetchall()
    ]
    for coluna, tipo in (
        ("qtd_matriculados", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_presentes", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_ausentes", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_visitantes", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_revistas", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_biblias", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_harpas", "INTEGER NOT NULL DEFAULT 0"),
        ("ofertas", "REAL NOT NULL DEFAULT 0"),
    ):
        if coluna not in cols_aulas:
            conn.execute(f"ALTER TABLE ebd_aulas ADD COLUMN {coluna} {tipo}")


def listar_ebd_classes(slug, incluir_inativas=False):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        where = "" if incluir_inativas else "WHERE ativa=1"
        return pd.read_sql_query(
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
        return pd.read_sql_query(
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


def salvar_ebd_matricula(slug, id_classe, nome_aluno, id_cadastro=None, data_inicio="", observacoes="", id_matricula=None, ativa=True):
    nome_aluno = sanitizar(nome_aluno)
    if not nome_aluno:
        raise ValueError("Nome do aluno e obrigatorio.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    id_cadastro = int(id_cadastro) if id_cadastro else None
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        if id_cadastro:
            row = conn.execute(
                "SELECT nome FROM cadastros WHERE id_cadastro=?", (id_cadastro,)
            ).fetchone()
            if row:
                nome_aluno = sanitizar(row["nome"])
        if id_matricula:
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
            return int(id_matricula)
        cur = conn.execute(
            """INSERT INTO ebd_matriculas
               (id_classe, id_cadastro, nome_aluno, ativa, data_inicio, observacoes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                int(id_classe), id_cadastro, nome_aluno, int(bool(ativa)),
                str(data_inicio or ""), sanitizar(observacoes),
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
        return pd.read_sql_query(
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
                         a.qtd_ausentes, a.qtd_visitantes, a.qtd_revistas, a.qtd_biblias,
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
    qtd_revistas=0,
    qtd_biblias=0,
    qtd_harpas=0,
    ofertas=0,
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
        qtd_revistas = max(int(qtd_revistas or 0), 0)
        qtd_biblias = max(int(qtd_biblias or 0), 0)
        qtd_harpas = max(int(qtd_harpas or 0), 0)
        ofertas = max(float(ofertas or 0), 0.0)
    except (TypeError, ValueError) as ex:
        raise ValueError("Informe valores validos para a chamada da EBD.") from ex
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        cur = conn.execute(
            """INSERT INTO ebd_aulas
               (id_classe, data, tema, professor, qtd_matriculados, qtd_presentes,
                qtd_ausentes, qtd_visitantes, qtd_revistas, qtd_biblias,
                qtd_harpas, ofertas, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id_classe, data) DO UPDATE SET
                   tema=excluded.tema,
                   professor=excluded.professor,
                   qtd_matriculados=excluded.qtd_matriculados,
                   qtd_presentes=excluded.qtd_presentes,
                   qtd_ausentes=excluded.qtd_ausentes,
                   qtd_visitantes=excluded.qtd_visitantes,
                   qtd_revistas=excluded.qtd_revistas,
                   qtd_biblias=excluded.qtd_biblias,
                   qtd_harpas=excluded.qtd_harpas,
                   ofertas=excluded.ofertas,
                   observacoes=excluded.observacoes""",
            (
                int(id_classe), str(data), sanitizar(tema),
                sanitizar(professor), qtd_matriculados, qtd_presentes,
                qtd_ausentes, qtd_visitantes, qtd_revistas, qtd_biblias,
                qtd_harpas, ofertas, sanitizar(observacoes),
            ),
        )
        row = conn.execute(
            "SELECT id_aula FROM ebd_aulas WHERE id_classe=? AND data=?",
            (int(id_classe), str(data)),
        ).fetchone()
        id_aula = int(row["id_aula"] if row else cur.lastrowid)
        for id_matricula, presente in presencas.items():
            conn.execute(
                """INSERT INTO ebd_presencas (id_aula, id_matricula, presente)
                   VALUES (?, ?, ?)
                   ON CONFLICT(id_aula, id_matricula) DO UPDATE SET
                       presente=excluded.presente""",
                (id_aula, int(id_matricula), int(bool(presente))),
            )
        return id_aula


def carregar_ebd_presencas(slug, id_aula):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        return pd.read_sql_query(
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
        return pd.read_sql_query(
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
        return pd.read_sql_query(
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


def _normalizar_usuario_ebd(usuario):
    usuario = str(usuario or "").strip().lower()
    if not USUARIO_EBD_RE.fullmatch(usuario):
        raise ValueError("Usuario deve ter 3 a 40 caracteres, usando letras, numeros, ponto, hifen ou underline.")
    return usuario


def _validar_pin_ebd(pin):
    pin = str(pin or "").strip()
    if not re.fullmatch(r"\d{4}", pin):
        raise ValueError("O PIN do secretario da EBD deve possuir exatamente 4 digitos.")
    return pin


def listar_ebd_secretarios(slug, incluir_inativos=True):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabelas_ebd(conn)
        where = "" if incluir_inativos else "WHERE s.situacao='Ativo'"
        return pd.read_sql_query(
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
            raise ValueError("Ja existe um secretario da EBD com este usuario.")
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


def _dados_lancamento_validados(conn, l, lote_id=""):
    tipo = str(l.tipo or "").strip()
    categoria = str(l.categoria or "").strip()
    forma_pagamento = str(getattr(l, "forma_pagamento", "Dinheiro") or "Dinheiro").strip()
    subcategoria = sanitizar(getattr(l, "subcategoria", ""))
    data = l.data.isoformat() if hasattr(l.data, "isoformat") else str(l.data)
    try:
        valor = float(l.valor)
    except (TypeError, ValueError) as ex:
        raise ValueError("Valor invalido.") from ex

    if tipo not in {"Entrada", "Saida"}:
        raise ValueError("Tipo de lancamento invalido.")
    if tipo == "Entrada" and categoria not in CATEGORIAS_ENTRADA:
        raise ValueError("Categoria de entrada invalida.")
    if tipo == "Saida" and categoria != "Despesa":
        raise ValueError("Categoria de saida invalida.")
    if forma_pagamento not in FORMAS_PAGAMENTO:
        raise ValueError("Forma de pagamento invalida.")
    if not math.isfinite(valor) or valor <= 0:
        raise ValueError("Valor deve ser maior que zero e finito.")

    id_cadastro = int(l.id_cadastro) if l.id_cadastro else None
    nome_cadastro = ""
    tipo_cadastro = ""
    situacao = ""
    if id_cadastro:
        row = conn.execute(
            """SELECT nome, tipo_cadastro, situacao FROM cadastros
               WHERE id_cadastro=?""",
            (id_cadastro,),
        ).fetchone()
        if not row:
            raise ValueError("Cadastro vinculado nao encontrado.")
        nome_cadastro = sanitizar(row["nome"])
        tipo_cadastro = str(row["tipo_cadastro"] or "").strip()
        situacao = str(row["situacao"] or "").strip().upper()

    if tipo == "Entrada" and categoria == "Dizimo":
        if not id_cadastro or tipo_cadastro.upper() != "MEMBRO" or situacao != "ATIVO":
            raise ValueError("Dizimo exige um membro ativo vinculado.")

    return (
        data, tipo, categoria, subcategoria, id_cadastro, nome_cadastro,
        tipo_cadastro, sanitizar(l.descricao), forma_pagamento,
        sanitizar(lote_id), valor,
    )


def listar_igrejas():
    with _conn(MASTER_DB) as conn:
        return pd.read_sql_query(
            "SELECT id, nome, slug, email_admin, plano, ativa, criada_em FROM igrejas ORDER BY nome",
            conn,
        )


def listar_ministerios(incluir_inativos=False):
    with _conn(MASTER_DB) as conn:
        _garantir_ministerio_padrao(conn)
        where = "" if incluir_inativos else "WHERE m.ativo=1"
        return pd.read_sql_query(
            f"""SELECT m.id, m.nome, m.slug, m.ativo, m.criado_em,
                       COUNT(mi.igreja_id) AS qtd_igrejas
                FROM ministerios m
                LEFT JOIN ministerio_igrejas mi ON mi.ministerio_id=m.id
                {where}
                GROUP BY m.id, m.nome, m.slug, m.ativo, m.criado_em
                ORDER BY m.nome""",
            conn,
        )


def criar_ministerio(nome, slug=None):
    nome = sanitizar(nome)
    slug = _validar_slug(slugify(slug or nome))
    if not nome:
        raise ValueError("Nome do ministerio e obrigatorio.")
    with _conn(MASTER_DB) as conn:
        cur = conn.execute(
            "INSERT INTO ministerios (nome, slug) VALUES (?, ?)", (nome, slug)
        )
        return cur.lastrowid


def vincular_igreja_ministerio(ministerio_id, igreja_id, tipo_unidade="congregacao"):
    tipo_unidade = str(tipo_unidade or "").strip().lower()
    if tipo_unidade not in {"sede", "congregacao"}:
        raise ValueError("Tipo de unidade invalido.")
    with _conn(MASTER_DB) as conn:
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
    with _conn(MASTER_DB) as conn:
        where_ativa = "" if incluir_inativas else "AND i.ativa=1"
        return pd.read_sql_query(
            f"""SELECT i.id, i.nome, i.slug, i.email_admin, i.plano, i.ativa,
                       i.criada_em, mi.tipo_unidade
                FROM ministerio_igrejas mi
                JOIN igrejas i ON i.id=mi.igreja_id
                WHERE mi.ministerio_id=? {where_ativa}
                ORDER BY CASE WHEN mi.tipo_unidade='sede' THEN 0 ELSE 1 END, i.nome""",
            conn,
            params=(int(ministerio_id),),
        )


def buscar_igreja_por_slug(slug):
    with _conn(MASTER_DB) as conn:
        row = conn.execute("SELECT * FROM igrejas WHERE slug=? AND ativa=1", (slug,)).fetchone()
    return dict(row) if row else None


def criar_igreja(igreja):
    slug = _validar_slug(igreja.slug)
    with _conn(MASTER_DB) as conn:
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
    with _conn(MASTER_DB) as conn:
        conn.execute(
            "UPDATE igrejas SET nome=?, email_admin=?, plano=?, ativa=? WHERE id=?",
            (sanitizar(nome), sanitizar(email), plano, int(ativa), id_igreja),
        )


def redefinir_senha_igreja(id_igreja, nova_senha):
    erros = validar_nova_senha(nova_senha)
    if erros:
        raise ValueError(" ".join(erros))
    with _conn(MASTER_DB) as conn:
        conn.execute("UPDATE igrejas SET senha_hash=? WHERE id=?",
                     (hash_senha(nova_senha), id_igreja))


def excluir_igreja(id_igreja, slug):
    slug = _validar_slug(slug)
    tenant_db = _tenant_db(slug)
    _fazer_backup(MASTER_DB)
    _fazer_backup(tenant_db)
    with _conn(MASTER_DB) as conn:
        conn.execute("DELETE FROM igrejas WHERE id=?", (id_igreja,))
    for caminho in (
        tenant_db,
        Path(f"{tenant_db}-wal"),
        Path(f"{tenant_db}-shm"),
    ):
        caminho.unlink(missing_ok=True)
    for padrao in (f"{slug}.*", f"sidebar_{slug}.*"):
        for caminho in LOGOS_DIR.glob(padrao):
            caminho.unlink()


def _garantir_tabela_tentativas_login(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tentativas_login (
            chave         TEXT PRIMARY KEY,
            falhas        INTEGER NOT NULL DEFAULT 0,
            bloqueado_ate TEXT DEFAULT ''
        )
    """)


def _autenticacao_bloqueada(conn, chave: str) -> bool:
    _garantir_tabela_tentativas_login(conn)
    row = conn.execute(
        "SELECT bloqueado_ate FROM tentativas_login WHERE chave=?", (chave,)
    ).fetchone()
    return bool(row and row["bloqueado_ate"] and row["bloqueado_ate"] > datetime.datetime.utcnow().isoformat())


def _registrar_resultado_login(conn, chave: str, sucesso: bool):
    _garantir_tabela_tentativas_login(conn)
    if sucesso:
        conn.execute("DELETE FROM tentativas_login WHERE chave=?", (chave,))
        return

    row = conn.execute(
        "SELECT falhas FROM tentativas_login WHERE chave=?", (chave,)
    ).fetchone()
    falhas = (row["falhas"] if row else 0) + 1
    bloqueado_ate = ""
    if falhas >= 5:
        bloqueado_ate = (
            datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
        ).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO tentativas_login (chave, falhas, bloqueado_ate)
           VALUES (?, ?, ?)""",
        (chave, falhas, bloqueado_ate),
    )


def autenticar_super_admin(usuario, senha):
    usuario = str(usuario or "").strip()
    chave = f"admin:{usuario.lower()}"
    with _conn(MASTER_DB) as conn:
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


def autenticar_igreja(slug, senha):
    try:
        slug = _validar_slug(slug)
    except ValueError:
        return None
    chave = f"igreja:{slug}"
    with _conn(MASTER_DB) as conn:
        if _autenticacao_bloqueada(conn, chave):
            return None
        row = conn.execute(
            "SELECT * FROM igrejas WHERE slug=? AND ativa=1",
            (slug,),
        ).fetchone()
        valido, migrar = _verificar_senha(senha, row["senha_hash"] if row else "")
        _registrar_resultado_login(conn, chave, valido)
        if valido and migrar:
            conn.execute(
                "UPDATE igrejas SET senha_hash=? WHERE id=?",
                (hash_senha(senha), row["id"]),
            )
    if not row or not valido:
        return None
    return {
        chave: row[chave]
        for chave in ("id", "nome", "slug", "email_admin", "plano", "ativa", "criada_em")
    }


def alterar_senha_super_admin(usuario, nova_senha):
    erros = validar_nova_senha(nova_senha)
    if erros:
        raise ValueError(" ".join(erros))
    with _conn(MASTER_DB) as conn:
        conn.execute("UPDATE super_admin SET senha_hash=? WHERE usuario=?",
                     (hash_senha(nova_senha), usuario))


def carregar_cadastros(slug):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        df = pd.read_sql_query("SELECT * FROM cadastros ORDER BY nome", conn)
    return df


def cpf_existe(slug, cpf, id_excluir=None):
    if not cpf.strip():
        return False
    doc_limpo = "".join(c for c in cpf if c.isdigit())
    db = _tenant_db(slug)
    with _conn(db) as conn:
        if id_excluir:
            row = conn.execute(
                "SELECT 1 FROM cadastros WHERE cpf=? AND id_cadastro!=? LIMIT 1",
                (doc_limpo, id_excluir),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM cadastros WHERE cpf=? LIMIT 1", (doc_limpo,)
            ).fetchone()
    return row is not None


def _garantir_colunas_cadastros(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(cadastros)").fetchall()]
    for col, tipo in [
        ("cpf", "TEXT DEFAULT ''"),
        ("data_nascimento", "TEXT DEFAULT ''"),
        ("sexo", "TEXT DEFAULT ''"),
        ("telefone", "TEXT DEFAULT ''"),
        ("logradouro", "TEXT DEFAULT ''"),
        ("numero", "TEXT DEFAULT ''"),
        ("bairro", "TEXT DEFAULT ''"),
        ("cidade", "TEXT DEFAULT ''"),
        ("cep", "TEXT DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE cadastros ADD COLUMN {col} {tipo}")


def _limite_membros_da_igreja(slug: str):
    with _conn(MASTER_DB) as conn:
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
                data_nascimento, sexo, telefone, logradouro, numero, bairro, cidade, cep, situacao)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.tipo_cadastro, sanitizar(c.nome), sanitizar(c.funcao),
             sanitizar(c.congregacao), cpf_limpo,
             sanitizar(getattr(c, "data_nascimento", "")),
             sanitizar(getattr(c, "sexo", "")),
             sanitizar(c.telefone), sanitizar(c.logradouro),
             sanitizar(c.numero), sanitizar(c.bairro),
             sanitizar(c.cidade), cep_limpo, c.situacao),
        )
        return cur.lastrowid


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
                   bairro=?, cidade=?, cep=?, situacao=?
               WHERE id_cadastro=?""",
            (c.tipo_cadastro, sanitizar(c.nome), sanitizar(c.funcao),
             sanitizar(c.congregacao), cpf_limpo,
             sanitizar(getattr(c, "data_nascimento", "")),
             sanitizar(getattr(c, "sexo", "")),
             sanitizar(c.telefone), sanitizar(c.logradouro),
             sanitizar(c.numero), sanitizar(c.bairro),
             sanitizar(c.cidade), cep_limpo,
             c.situacao, c.id_cadastro),
        )


def excluir_cadastro(slug, id_cadastro):
    _fazer_backup(_tenant_db(slug))
    db = _tenant_db(slug)
    with _conn(db) as conn:
        conn.execute("DELETE FROM cadastros WHERE id_cadastro=?", (id_cadastro,))


def cadastro_em_uso(slug, id_cadastro):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        row = conn.execute(
            "SELECT 1 FROM lancamentos WHERE id_cadastro=? LIMIT 1", (id_cadastro,)
        ).fetchone()
    return row is not None


def _garantir_tabela_tesoureiros(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tesoureiros (
            id_tesoureiro INTEGER PRIMARY KEY AUTOINCREMENT,
            nome          TEXT NOT NULL,
            cpf           TEXT NOT NULL UNIQUE,
            usuario       TEXT NOT NULL DEFAULT '',
            senha_hash    TEXT NOT NULL DEFAULT '',
            telefone      TEXT DEFAULT '',
            email         TEXT DEFAULT '',
            data_inicio   TEXT DEFAULT '',
            data_fim      TEXT DEFAULT '',
            situacao      TEXT NOT NULL DEFAULT 'Ativo',
            principal     INTEGER NOT NULL DEFAULT 0,
            observacoes   TEXT DEFAULT '',
            criado_em     TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tesoureiro_principal_ativo
            ON tesoureiros(principal)
            WHERE principal=1 AND situacao='Ativo';
    """)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(tesoureiros)").fetchall()]
    for col, tipo in [
        ("usuario", "TEXT NOT NULL DEFAULT ''"),
        ("senha_hash", "TEXT NOT NULL DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE tesoureiros ADD COLUMN {col} {tipo}")
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_tesoureiro_usuario
           ON tesoureiros(usuario) WHERE usuario!=''"""
    )


def carregar_tesoureiros(slug):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_tesoureiros(conn)
        return pd.read_sql_query(
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


def _validar_tesoureiro(tesoureiro):
    erros = tesoureiro.validar()
    if erros:
        raise ValueError(" ".join(erros))


def _normalizar_usuario_tesoureiro(usuario):
    usuario = str(usuario or "").strip().lower()
    if not USUARIO_TESOUREIRO_RE.fullmatch(usuario):
        raise ValueError(
            "Usuario invalido. Use de 4 a 40 caracteres: letras minusculas, "
            "numeros, ponto, hifen ou sublinhado."
        )
    return usuario


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


def carregar_lancamentos(slug):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_colunas_lancamentos(conn)
        df = pd.read_sql_query(
            "SELECT * FROM lancamentos ORDER BY data DESC, id_lancamento DESC", conn
        )
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    return df


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


def _contar_membros_ativos_dashboard(cad):
    obrigatorias = {"tipo_cadastro", "situacao"}
    if cad.empty:
        return 0
    if not obrigatorias.issubset(cad.columns):
        raise ValueError("Cadastro sem colunas obrigatorias.")
    tipos = cad["tipo_cadastro"].fillna("").astype(str).str.strip().str.upper()
    situacoes = cad["situacao"].fillna("").astype(str).str.strip().str.upper()
    return int(((tipos == "MEMBRO") & (situacoes == "ATIVO")).sum())


def _df_detalhes_dashboard():
    return pd.DataFrame(columns=[
        "id_lancamento", "data", "tipo", "categoria", "subcategoria",
        "descricao", "forma_pagamento", "valor", "lote_id", "igreja_id",
        "igreja", "slug_igreja",
    ])


def _normalizar_lancamentos_dashboard(lanc):
    obrigatorias = {"id_lancamento", "data", "tipo", "categoria", "valor"}
    if lanc.empty:
        return _df_detalhes_dashboard(), 0
    if not obrigatorias.issubset(lanc.columns):
        raise ValueError("Lancamentos sem colunas obrigatorias.")

    df = lanc.copy()
    for coluna in ("subcategoria", "descricao", "forma_pagamento", "lote_id"):
        if coluna not in df.columns:
            df[coluna] = ""
    df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.normalize()
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["tipo"] = df["tipo"].fillna("").astype(str).str.strip()
    tipos_validos = df["tipo"].isin({"Entrada", "Saida"})
    validos = df["data"].notna() & df["valor"].notna() & (df["valor"] > 0) & tipos_validos
    colunas = [
        "id_lancamento", "data", "tipo", "categoria", "subcategoria",
        "descricao", "forma_pagamento", "valor", "lote_id",
    ]
    return df.loc[validos, colunas].copy(), int((~validos).sum())


def inserir_lancamento(slug, l):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_colunas_lancamentos(conn)
        dados = _dados_lancamento_validados(conn, l)
        cur = conn.execute(
            """INSERT INTO lancamentos
               (data, tipo, categoria, subcategoria, id_cadastro, nome_cadastro, tipo_cadastro,
                descricao, forma_pagamento, lote_id, valor)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            dados,
        )
        return cur.lastrowid


def inserir_lancamentos_lote(slug, lancamentos, lote_id=None):
    lancamentos = list(lancamentos)
    if not lancamentos:
        raise ValueError("O lote deve possuir ao menos um lancamento.")
    lote_id = str(lote_id or f"LOTE-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}")
    db = _tenant_db(slug)
    ids = []
    with _conn(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _garantir_colunas_lancamentos(conn)
        dados_lote = [_dados_lancamento_validados(conn, l, lote_id) for l in lancamentos]
        for dados in dados_lote:
            cur = conn.execute(
                """INSERT INTO lancamentos
                   (data, tipo, categoria, subcategoria, id_cadastro, nome_cadastro, tipo_cadastro,
                    descricao, forma_pagamento, lote_id, valor)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                dados,
            )
            ids.append(cur.lastrowid)
    return lote_id, ids


def atualizar_lancamento(slug, l):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_colunas_lancamentos(conn)
        row = conn.execute(
            "SELECT lote_id FROM lancamentos WHERE id_lancamento=?", (l.id_lancamento,)
        ).fetchone()
        if not row:
            raise ValueError("Lancamento nao encontrado.")
        dados = _dados_lancamento_validados(conn, l, row["lote_id"] or "")
        conn.execute(
            """UPDATE lancamentos SET data=?, tipo=?, categoria=?, subcategoria=?, id_cadastro=?,
               nome_cadastro=?, tipo_cadastro=?, descricao=?, forma_pagamento=?, lote_id=?, valor=?
               WHERE id_lancamento=?""",
            dados + (l.id_lancamento,),
        )


def excluir_lancamento(slug, id_lancamento):
    _fazer_backup(_tenant_db(slug))
    db = _tenant_db(slug)
    with _conn(db) as conn:
        conn.execute("DELETE FROM lancamentos WHERE id_lancamento=?", (id_lancamento,))


def _garantir_tabela_config(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_sistema (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)


def obter_config(chave: str, padrao: str = "") -> str:
    with _conn(MASTER_DB) as conn:
        _garantir_tabela_config(conn)
        row = conn.execute(
            "SELECT valor FROM config_sistema WHERE chave=?", (chave,)
        ).fetchone()
    return row["valor"] if row else padrao


def salvar_config(chave: str, valor: str):
    with _conn(MASTER_DB) as conn:
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
    with _conn(MASTER_DB) as conn:
        conn.execute(
            "UPDATE igrejas SET senha_hash=? WHERE slug=?",
            (hash_senha(nova_senha), slug),
        )
    return True


DIAS_DIZIMISTA_ATIVO_DEFAULT = 30


def _garantir_tabela_config_igreja(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_igreja (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)


def obter_config_igreja(slug: str, chave: str, padrao: str = "") -> str:
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_config_igreja(conn)
        row = conn.execute(
            "SELECT valor FROM config_igreja WHERE chave=?", (chave,)
        ).fetchone()
    return row["valor"] if row else padrao


def salvar_config_igreja(slug: str, chave: str, valor: str):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_config_igreja(conn)
        conn.execute(
            "INSERT OR REPLACE INTO config_igreja (chave, valor) VALUES (?, ?)",
            (chave, valor),
        )


CHAVE_SENHA_PASTORAL = "senha_pastoral_hash"


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
    with _conn(MASTER_DB) as conn:
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


SUBCATEGORIAS_DESPESA_PADRAO = [
    "Alimentacao",
    "Limpeza e higienizacao",
    "Construcao",
    "Reforma",
    "Manutencao",
    "Agua",
    "Energia",
    "Internet e telefone",
    "Material de escritorio",
    "Combustivel",
    "Outras despesas",
    "Assistencia Social",
    "Eventos",
    "Previdencia Privada",
    "Seguro de Vida",
    "Prebenda Pastoral",
    "Missoes",
    "Comunicacao",
    "Repasse Sede",
    "Inscrições/Congressos/Convenções",
    "Licencas",
    "Software",
    "Treinamentos",
    "Literatura",
    
]


def _garantir_tabela_subcategorias_despesa(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subcategorias_despesa (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            nome  TEXT NOT NULL UNIQUE,
            ordem INTEGER DEFAULT 0
        )
    """)


def _db_subcategorias(slug: str | None = None) -> Path:
    try:
        slug = _validar_slug(slug) if slug else ""
    except ValueError:
        LOGGER.warning("Slug invalido ao carregar subcategorias: %r", slug)
        return MASTER_DB
    if slug:
        db = _tenant_db(slug)
        if not db.exists():
            inicializar_tenant(slug)
        return db
    return MASTER_DB


def listar_subcategorias_despesa(slug: str | None = None) -> list:
    """Retorna lista de nomes das subcategorias de despesa cadastradas."""
    with _conn(_db_subcategorias(slug)) as conn:
        _garantir_tabela_subcategorias_despesa(conn)
        qtd = conn.execute("SELECT COUNT(*) AS n FROM subcategorias_despesa").fetchone()["n"]
        if qtd == 0:
            for i, nome in enumerate(SUBCATEGORIAS_DESPESA_PADRAO):
                conn.execute(
                    "INSERT OR IGNORE INTO subcategorias_despesa (nome, ordem) VALUES (?, ?)",
                    (nome, i),
                )
        # Ordenacao alfabetica case-insensitive (ignora maiusculas/minusculas)
        rows = conn.execute(
            "SELECT nome FROM subcategorias_despesa ORDER BY LOWER(nome)"
        ).fetchall()
    return [r["nome"] for r in rows]


def adicionar_subcategoria_despesa(nome: str, slug: str | None = None) -> bool:
    nome = sanitizar(nome).strip()
    if not nome:
        return False
    with _conn(_db_subcategorias(slug)) as conn:
        _garantir_tabela_subcategorias_despesa(conn)
        try:
            conn.execute(
                "INSERT INTO subcategorias_despesa (nome, ordem) VALUES (?, "
                "(SELECT COALESCE(MAX(ordem),0)+1 FROM subcategorias_despesa))",
                (nome,),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def excluir_subcategoria_despesa(nome: str, slug: str | None = None):
    with _conn(_db_subcategorias(slug)) as conn:
        _garantir_tabela_subcategorias_despesa(conn)
        conn.execute("DELETE FROM subcategorias_despesa WHERE nome=?", (nome,))


def _substituir_banco_validado(destino: Path, dados: bytes, tabelas_obrigatorias: set[str]):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destino.parent, prefix=f".{destino.stem}_", suffix=".db", delete=False
        ) as arquivo:
            arquivo.write(dados)
            temporario = Path(arquivo.name)

        try:
            with closing(sqlite3.connect(str(temporario))) as conn:
                integridade = conn.execute("PRAGMA integrity_check").fetchone()[0]
                if integridade != "ok":
                    raise ValueError("Banco SQLite corrompido.")
                tabelas = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if not tabelas_obrigatorias.issubset(tabelas):
                    raise ValueError("Banco SQLite nao possui as tabelas obrigatorias.")
        except sqlite3.DatabaseError as ex:
            raise ValueError("Arquivo SQLite invalido ou corrompido.") from ex

        for auxiliar in (Path(f"{destino}-wal"), Path(f"{destino}-shm")):
            auxiliar.unlink(missing_ok=True)
        os.replace(temporario, destino)
        temporario = None
    finally:
        if temporario:
            temporario.unlink(missing_ok=True)


def _copia_consistente_sqlite(db_path: Path) -> bytes:
    """Cria snapshot SQLite consistente mesmo quando o banco usa WAL."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise ValueError("Banco de dados da igreja nao encontrado.")
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=db_path.parent, prefix=f".{db_path.stem}_backup_", suffix=".db",
            delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
        with closing(sqlite3.connect(str(db_path))) as origem:
            with closing(sqlite3.connect(str(temporario))) as destino:
                origem.backup(destino)
        return temporario.read_bytes()
    finally:
        if temporario:
            temporario.unlink(missing_ok=True)


def _df_csv_seguro(df):
    seguro = df.copy()
    for coluna in seguro.select_dtypes(include=["object", "string"]).columns:
        seguro[coluna] = seguro[coluna].map(
            lambda valor: sanitizar(valor) if isinstance(valor, str) else valor
        )
    return seguro


def exportar_backup_igreja(slug) -> bytes:
    """Exporta ZIP restauravel com snapshot SQLite e CSVs para conferencia."""
    import io
    import zipfile

    slug = _validar_slug(slug)
    inicializar_tenant(slug)
    banco = _copia_consistente_sqlite(_tenant_db(slug))
    cadastros = _df_csv_seguro(carregar_cadastros(slug))
    lancamentos = _df_csv_seguro(carregar_lancamentos(slug))
    if "data" in lancamentos.columns:
        lancamentos["data"] = pd.to_datetime(
            lancamentos["data"], errors="coerce"
        ).dt.strftime("%Y-%m-%d").fillna("")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"banco_{slug}.db", banco)
        zf.writestr(
            f"cadastros_{slug}.csv",
            cadastros.to_csv(index=False).encode("utf-8-sig"),
        )
        zf.writestr(
            f"lancamentos_{slug}.csv",
            lancamentos.to_csv(index=False).encode("utf-8-sig"),
        )
    dados = buf.getvalue()
    if len(dados) > TAMANHO_MAXIMO_ZIP:
        raise ValueError("O backup excede o limite de 100 MB.")
    return dados


def _extrair_banco_backup_igreja(slug, dados, nome_arquivo):
    import io
    import zipfile

    if not isinstance(dados, bytes) or not dados:
        raise ValueError("Arquivo de backup vazio ou invalido.")
    nome = Path(str(nome_arquivo or "")).name.lower()
    if nome.endswith(".db"):
        if len(dados) > TAMANHO_MAXIMO_ARQUIVOS_ZIP:
            raise ValueError("O banco excede o limite de 500 MB.")
        return dados
    if not nome.endswith(".zip"):
        raise ValueError("Formato invalido. Envie um arquivo .zip ou .db.")
    if len(dados) > TAMANHO_MAXIMO_ZIP:
        raise ValueError("O ZIP deve possuir no maximo 100 MB.")

    esperado = f"banco_{slug}.db"
    try:
        with zipfile.ZipFile(io.BytesIO(dados), "r") as zf:
            infos = zf.infolist()
            if len(infos) > 20:
                raise ValueError("ZIP possui arquivos demais.")
            if sum(info.file_size for info in infos) > TAMANHO_MAXIMO_ARQUIVOS_ZIP:
                raise ValueError("Conteudo descompactado excede o limite de 500 MB.")
            nomes = zf.namelist()
            if len(nomes) != len(set(nomes)):
                raise ValueError("ZIP possui nomes de arquivo duplicados.")
            for nome_zip in nomes:
                partes = Path(nome_zip.replace("\\", "/")).parts
                if nome_zip.startswith(("/", "\\")) or ".." in partes:
                    raise ValueError("ZIP possui caminho interno invalido.")
            if esperado not in nomes:
                raise ValueError(
                    f"O ZIP nao possui o banco esperado para esta igreja: {esperado}."
                )
            banco = zf.read(esperado)
            if len(banco) > TAMANHO_MAXIMO_ARQUIVOS_ZIP:
                raise ValueError("O banco excede o limite de 500 MB.")
            return banco
    except zipfile.BadZipFile as ex:
        raise ValueError("Arquivo ZIP invalido ou corrompido.") from ex


def restaurar_backup_igreja(slug, dados, nome_arquivo):
    """Valida e restaura atomicamente somente o banco da igreja informada."""
    slug = _validar_slug(slug)
    banco = _extrair_banco_backup_igreja(slug, dados, nome_arquivo)
    destino = _tenant_db(slug)
    _fazer_backup(destino)
    _substituir_banco_validado(destino, banco, {"cadastros", "lancamentos"})
    inicializar_tenant(slug)
    with _conn(destino) as conn:
        _garantir_colunas_cadastros(conn)
        _garantir_colunas_lancamentos(conn)
        _garantir_tabela_tesoureiros(conn)
    return True


def restaurar_backup_zip(zip_bytes: bytes) -> dict:
    import io
    import zipfile

    resultado = {
        "sucesso_tenants": [],
        "master_restaurado": False,
        "logos_restaurados": 0,
        "erros": [],
        "igrejas_recriadas": [],
        "senhas_temporarias": {},
    }

    try:
        if not isinstance(zip_bytes, bytes) or len(zip_bytes) > TAMANHO_MAXIMO_ZIP:
            resultado["erros"].append("O ZIP deve possuir no maximo 100 MB.")
            return resultado

        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            infos = zf.infolist()
            if len(infos) > 500:
                resultado["erros"].append("ZIP possui arquivos demais.")
                return resultado
            if sum(info.file_size for info in infos) > TAMANHO_MAXIMO_ARQUIVOS_ZIP:
                resultado["erros"].append("Conteudo descompactado excede o limite de 500 MB.")
                return resultado

            arquivos = zf.namelist()
            if len(arquivos) != len(set(arquivos)):
                resultado["erros"].append("ZIP possui nomes de arquivo duplicados.")
                return resultado

            bancos_tenants = {}
            arquivo_master = None
            arquivos_logos = []

            for nome in arquivos:
                if nome == "master.db":
                    arquivo_master = nome
                elif nome.startswith("logos/") and not nome.endswith("/"):
                    arquivos_logos.append(nome)
                elif nome.endswith(".db") and "/banco_" in nome:
                    partes = nome.split("/")
                    if len(partes) == 2:
                        slug_zip = _validar_slug(partes[0])
                        if partes[1] != f"banco_{slug_zip}.db":
                            raise ValueError(f"Nome de banco tenant invalido: {nome}")
                        bancos_tenants[slug_zip] = nome

            if not (bancos_tenants or arquivo_master or arquivos_logos):
                resultado["erros"].append(
                    "ZIP nao contem arquivos reconheciveis. "
                    "Estrutura esperada: master.db, logos/<arquivo>, <slug>/banco_<slug>.db"
                )
                return resultado

            try:
                _fazer_backup(MASTER_DB)
            except Exception:
                pass

            slugs_existentes = set()
            try:
                with _conn(MASTER_DB) as conn:
                    rows = conn.execute("SELECT slug FROM igrejas").fetchall()
                    slugs_existentes = {r["slug"] for r in rows}
            except Exception:
                pass

            if arquivo_master:
                try:
                    dados_master = zf.read(arquivo_master)
                    _substituir_banco_validado(
                        MASTER_DB, dados_master, {"igrejas", "super_admin"}
                    )
                    resultado["master_restaurado"] = True

                    try:
                        with _conn(MASTER_DB) as conn:
                            rows = conn.execute("SELECT slug FROM igrejas").fetchall()
                            slugs_existentes = {r["slug"] for r in rows}
                    except Exception:
                        pass
                except Exception as ex:
                    resultado["erros"].append(f"master.db: {ex}")

            for caminho_logo in arquivos_logos:
                try:
                    nome_arquivo = caminho_logo.replace("logos/", "", 1)
                    if not nome_arquivo or Path(nome_arquivo).name != nome_arquivo:
                        raise ValueError("Nome de arquivo invalido.")
                    extensao = Path(nome_arquivo).suffix.replace(".", "")
                    dados_logo = zf.read(caminho_logo)
                    dados_logo, _ = _validar_logo(dados_logo, extensao)
                    destino_logo = LOGOS_DIR / nome_arquivo
                    destino_logo.write_bytes(dados_logo)
                    resultado["logos_restaurados"] += 1
                except Exception as ex:
                    resultado["erros"].append(f"logo {caminho_logo}: {ex}")

            for slug_zip, caminho_zip in bancos_tenants.items():
                try:
                    db_destino = _tenant_db(slug_zip)

                    if db_destino.exists():
                        try:
                            _fazer_backup(db_destino)
                        except Exception:
                            pass

                    dados_db = zf.read(caminho_zip)
                    _substituir_banco_validado(
                        db_destino, dados_db, {"cadastros", "lancamentos"}
                    )

                    if slug_zip not in slugs_existentes:
                        try:
                            with _conn(db_destino) as conn_t:
                                conn_t.execute("SELECT COUNT(*) FROM cadastros").fetchone()

                            with _conn(MASTER_DB) as conn_m:
                                senha_temporaria = secrets.token_urlsafe(12)
                                conn_m.execute(
                                    """INSERT INTO igrejas (nome, slug, email_admin, senha_hash, plano, ativa)
                                       VALUES (?, ?, ?, ?, ?, ?)""",
                                    (
                                        slug_zip.replace("-", " ").title(),
                                        slug_zip,
                                        f"admin@{slug_zip}.com",
                                        hash_senha(senha_temporaria),
                                        "basico",
                                        1,
                                    ),
                                )
                            resultado["igrejas_recriadas"].append(slug_zip)
                            resultado["senhas_temporarias"][slug_zip] = senha_temporaria
                        except Exception as ex_recriacao:
                            resultado["erros"].append(
                                f"{slug_zip}: banco restaurado mas erro ao recriar no master: {ex_recriacao}"
                            )

                    resultado["sucesso_tenants"].append(slug_zip)
                except Exception as ex:
                    resultado["erros"].append(f"{slug_zip}: {ex}")

    except zipfile.BadZipFile:
        resultado["erros"].append("Arquivo ZIP invalido ou corrompido.")
    except Exception as ex:
        resultado["erros"].append(f"Erro geral: {ex}")

    try:
        inicializar_master()
    except Exception as ex:
        LOGGER.exception("Falha ao migrar master.db apos restauracao.")
        resultado["erros"].append(f"Erro ao migrar master.db restaurado: {ex}")

    return resultado
