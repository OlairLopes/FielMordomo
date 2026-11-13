"""Base do repositorio: caminhos, conexoes, validacoes e funcoes compartilhadas."""
import io
import os
import re
import json
import sqlite3
import hashlib
import hmac
import logging
import math
import secrets
import shutil
import datetime
import tempfile
import unicodedata
from contextlib import closing, contextmanager
from pathlib import Path
import pandas as pd


"""
Camada de persistencia multi-tenant.
"""


LOGGER = logging.getLogger(__name__)
_PD_READ_SQL_QUERY = getattr(pd, "read_sql_query")
PBKDF2_ITERACOES = 210_000
SENHA_MIN_CARACTERES = 15
SENHA_MAX_CARACTERES = 128
# Login dos leitores do plano de leitura biblica: conta de baixa sensibilidade
# (so confirma leituras diarias, sem acesso a dados financeiros/membros), por
# isso usa uma senha minima bem mais curta que a dos perfis administrativos.
SENHA_LEITOR_MIN_CARACTERES = 6
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
    "Campanha",
    "Dizimo",
    "Missao",
    "Oferta",
    "Oferta Culto Missões",
    "Oferta Culto Jovens",
    "Oferta Culto Senhoras",
    "Oferta Culto Senhores",
    "Oferta Escola Bíblica",
    "Oferta Culto Infantil",
    "Revista EBD",
    "Saldo ano anterior",
}
FORMAS_PAGAMENTO = {
    "Pix", "Dinheiro", "Transferencia", "Boleto", "Cheque",
    "Cartao Debito", "Cartao Credito",
}
MINISTERIO_PADRAO_SLUG = "ministerio-principal"


def formatar_telefone(telefone) -> str:
    texto_original = str(telefone if telefone is not None else "").strip()
    digitos = "".join(c for c in texto_original if c.isdigit())

    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]

    while digitos.startswith("0") and len(digitos) > 11:
        digitos = digitos[1:]

    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2]} {digitos[3:7]}-{digitos[7:]}"

    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"

    return texto_original


def _formatar_colunas_telefone(df):
    if df is None or df.empty:
        return df

    for coluna in df.columns:
        nome_coluna = str(coluna).lower()
        if "telefone" in nome_coluna or "whatsapp" in nome_coluna:
            df[coluna] = df[coluna].apply(formatar_telefone)

    return df


def _read_sql_query_formatado(*args, **kwargs):
    return _formatar_colunas_telefone(_PD_READ_SQL_QUERY(*args, **kwargs))


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


def _validar_senha_leitor_biblia(senha: str) -> list[str]:
    """Validacao de senha para o login dos leitores do plano de leitura biblica
    (conta de baixa sensibilidade, senha minima mais curta que a administrativa)."""
    erros = []
    if not isinstance(senha, str):
        return ["Senha invalida."]
    if len(senha) < SENHA_LEITOR_MIN_CARACTERES:
        erros.append(
            f"A senha deve possuir ao menos {SENHA_LEITOR_MIN_CARACTERES} caracteres."
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
        _garantir_tabelas_orhafe(conn)
        _garantir_tabelas_gfc(conn)
        _garantir_tabelas_obreiros(conn)
        _garantir_tabelas_visitantes(conn)
        _garantir_tabelas_pedidos_oracao(conn)
        _garantir_tabelas_eventos(conn)
        _garantir_tabela_permissoes_usuarios(conn)
        _garantir_tabela_pastores_auxiliares(conn)
        _garantir_tabela_secretarios_gerais(conn)
        _garantir_tabela_recepcao(conn)
        _garantir_tabela_contribuicoes_online(conn)


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
            qtd_assistentes  INTEGER NOT NULL DEFAULT 0,
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
        CREATE TABLE IF NOT EXISTS ebd_professores_classe (
            id_professor_classe INTEGER PRIMARY KEY AUTOINCREMENT,
            id_classe   INTEGER REFERENCES ebd_classes(id_classe) ON DELETE CASCADE,
            funcao      TEXT NOT NULL DEFAULT 'Professor',
            nome        TEXT NOT NULL,
            telefone    TEXT DEFAULT '',
            ativo       INTEGER NOT NULL DEFAULT 1,
            ordem       INTEGER NOT NULL DEFAULT 0,
            criado_em   TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ebd_professores_classe
            ON ebd_professores_classe(id_classe, funcao, ativo);
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
        ("qtd_assistentes", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_revistas", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_biblias", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_harpas", "INTEGER NOT NULL DEFAULT 0"),
        ("ofertas", "REAL NOT NULL DEFAULT 0"),
    ):
        if coluna not in cols_aulas:
            conn.execute(f"ALTER TABLE ebd_aulas ADD COLUMN {coluna} {tipo}")


def _garantir_tabelas_orhafe(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS orhafe_coordenadoras (
            id_coordenadora INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro     INTEGER REFERENCES cadastros(id_cadastro),
            nome            TEXT NOT NULL,
            telefone        TEXT DEFAULT '',
            funcao          TEXT DEFAULT 'Coordenadora',
            ordem           INTEGER NOT NULL DEFAULT 0,
            ativa           INTEGER NOT NULL DEFAULT 1,
            observacoes     TEXT DEFAULT '',
            criado_em       TEXT DEFAULT (datetime('now')),
            atualizado_em   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS orhafe_lideres (
            id_lider    INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro INTEGER REFERENCES cadastros(id_cadastro),
            nome        TEXT NOT NULL,
            telefone    TEXT DEFAULT '',
            funcao      TEXT DEFAULT 'Lider',
            ordem       INTEGER NOT NULL DEFAULT 0,
            ativo       INTEGER NOT NULL DEFAULT 1,
            observacoes TEXT DEFAULT '',
            criado_em   TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS orhafe_matriculas (
            id_matricula INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro  INTEGER REFERENCES cadastros(id_cadastro),
            nome         TEXT NOT NULL,
            telefone     TEXT DEFAULT '',
            ativa        INTEGER NOT NULL DEFAULT 1,
            data_inicio  TEXT DEFAULT '',
            data_fim     TEXT DEFAULT '',
            observacoes  TEXT DEFAULT '',
            criado_em    TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now')),
            UNIQUE(id_cadastro)
        );
        CREATE TABLE IF NOT EXISTS orhafe_reunioes (
            id_reuniao       INTEGER PRIMARY KEY AUTOINCREMENT,
            data             TEXT NOT NULL UNIQUE,
            tema             TEXT DEFAULT '',
            id_lider         INTEGER REFERENCES orhafe_lideres(id_lider),
            lider_nome       TEXT DEFAULT '',
            qtd_matriculadas INTEGER NOT NULL DEFAULT 0,
            qtd_presentes    INTEGER NOT NULL DEFAULT 0,
            qtd_ausentes     INTEGER NOT NULL DEFAULT 0,
            qtd_visitantes   INTEGER NOT NULL DEFAULT 0,
            ofertas          REAL NOT NULL DEFAULT 0,
            observacoes      TEXT DEFAULT '',
            criado_em        TEXT DEFAULT (datetime('now')),
            atualizado_em    TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS orhafe_presencas (
            id_presenca  INTEGER PRIMARY KEY AUTOINCREMENT,
            id_reuniao   INTEGER NOT NULL REFERENCES orhafe_reunioes(id_reuniao) ON DELETE CASCADE,
            id_matricula INTEGER REFERENCES orhafe_matriculas(id_matricula) ON DELETE CASCADE,
            nome         TEXT NOT NULL,
            presente     INTEGER NOT NULL DEFAULT 0,
            visitante    INTEGER NOT NULL DEFAULT 0,
            observacao   TEXT DEFAULT '',
            UNIQUE(id_reuniao, id_matricula, nome)
        );
        CREATE INDEX IF NOT EXISTS idx_orhafe_matriculas_ativa
            ON orhafe_matriculas(ativa);
        CREATE INDEX IF NOT EXISTS idx_orhafe_reunioes_data
            ON orhafe_reunioes(data);
        CREATE INDEX IF NOT EXISTS idx_orhafe_presencas_reuniao
            ON orhafe_presencas(id_reuniao);
        CREATE TABLE IF NOT EXISTS orhafe_secretarias (
            id_secretaria INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro   INTEGER REFERENCES cadastros(id_cadastro),
            nome          TEXT NOT NULL,
            usuario       TEXT NOT NULL UNIQUE,
            senha_hash    TEXT NOT NULL,
            perfil        TEXT NOT NULL DEFAULT 'chamada',
            telefone      TEXT DEFAULT '',
            email         TEXT DEFAULT '',
            situacao      TEXT NOT NULL DEFAULT 'Ativo',
            observacoes   TEXT DEFAULT '',
            criado_em     TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_orhafe_secretarias_usuario
            ON orhafe_secretarias(usuario);
    """)
    cols_coordenadoras = [
        row[1]
        for row in conn.execute("PRAGMA table_info(orhafe_coordenadoras)").fetchall()
    ]
    if "id_cadastro" not in cols_coordenadoras:
        conn.execute(
            "ALTER TABLE orhafe_coordenadoras ADD COLUMN id_cadastro INTEGER REFERENCES cadastros(id_cadastro)"
        )
    cols_lideres = [
        row[1]
        for row in conn.execute("PRAGMA table_info(orhafe_lideres)").fetchall()
    ]
    if "id_cadastro" not in cols_lideres:
        conn.execute(
            "ALTER TABLE orhafe_lideres ADD COLUMN id_cadastro INTEGER REFERENCES cadastros(id_cadastro)"
        )
    cols_secretarias = [
        row[1]
        for row in conn.execute("PRAGMA table_info(orhafe_secretarias)").fetchall()
    ]
    if "id_cadastro" not in cols_secretarias:
        conn.execute(
            "ALTER TABLE orhafe_secretarias ADD COLUMN id_cadastro INTEGER REFERENCES cadastros(id_cadastro)"
        )


def _garantir_tabelas_gfc(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gfc_coordenadores (
            id_coordenador INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro    INTEGER REFERENCES cadastros(id_cadastro),
            nome           TEXT NOT NULL,
            telefone       TEXT DEFAULT '',
            funcao         TEXT DEFAULT 'Coordenador',
            setor          TEXT DEFAULT '',
            ordem          INTEGER NOT NULL DEFAULT 0,
            ativo          INTEGER NOT NULL DEFAULT 1,
            observacoes    TEXT DEFAULT '',
            criado_em      TEXT DEFAULT (datetime('now')),
            atualizado_em  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS gfc_lideres (
            id_lider      INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro   INTEGER REFERENCES cadastros(id_cadastro),
            nome          TEXT NOT NULL,
            telefone      TEXT DEFAULT '',
            funcao        TEXT DEFAULT 'Lider',
            setor         TEXT DEFAULT '',
            ordem         INTEGER NOT NULL DEFAULT 0,
            ativo         INTEGER NOT NULL DEFAULT 1,
            observacoes   TEXT DEFAULT '',
            criado_em     TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS gfc_grupos (
            id_grupo    INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            setor       TEXT DEFAULT '',
            responsavel TEXT DEFAULT '',
            telefone    TEXT DEFAULT '',
            ativo       INTEGER NOT NULL DEFAULT 1,
            observacoes TEXT DEFAULT '',
            criado_em   TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now')),
            UNIQUE(nome, setor)
        );
        CREATE TABLE IF NOT EXISTS gfc_matriculas (
            id_matricula INTEGER PRIMARY KEY AUTOINCREMENT,
            id_grupo     INTEGER NOT NULL REFERENCES gfc_grupos(id_grupo) ON DELETE CASCADE,
            id_cadastro  INTEGER REFERENCES cadastros(id_cadastro),
            nome         TEXT NOT NULL,
            telefone     TEXT DEFAULT '',
            ativa        INTEGER NOT NULL DEFAULT 1,
            data_inicio  TEXT DEFAULT '',
            data_fim     TEXT DEFAULT '',
            observacoes  TEXT DEFAULT '',
            criado_em    TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now')),
            UNIQUE(id_grupo, id_cadastro)
        );
        CREATE TABLE IF NOT EXISTS gfc_reunioes (
            id_reuniao       INTEGER PRIMARY KEY AUTOINCREMENT,
            data             TEXT NOT NULL,
            id_grupo         INTEGER REFERENCES gfc_grupos(id_grupo),
            grupo_nome       TEXT NOT NULL,
            setor            TEXT DEFAULT '',
            tipo_culto       TEXT NOT NULL,
            tema             TEXT DEFAULT '',
            coordenador1_nome TEXT DEFAULT '',
            coordenador2_nome TEXT DEFAULT '',
            lider_nome       TEXT DEFAULT '',
            qtd_pessoas      INTEGER NOT NULL DEFAULT 0,
            qtd_participantes INTEGER NOT NULL DEFAULT 0,
            qtd_presentes    INTEGER NOT NULL DEFAULT 0,
            qtd_ausentes     INTEGER NOT NULL DEFAULT 0,
            qtd_nao_crentes  INTEGER NOT NULL DEFAULT 0,
            qtd_conversoes   INTEGER NOT NULL DEFAULT 0,
            observacoes      TEXT DEFAULT '',
            criado_em        TEXT DEFAULT (datetime('now')),
            atualizado_em    TEXT DEFAULT (datetime('now')),
            UNIQUE(data, id_grupo, tipo_culto)
        );
        CREATE TABLE IF NOT EXISTS gfc_presencas (
            id_presenca   INTEGER PRIMARY KEY AUTOINCREMENT,
            id_reuniao    INTEGER NOT NULL REFERENCES gfc_reunioes(id_reuniao) ON DELETE CASCADE,
            id_matricula  INTEGER REFERENCES gfc_matriculas(id_matricula) ON DELETE CASCADE,
            id_cadastro   INTEGER REFERENCES cadastros(id_cadastro),
            nome          TEXT NOT NULL,
            presente      INTEGER NOT NULL DEFAULT 0,
            observacao    TEXT DEFAULT '',
            criado_em     TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now')),
            UNIQUE(id_reuniao, id_cadastro, nome)
        );
        CREATE TABLE IF NOT EXISTS gfc_secretarias (
            id_secretaria INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro   INTEGER REFERENCES cadastros(id_cadastro),
            nome          TEXT NOT NULL,
            usuario       TEXT NOT NULL UNIQUE,
            senha_hash    TEXT NOT NULL,
            perfil        TEXT NOT NULL DEFAULT 'chamada',
            telefone      TEXT DEFAULT '',
            email         TEXT DEFAULT '',
            situacao      TEXT NOT NULL DEFAULT 'Ativo',
            observacoes   TEXT DEFAULT '',
            criado_em     TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_gfc_grupos_ativo
            ON gfc_grupos(ativo);
        CREATE INDEX IF NOT EXISTS idx_gfc_matriculas_grupo
            ON gfc_matriculas(id_grupo);
        CREATE INDEX IF NOT EXISTS idx_gfc_matriculas_ativa
            ON gfc_matriculas(ativa);
        CREATE INDEX IF NOT EXISTS idx_gfc_reunioes_data
            ON gfc_reunioes(data);
        CREATE INDEX IF NOT EXISTS idx_gfc_reunioes_grupo
            ON gfc_reunioes(id_grupo);
        CREATE INDEX IF NOT EXISTS idx_gfc_presencas_reuniao
            ON gfc_presencas(id_reuniao);
        CREATE INDEX IF NOT EXISTS idx_gfc_secretarias_usuario
            ON gfc_secretarias(usuario);
        CREATE INDEX IF NOT EXISTS idx_gfc_coordenadores_ativo
            ON gfc_coordenadores(ativo);
        CREATE INDEX IF NOT EXISTS idx_gfc_lideres_ativo
            ON gfc_lideres(ativo);
    """)
    cols_coordenadores = [
        row[1]
        for row in conn.execute("PRAGMA table_info(gfc_coordenadores)").fetchall()
    ]
    if "id_cadastro" not in cols_coordenadores:
        conn.execute(
            "ALTER TABLE gfc_coordenadores ADD COLUMN id_cadastro INTEGER REFERENCES cadastros(id_cadastro)"
        )
    if "setor" not in cols_coordenadores:
        conn.execute("ALTER TABLE gfc_coordenadores ADD COLUMN setor TEXT DEFAULT ''")

    cols_lideres = [
        row[1]
        for row in conn.execute("PRAGMA table_info(gfc_lideres)").fetchall()
    ]
    if "id_cadastro" not in cols_lideres:
        conn.execute(
            "ALTER TABLE gfc_lideres ADD COLUMN id_cadastro INTEGER REFERENCES cadastros(id_cadastro)"
        )
    if "setor" not in cols_lideres:
        conn.execute("ALTER TABLE gfc_lideres ADD COLUMN setor TEXT DEFAULT ''")

    cols_secretarias = [
        row[1]
        for row in conn.execute("PRAGMA table_info(gfc_secretarias)").fetchall()
    ]
    if "id_cadastro" not in cols_secretarias:
        conn.execute(
            "ALTER TABLE gfc_secretarias ADD COLUMN id_cadastro INTEGER REFERENCES cadastros(id_cadastro)"
        )

    cols_reunioes = [
        row[1]
        for row in conn.execute("PRAGMA table_info(gfc_reunioes)").fetchall()
    ]
    for col, tipo in [
        ("coordenador1_nome", "TEXT DEFAULT ''"),
        ("coordenador2_nome", "TEXT DEFAULT ''"),
        ("lider_nome", "TEXT DEFAULT ''"),
        ("qtd_participantes", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_presentes", "INTEGER NOT NULL DEFAULT 0"),
        ("qtd_ausentes", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in cols_reunioes:
            conn.execute(f"ALTER TABLE gfc_reunioes ADD COLUMN {col} {tipo}")

    cols_presencas = [
        row[1]
        for row in conn.execute("PRAGMA table_info(gfc_presencas)").fetchall()
    ]
    if "id_matricula" not in cols_presencas:
        conn.execute(
            "ALTER TABLE gfc_presencas ADD COLUMN id_matricula INTEGER REFERENCES gfc_matriculas(id_matricula)"
        )


def _normalizar_tipo_culto_gfc(tipo):
    tipos = {
        "Culto Evangelístico",
        "Culto de Oração",
        "Culto Ação de Graças",
        "Vigília",
    }
    tipo = str(tipo or "").strip()
    if tipo not in tipos:
        raise ValueError("Selecione um tipo de culto valido para o GFC.")
    return tipo


def _normalizar_usuario_gfc(usuario):
    usuario = str(usuario or "").strip().lower()
    if not USUARIO_EBD_RE.fullmatch(usuario):
        raise ValueError("Usuario deve ter 3 a 40 caracteres, usando letras, numeros, ponto, hifen ou underline.")
    return usuario


def _validar_pin_gfc(pin):
    pin = str(pin or "").strip()
    if not re.fullmatch(r"\d{4}", pin):
        raise ValueError("O PIN da secretaria GFC deve possuir exatamente 4 digitos.")
    return pin


def _garantir_tabelas_visitantes(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS visitantes_cultos (
            id_visitante INTEGER PRIMARY KEY AUTOINCREMENT,
            data         TEXT NOT NULL,
            departamento TEXT NOT NULL DEFAULT '',
            nome_visitante TEXT NOT NULL,
            tipo_visitante TEXT NOT NULL,
            igreja_origem  TEXT DEFAULT '',
            cidade         TEXT DEFAULT '',
            estado         TEXT DEFAULT '',
            congregacao    TEXT DEFAULT '',
            denominacao    TEXT DEFAULT '',
            deseja_ser_apresentado INTEGER NOT NULL DEFAULT 0,
            deseja_oracao_final    INTEGER NOT NULL DEFAULT 0,
            observacoes    TEXT DEFAULT '',
            criado_em      TEXT DEFAULT (datetime('now')),
            atualizado_em  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_visitantes_cultos_data
            ON visitantes_cultos(data);
        CREATE INDEX IF NOT EXISTS idx_visitantes_cultos_departamento
            ON visitantes_cultos(departamento);
    """)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(visitantes_cultos)").fetchall()]
    if "congregacao" not in cols:
        conn.execute("ALTER TABLE visitantes_cultos ADD COLUMN congregacao TEXT DEFAULT ''")


def _garantir_tabelas_obreiros(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS obreiros_reunioes (
            id_reuniao      INTEGER PRIMARY KEY AUTOINCREMENT,
            data            TEXT NOT NULL UNIQUE,
            tema            TEXT DEFAULT '',
            funcoes         TEXT DEFAULT '',
            qtd_matriculados INTEGER NOT NULL DEFAULT 0,
            qtd_presentes   INTEGER NOT NULL DEFAULT 0,
            qtd_ausentes    INTEGER NOT NULL DEFAULT 0,
            qtd_visitantes  INTEGER NOT NULL DEFAULT 0,
            ofertas         REAL NOT NULL DEFAULT 0,
            observacoes     TEXT DEFAULT '',
            ata_nome        TEXT DEFAULT '',
            ata_mime        TEXT DEFAULT '',
            ata_bytes       BLOB,
            ata_enviada_em  TEXT DEFAULT '',
            criado_em       TEXT DEFAULT (datetime('now')),
            atualizado_em   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS obreiros_presencas (
            id_presenca INTEGER PRIMARY KEY AUTOINCREMENT,
            id_reuniao  INTEGER NOT NULL REFERENCES obreiros_reunioes(id_reuniao) ON DELETE CASCADE,
            id_cadastro INTEGER REFERENCES cadastros(id_cadastro),
            nome        TEXT NOT NULL,
            funcao      TEXT DEFAULT '',
            presente    INTEGER NOT NULL DEFAULT 0,
            observacao  TEXT DEFAULT '',
            UNIQUE(id_reuniao, id_cadastro, nome)
        );
        CREATE INDEX IF NOT EXISTS idx_obreiros_reunioes_data
            ON obreiros_reunioes(data);
        CREATE INDEX IF NOT EXISTS idx_obreiros_presencas_reuniao
            ON obreiros_presencas(id_reuniao);
    """)
    cols = [
        row[1]
        for row in conn.execute("PRAGMA table_info(obreiros_reunioes)").fetchall()
    ]
    for coluna, tipo in (
        ("ata_nome", "TEXT DEFAULT ''"),
        ("ata_mime", "TEXT DEFAULT ''"),
        ("ata_bytes", "BLOB"),
        ("ata_enviada_em", "TEXT DEFAULT ''"),
    ):
        if coluna not in cols:
            conn.execute(f"ALTER TABLE obreiros_reunioes ADD COLUMN {coluna} {tipo}")


def _garantir_tabelas_pedidos_oracao(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agenda_pastoral (
            id_slot      INTEGER PRIMARY KEY AUTOINCREMENT,
            data         TEXT NOT NULL,
            hora_inicio  TEXT NOT NULL,
            hora_fim     TEXT NOT NULL,
            local        TEXT DEFAULT '',
            observacoes  TEXT DEFAULT '',
            disponivel   INTEGER NOT NULL DEFAULT 1,
            id_pedido    INTEGER,
            criado_em    TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_agenda_pastoral_data
            ON agenda_pastoral(data, hora_inicio);

        CREATE TABLE IF NOT EXISTS pedidos_oracao (
            id_pedido     INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro   INTEGER REFERENCES cadastros(id_cadastro),
            congregacao   TEXT DEFAULT '',
            nome_membro   TEXT NOT NULL,
            telefone      TEXT DEFAULT '',
            tipo_pedido   TEXT NOT NULL DEFAULT 'Pedido de oracao',
            motivo_oracao TEXT DEFAULT '',
            pedido        TEXT NOT NULL,
            privacidade   TEXT NOT NULL DEFAULT 'Pastor',
            confidencial  INTEGER NOT NULL DEFAULT 1,
            deseja_visita INTEGER NOT NULL DEFAULT 0,
            id_slot       INTEGER REFERENCES agenda_pastoral(id_slot),
            status        TEXT NOT NULL DEFAULT 'Novo',
            notificacao_status TEXT DEFAULT '',
            criado_em     TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_pedidos_oracao_criado
            ON pedidos_oracao(criado_em);
        CREATE INDEX IF NOT EXISTS idx_pedidos_oracao_status
            ON pedidos_oracao(status);
    """)
    cols = [
        row[1]
        for row in conn.execute("PRAGMA table_info(pedidos_oracao)").fetchall()
    ]
    for coluna, tipo in (
        ("congregacao", "TEXT DEFAULT ''"),
        ("motivo_oracao", "TEXT DEFAULT ''"),
        ("privacidade", "TEXT NOT NULL DEFAULT 'Pastor'"),
    ):
        if coluna not in cols:
            conn.execute(f"ALTER TABLE pedidos_oracao ADD COLUMN {coluna} {tipo}")


def _garantir_tabelas_eventos(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS eventos_igreja (
            id_evento     INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo        TEXT NOT NULL,
            data          TEXT NOT NULL,
            hora_inicio   TEXT DEFAULT '',
            hora_fim      TEXT DEFAULT '',
            local         TEXT DEFAULT '',
            departamento  TEXT DEFAULT '',
            descricao     TEXT DEFAULT '',
            responsavel   TEXT DEFAULT '',
            contato       TEXT DEFAULT '',
            visibilidade  TEXT NOT NULL DEFAULT 'Publico',
            situacao      TEXT NOT NULL DEFAULT 'Programado',
            cartaz_nome    TEXT DEFAULT '',
            cartaz_mime    TEXT DEFAULT '',
            cartaz_bytes   BLOB,
            cartaz_enviado_em TEXT DEFAULT '',
            criado_em     TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_eventos_igreja_data
            ON eventos_igreja(data);
        CREATE INDEX IF NOT EXISTS idx_eventos_igreja_visibilidade
            ON eventos_igreja(visibilidade, situacao);
    """)
    cols = [
        row[1]
        for row in conn.execute("PRAGMA table_info(eventos_igreja)").fetchall()
    ]
    for coluna, tipo in (
        ("hora_inicio", "TEXT DEFAULT ''"),
        ("hora_fim", "TEXT DEFAULT ''"),
        ("local", "TEXT DEFAULT ''"),
        ("departamento", "TEXT DEFAULT ''"),
        ("descricao", "TEXT DEFAULT ''"),
        ("responsavel", "TEXT DEFAULT ''"),
        ("contato", "TEXT DEFAULT ''"),
        ("visibilidade", "TEXT NOT NULL DEFAULT 'Publico'"),
        ("situacao", "TEXT NOT NULL DEFAULT 'Programado'"),
        ("cartaz_nome", "TEXT DEFAULT ''"),
        ("cartaz_mime", "TEXT DEFAULT ''"),
        ("cartaz_bytes", "BLOB"),
        ("cartaz_enviado_em", "TEXT DEFAULT ''"),
        ("atualizado_em", "TEXT DEFAULT ''"),
    ):
        if coluna not in cols:
            conn.execute(f"ALTER TABLE eventos_igreja ADD COLUMN {coluna} {tipo}")


def _garantir_tabela_permissoes_usuarios(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS permissoes_usuarios (
            id_permissao INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_login   TEXT NOT NULL,
            id_usuario   INTEGER NOT NULL,
            modulo       TEXT NOT NULL,
            permitido    INTEGER NOT NULL DEFAULT 1,
            criado_em    TEXT DEFAULT (datetime('now')),
            UNIQUE(tipo_login, id_usuario, modulo)
        );
        CREATE INDEX IF NOT EXISTS idx_permissoes_usuarios_lookup
            ON permissoes_usuarios(tipo_login, id_usuario, permitido);
    """)


def _garantir_tabela_pastores_auxiliares(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pastores_auxiliares (
            id_pastor_auxiliar INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro        INTEGER REFERENCES cadastros(id_cadastro),
            nome               TEXT NOT NULL,
            usuario            TEXT NOT NULL UNIQUE,
            senha_hash         TEXT NOT NULL,
            telefone           TEXT DEFAULT '',
            email              TEXT DEFAULT '',
            situacao           TEXT NOT NULL DEFAULT 'Ativo',
            observacoes        TEXT DEFAULT '',
            criado_em          TEXT DEFAULT (datetime('now')),
            atualizado_em      TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_pastores_auxiliares_usuario
            ON pastores_auxiliares(usuario);
    """)
    cols = [
        row[1]
        for row in conn.execute("PRAGMA table_info(pastores_auxiliares)").fetchall()
    ]
    if "id_cadastro" not in cols:
        conn.execute(
            "ALTER TABLE pastores_auxiliares ADD COLUMN id_cadastro INTEGER REFERENCES cadastros(id_cadastro)"
        )


def _garantir_tabela_recepcao(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS recepcao_usuarios (
            id_recepcao INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro INTEGER REFERENCES cadastros(id_cadastro),
            nome        TEXT NOT NULL,
            usuario     TEXT NOT NULL UNIQUE,
            senha_hash  TEXT NOT NULL,
            telefone    TEXT DEFAULT '',
            email       TEXT DEFAULT '',
            situacao    TEXT NOT NULL DEFAULT 'Ativo',
            automatico  INTEGER NOT NULL DEFAULT 0,
            observacoes TEXT DEFAULT '',
            criado_em   TEXT DEFAULT (datetime('now')),
            atualizado_em TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_recepcao_usuarios_usuario
            ON recepcao_usuarios(usuario);
    """)
    cols = [
        row[1]
        for row in conn.execute("PRAGMA table_info(recepcao_usuarios)").fetchall()
    ]
    if "id_cadastro" not in cols:
        conn.execute(
            "ALTER TABLE recepcao_usuarios ADD COLUMN id_cadastro INTEGER REFERENCES cadastros(id_cadastro)"
        )
    if "automatico" not in cols:
        conn.execute(
            "ALTER TABLE recepcao_usuarios ADD COLUMN automatico INTEGER NOT NULL DEFAULT 0"
        )


def _garantir_tabela_secretarios_gerais(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS secretarios_gerais (
            id_secretario_geral INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cadastro         INTEGER REFERENCES cadastros(id_cadastro),
            nome                TEXT NOT NULL,
            usuario             TEXT NOT NULL UNIQUE,
            senha_hash          TEXT NOT NULL,
            telefone            TEXT DEFAULT '',
            email               TEXT DEFAULT '',
            situacao            TEXT NOT NULL DEFAULT 'Ativo',
            observacoes         TEXT DEFAULT '',
            criado_em           TEXT DEFAULT (datetime('now')),
            atualizado_em       TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_secretarios_gerais_usuario
            ON secretarios_gerais(usuario);
    """)


def _normalizar_usuario_ebd(usuario):
    usuario = str(usuario or "").strip().lower()
    if not USUARIO_EBD_RE.fullmatch(usuario):
        raise ValueError("Usuario deve ter 3 a 40 caracteres, usando letras, numeros, ponto, hifen ou underline.")
    return usuario


def _validar_pin_ebd(pin):
    pin = str(pin or "").strip()
    if not re.fullmatch(r"\d{4}", pin):
        raise ValueError("O PIN do secretario da Escola Bíblica deve possuir exatamente 4 digitos.")
    return pin


def _normalizar_usuario_orhafe(usuario):
    usuario = str(usuario or "").strip().lower()
    if not USUARIO_EBD_RE.fullmatch(usuario):
        raise ValueError("Usuario deve ter 3 a 40 caracteres, usando letras, numeros, ponto, hifen ou underline.")
    return usuario


def _validar_pin_orhafe(pin):
    pin = str(pin or "").strip()
    if not re.fullmatch(r"\d{4}", pin):
        raise ValueError("O PIN da secretária do Círculo de Oração deve possuir exatamente 4 dígitos.")
    return pin


VISIBILIDADES_EVENTO = {"Publico", "Membros", "Restrito"}
SITUACOES_EVENTO = {"Programado", "Realizado", "Cancelado"}


TABELAS_ACESSO_USUARIOS = {
    "tesoureiro": ("tesoureiros", "id_tesoureiro", "Tesoureiro"),
    "pastor_auxiliar": ("pastores_auxiliares", "id_pastor_auxiliar", "Pastor Auxiliar"),
    "secretario_geral": ("secretarios_gerais", "id_secretario_geral", "Secretario Geral"),
    "recepcao": ("recepcao_usuarios", "id_recepcao", "Recepcao"),
    "secretario_ebd": ("ebd_secretarios", "id_secretario", "Secretaria Escola Biblica"),
    "secretaria_orhafe": ("orhafe_secretarias", "id_secretaria", "Secretaria Circulo de Oracao"),
    "secretaria_gfc": ("gfc_secretarias", "id_secretaria", "Secretaria GFC"),
}
SITUACOES_ACESSO = {"Ativo", "Inativo", "Bloqueado"}
TIPOS_LOGIN_PIN = {"recepcao", "secretario_ebd", "secretaria_orhafe", "secretaria_gfc"}


def _garantir_tabelas_acesso_usuarios(conn):
    _garantir_tabela_tesoureiros(conn)
    _garantir_tabela_pastores_auxiliares(conn)
    _garantir_tabela_secretarios_gerais(conn)
    _garantir_tabela_recepcao(conn)
    _garantir_tabelas_ebd(conn)
    _garantir_tabelas_orhafe(conn)
    _garantir_tabelas_gfc(conn)
    _garantir_tabela_permissoes_usuarios(conn)


def _validar_senha_por_tipo_login(tipo_login, nova_senha):
    tipo_login = str(tipo_login or "").strip()
    nova_senha = str(nova_senha or "")

    if tipo_login in {"igreja", "admin", "tesoureiro"}:
        erros = validar_nova_senha(nova_senha)
        if erros:
            raise ValueError(" ".join(erros))
        return nova_senha

    if tipo_login == "pastor_auxiliar":
        return _validar_senha_pastor_auxiliar(nova_senha)

    if tipo_login == "secretario_geral":
        return _validar_senha_secretario_geral(nova_senha)

    if tipo_login == "recepcao":
        return _validar_pin_recepcao(nova_senha)

    if tipo_login == "secretario_ebd":
        return _validar_pin_ebd(nova_senha)

    if tipo_login == "secretaria_orhafe":
        return _validar_pin_orhafe(nova_senha)

    if tipo_login == "secretaria_gfc":
        return _validar_pin_gfc(nova_senha)

    raise ValueError("Tipo de login invalido.")


def gerar_credencial_temporaria_acesso(tipo_login):
    """
    Gera uma credencial temporaria adequada ao tipo de login.

    Perfis de PIN recebem 4 digitos. Perfis de senha recebem senha forte
    compativel com validar_nova_senha().
    """
    tipo_login = str(tipo_login or "").strip()
    if tipo_login in TIPOS_LOGIN_PIN:
        return f"{secrets.randbelow(10000):04d}"
    if tipo_login in {"igreja", "admin", "tesoureiro", "pastor_auxiliar", "secretario_geral"}:
        return secrets.token_urlsafe(18)
    raise ValueError("Tipo de login invalido.")


def _garantir_tabelas_geo_frequencia(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS geo_eventos (
            id_evento          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome               TEXT NOT NULL,
            data               TEXT NOT NULL,
            endereco           TEXT DEFAULT '',
            latitude           REAL NOT NULL DEFAULT 0,
            longitude          REAL NOT NULL DEFAULT 0,
            raio_metros        INTEGER NOT NULL DEFAULT 30,
            captura_habilitada INTEGER NOT NULL DEFAULT 0,
            ativo              INTEGER NOT NULL DEFAULT 1,
            mensagem_presentes TEXT DEFAULT '',
            mensagem_ausentes  TEXT DEFAULT '',
            observacoes        TEXT DEFAULT '',
            criado_em          TEXT DEFAULT (datetime('now')),
            atualizado_em      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS geo_presencas (
            id_presenca   INTEGER PRIMARY KEY AUTOINCREMENT,
            id_evento     INTEGER NOT NULL REFERENCES geo_eventos(id_evento) ON DELETE CASCADE,
            id_cadastro   INTEGER NOT NULL REFERENCES cadastros(id_cadastro),
            nome          TEXT NOT NULL,
            telefone      TEXT DEFAULT '',
            latitude      REAL NOT NULL DEFAULT 0,
            longitude     REAL NOT NULL DEFAULT 0,
            distancia_m   REAL NOT NULL DEFAULT 0,
            dentro_raio   INTEGER NOT NULL DEFAULT 0,
            presente      INTEGER NOT NULL DEFAULT 0,
            status        TEXT DEFAULT '',
            registrado_em TEXT DEFAULT (datetime('now')),
            UNIQUE(id_evento, id_cadastro)
        );

        CREATE INDEX IF NOT EXISTS idx_geo_eventos_data
            ON geo_eventos(data);
        CREATE INDEX IF NOT EXISTS idx_geo_presencas_evento
            ON geo_presencas(id_evento);
    """)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(geo_eventos)").fetchall()]
    if "endereco" not in cols:
        conn.execute("ALTER TABLE geo_eventos ADD COLUMN endereco TEXT DEFAULT ''")


def _normalizar_usuario_pastor_auxiliar(usuario):
    usuario = str(usuario or "").strip().lower()
    if not USUARIO_TESOUREIRO_RE.fullmatch(usuario):
        raise ValueError("Usuario deve ter 3 a 40 caracteres, usando letras, numeros, ponto, hifen ou underline.")
    return usuario


def _validar_senha_pastor_auxiliar(senha):
    senha = str(senha or "")
    if len(senha) < 8:
        raise ValueError("A senha do Pastor Auxiliar deve possuir ao menos 8 caracteres.")
    if len(senha) > SENHA_MAX_CARACTERES:
        raise ValueError(f"A senha deve possuir no maximo {SENHA_MAX_CARACTERES} caracteres.")
    return senha


def _normalizar_usuario_secretario_geral(usuario):
    usuario = str(usuario or "").strip().lower()
    if not USUARIO_TESOUREIRO_RE.fullmatch(usuario):
        raise ValueError("Usuario deve ter 3 a 40 caracteres, usando letras, numeros, ponto, hifen ou underline.")
    return usuario


def _normalizar_usuario_login_secretario_geral(usuario):
    return str(usuario or "").strip().lower()


def _validar_senha_secretario_geral(senha):
    senha = str(senha or "")
    if len(senha) < 8:
        raise ValueError("A senha do Secretario Geral deve possuir ao menos 8 caracteres.")
    if len(senha) > SENHA_MAX_CARACTERES:
        raise ValueError(f"A senha deve possuir no maximo {SENHA_MAX_CARACTERES} caracteres.")
    return senha


def _normalizar_usuario_recepcao(usuario):
    usuario = str(usuario or "").strip().lower()
    if not USUARIO_TESOUREIRO_RE.fullmatch(usuario):
        raise ValueError("Usuario deve ter 3 a 40 caracteres, usando letras, numeros, ponto, hifen ou underline.")
    return usuario


FUNCOES_RECEPCAO_AUTO = {"DIACONO", "DIACONISA", "AUXILIAR", "COOPERADORA"}


def _normalizar_texto_sem_acento(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().upper()


def _funcao_recepcao_elegivel(funcao):
    return _normalizar_texto_sem_acento(funcao) in FUNCOES_RECEPCAO_AUTO


def _validar_pin_recepcao(pin):
    pin = str(pin or "").strip()
    if not re.fullmatch(r"\d{4}", pin):
        raise ValueError("O PIN da Recepcao deve possuir exatamente 4 digitos.")
    return pin


def _pin_recepcao_por_cpf(cpf):
    cpf_limpo = "".join(c for c in str(cpf or "") if c.isdigit())
    if len(cpf_limpo) < 4:
        raise ValueError("CPF invalido para gerar PIN da Recepcao.")
    return cpf_limpo[-4:]


def _usuario_login_por_nome(nome, id_cadastro):
    texto = unicodedata.normalize("NFKD", str(nome or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", ".", texto).strip(".")
    texto = re.sub(r"\.+", ".", texto)
    if len(texto) < 3:
        texto = f"recepcao{int(id_cadastro)}"
    if len(texto) > 40:
        texto = texto[:40].strip(".")
    if len(texto) < 3:
        texto = f"recepcao{int(id_cadastro)}"
    return texto


def _usuario_recepcao_auto(conn, nome, id_cadastro):
    usuario = _usuario_login_por_nome(nome, id_cadastro)
    existente = conn.execute(
        """SELECT id_cadastro FROM recepcao_usuarios
           WHERE usuario=? AND COALESCE(id_cadastro, 0)!=?
           LIMIT 1""",
        (usuario, int(id_cadastro)),
    ).fetchone()
    if not existente:
        return usuario

    sufixo = f".{int(id_cadastro)}"
    base = usuario[: 40 - len(sufixo)].strip(".")
    usuario = f"{base}{sufixo}"
    return usuario[:40]


def _sincronizar_recepcao_cadastro_conn(conn, id_cadastro):
    _garantir_tabela_recepcao(conn)
    row = conn.execute(
        """SELECT id_cadastro, tipo_cadastro, nome, funcao, cpf, telefone, situacao
           FROM cadastros
           WHERE id_cadastro=?""",
        (int(id_cadastro),),
    ).fetchone()
    if not row:
        return
    elegivel = (
        _normalizar_texto_sem_acento(row["tipo_cadastro"]) == "MEMBRO"
        and _normalizar_texto_sem_acento(row["situacao"]) == "ATIVO"
        and _funcao_recepcao_elegivel(row["funcao"])
    )
    existente = conn.execute(
        """SELECT id_recepcao FROM recepcao_usuarios
           WHERE id_cadastro=? AND automatico=1
           LIMIT 1""",
        (int(id_cadastro),),
    ).fetchone()
    if not elegivel:
        if existente:
            conn.execute(
                """UPDATE recepcao_usuarios
                   SET situacao='Inativo', atualizado_em=datetime('now')
                   WHERE id_recepcao=?""",
                (existente["id_recepcao"],),
            )
        return

    pin = _pin_recepcao_por_cpf(row["cpf"])
    dados = (
        int(row["id_cadastro"]),
        sanitizar(row["nome"]),
        _usuario_recepcao_auto(conn, row["nome"], row["id_cadastro"]),
        hash_senha(pin),
        sanitizar(row["telefone"]),
        "Ativo",
        1,
        "Usuario automatico por funcao ministerial.",
    )
    if existente:
        conn.execute(
            """UPDATE recepcao_usuarios
               SET id_cadastro=?, nome=?, usuario=?, senha_hash=?, telefone=?,
                   situacao=?, automatico=?, observacoes=?,
                   atualizado_em=datetime('now')
               WHERE id_recepcao=?""",
            dados + (existente["id_recepcao"],),
        )
    else:
        conn.execute(
            """INSERT INTO recepcao_usuarios
               (id_cadastro, nome, usuario, senha_hash, telefone, situacao,
                automatico, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            dados,
        )


def _sincronizar_recepcao_automatica_conn(conn):
    _garantir_tabela_recepcao(conn)
    rows = conn.execute(
        """SELECT id_cadastro FROM cadastros
           WHERE UPPER(TRIM(tipo_cadastro))='MEMBRO'"""
    ).fetchall()
    for row in rows:
        _sincronizar_recepcao_cadastro_conn(conn, row["id_cadastro"])


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


def listar_ministerios(incluir_inativos=False):
    with _conn(MASTER_DB) as conn:
        _garantir_ministerio_padrao(conn)
        where = "" if incluir_inativos else "WHERE m.ativo=1"
        return _read_sql_query_formatado(
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


def buscar_igreja_por_slug(slug):
    with _conn(MASTER_DB) as conn:
        row = conn.execute("SELECT * FROM igrejas WHERE slug=? AND ativa=1", (slug,)).fetchone()
    return dict(row) if row else None


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


def carregar_cadastros(slug):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_colunas_cadastros(conn)
        df = _read_sql_query_formatado("SELECT * FROM cadastros ORDER BY nome", conn)
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
        ("estado_civil", "TEXT DEFAULT ''"),
        ("tipo_membro", "TEXT DEFAULT ''"),
        ("data_batismo_aguas", "TEXT DEFAULT ''"),
        ("data_batismo_espirito_santo", "TEXT DEFAULT ''"),
        ("telefone", "TEXT DEFAULT ''"),
        ("logradouro", "TEXT DEFAULT ''"),
        ("numero", "TEXT DEFAULT ''"),
        ("bairro", "TEXT DEFAULT ''"),
        ("cidade", "TEXT DEFAULT ''"),
        ("cep", "TEXT DEFAULT ''"),
        ("foto", "TEXT DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE cadastros ADD COLUMN {col} {tipo}")


def _garantir_tabela_pre_cadastros(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pre_cadastros_membros (
            id_pre_cadastro INTEGER PRIMARY KEY AUTOINCREMENT,
            nome            TEXT NOT NULL,
            cpf             TEXT NOT NULL,
            data_nascimento TEXT NOT NULL,
            sexo            TEXT DEFAULT '',
            estado_civil    TEXT DEFAULT '',
            tipo_membro     TEXT DEFAULT '',
            funcao          TEXT DEFAULT '',
            data_batismo_aguas TEXT DEFAULT '',
            data_batismo_espirito_santo TEXT DEFAULT '',
            telefone        TEXT DEFAULT '',
            logradouro      TEXT DEFAULT '',
            numero          TEXT DEFAULT '',
            bairro          TEXT DEFAULT '',
            cidade          TEXT DEFAULT '',
            cep             TEXT DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'Pendente',
            observacoes     TEXT DEFAULT '',
            criado_em       TEXT DEFAULT (datetime('now')),
            atualizado_em   TEXT DEFAULT (datetime('now'))
        )
    """)
    cols = [
        r[1]
        for r in conn.execute("PRAGMA table_info(pre_cadastros_membros)").fetchall()
    ]
    for col, tipo in [
        ("estado_civil", "TEXT DEFAULT ''"),
        ("tipo_membro", "TEXT DEFAULT ''"),
        ("funcao", "TEXT DEFAULT ''"),
        ("data_batismo_aguas", "TEXT DEFAULT ''"),
        ("data_batismo_espirito_santo", "TEXT DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE pre_cadastros_membros ADD COLUMN {col} {tipo}")


def localizar_cadastro_publico(slug, cpf, data_nascimento):
    slug = _validar_slug(slug)
    cpf_limpo = "".join(c for c in str(cpf or "") if c.isdigit())
    data_nascimento = str(data_nascimento or "").strip()
    if len(cpf_limpo) != 11 or not data_nascimento:
        return None
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        return None
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_colunas_cadastros(conn)
        row = conn.execute(
            """SELECT id_cadastro, tipo_cadastro, nome, funcao, congregacao, cpf,
                      data_nascimento, sexo, telefone, logradouro, numero,
                      bairro, cidade, cep, situacao, estado_civil, tipo_membro,
                      data_batismo_aguas, data_batismo_espirito_santo
               FROM cadastros
               WHERE cpf=? AND data_nascimento=? AND UPPER(TRIM(tipo_cadastro))='MEMBRO'
               LIMIT 1""",
            (cpf_limpo, data_nascimento),
        ).fetchone()
    if not row:
        return None
    dados = dict(row)
    dados["igreja_nome"] = igreja.get("nome", "")
    return dados


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


def carregar_lancamentos(slug):
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_colunas_lancamentos(conn)
        df = _read_sql_query_formatado(
            "SELECT * FROM lancamentos ORDER BY data DESC, id_lancamento DESC", conn
        )
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    return df


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


def _garantir_tabela_config(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_sistema (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)


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


PLANOS_LEITURA_BIBLICA = {
    "sbb-1-ano": {
        "nome": "Bíblia em 1 ano (SBB)",
        "arquivo": "plano_leitura_biblica_sbb.json",
    },
    "cronologico": {
        "nome": "Cronológico (ordem dos eventos)",
        "arquivo": "plano_leitura_biblica_cronologico.json",
    },
    "por-assuntos": {
        "nome": "Por assuntos",
        "arquivo": "plano_leitura_biblica_por_assuntos.json",
    },
    "por-livro": {
        "nome": "Bíblia em 1 ano (por livro)",
        "arquivo": "plano_leitura_biblica_por_livro.json",
    },
}
PLANO_LEITURA_PADRAO = "sbb-1-ano"


def _garantir_tabela_plano_leitura(conn):
    cols = [row[1] for row in conn.execute("PRAGMA table_info(plano_leitura_dias)").fetchall()]
    if cols and "plano_id" not in cols:
        # Tabela antiga (versao com um unico plano); os dados sao apenas
        # conteudo semeado a partir dos JSON, seguro recriar.
        conn.execute("DROP TABLE plano_leitura_dias")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS plano_leitura_dias (
            plano_id   TEXT NOT NULL,
            dia_numero INTEGER NOT NULL,
            passagens  TEXT NOT NULL,
            tema       TEXT DEFAULT '',
            PRIMARY KEY (plano_id, dia_numero)
        );
    """)
    for plano_id, info in PLANOS_LEITURA_BIBLICA.items():
        existe = conn.execute(
            "SELECT 1 FROM plano_leitura_dias WHERE plano_id=? LIMIT 1", (plano_id,)
        ).fetchone()
        if existe:
            continue
        caminho = Path(__file__).resolve().parent / info["arquivo"]
        if not caminho.exists():
            continue
        try:
            dias = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            LOGGER.exception("Nao foi possivel carregar o plano de leitura %s.", plano_id)
            continue
        for item in dias:
            dia_numero = int(item.get("dia", 0))
            passagens = "; ".join(
                str(p).strip() for p in item.get("passagens", []) if str(p).strip()
            )
            tema = str(item.get("tema", "") or "").strip()
            if dia_numero > 0 and passagens:
                conn.execute(
                    """INSERT OR IGNORE INTO plano_leitura_dias
                       (plano_id, dia_numero, passagens, tema) VALUES (?, ?, ?, ?)""",
                    (plano_id, dia_numero, passagens, tema),
                )


def _garantir_tabela_leitores_biblia(conn):
    cols_info = conn.execute("PRAGMA table_info(leitores_biblia)").fetchall()
    if cols_info:
        cpf_notnull = next((row[3] for row in cols_info if row[1] == "cpf"), 0)
        if cpf_notnull:
            # Tabela antiga exigia cpf/data_nascimento; leitores importados em lote
            # (sem CPF, identificados so pelo telefone) precisam desses campos
            # opcionais.
            conn.executescript("""
                ALTER TABLE leitores_biblia RENAME TO leitores_biblia_old;
                CREATE TABLE leitores_biblia (
                    id_leitor       INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome            TEXT NOT NULL,
                    cpf             TEXT,
                    data_nascimento TEXT,
                    telefone        TEXT DEFAULT '',
                    criado_em       TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(cpf, data_nascimento)
                );
                INSERT INTO leitores_biblia
                    (id_leitor, nome, cpf, data_nascimento, telefone, criado_em)
                SELECT id_leitor, nome, cpf, data_nascimento, telefone, criado_em
                FROM leitores_biblia_old;
                DROP TABLE leitores_biblia_old;
            """)
    else:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS leitores_biblia (
                id_leitor       INTEGER PRIMARY KEY AUTOINCREMENT,
                nome            TEXT NOT NULL,
                cpf             TEXT,
                data_nascimento TEXT,
                telefone        TEXT DEFAULT '',
                criado_em       TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(cpf, data_nascimento)
            );
        """)

    # Login proprio do leitor (usuario = telefone, com senha). Coluna adicionada
    # depois da criacao original da tabela, por isso o ALTER TABLE em separado.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(leitores_biblia)").fetchall()]
    if "senha_hash" not in cols:
        conn.execute("ALTER TABLE leitores_biblia ADD COLUMN senha_hash TEXT DEFAULT ''")


def _normalizar_telefone_leitor(tel):
    digitos = "".join(c for c in str(tel or "") if c.isdigit())
    while digitos.startswith("0"):
        digitos = digitos[1:]
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    return digitos


def _garantir_tabela_leitura_confirmacoes(conn):
    cols = [
        row[1]
        for row in conn.execute("PRAGMA table_info(leitura_biblica_confirmacoes)").fetchall()
    ]
    if cols and "plano_id" not in cols and "origem" in cols:
        # Tabela de uma versao anterior (um unico plano implicito). Preserva as
        # confirmacoes existentes, atribuindo-as ao plano padrao.
        conn.executescript("""
            ALTER TABLE leitura_biblica_confirmacoes
                RENAME TO leitura_biblica_confirmacoes_old;
            CREATE TABLE leitura_biblica_confirmacoes (
                id_confirmacao INTEGER PRIMARY KEY AUTOINCREMENT,
                origem         TEXT NOT NULL CHECK(origem IN ('membro', 'leitor')),
                id_pessoa      INTEGER NOT NULL,
                plano_id       TEXT NOT NULL DEFAULT 'sbb-1-ano',
                dia_numero     INTEGER NOT NULL,
                confirmado_em  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(origem, id_pessoa, plano_id, dia_numero)
            );
            INSERT INTO leitura_biblica_confirmacoes
                (origem, id_pessoa, plano_id, dia_numero, confirmado_em)
            SELECT origem, id_pessoa, 'sbb-1-ano', dia_numero, confirmado_em
            FROM leitura_biblica_confirmacoes_old;
            DROP TABLE leitura_biblica_confirmacoes_old;
        """)
        return

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leitura_biblica_confirmacoes (
            id_confirmacao INTEGER PRIMARY KEY AUTOINCREMENT,
            origem         TEXT NOT NULL CHECK(origem IN ('membro', 'leitor')),
            id_pessoa      INTEGER NOT NULL,
            plano_id       TEXT NOT NULL DEFAULT 'sbb-1-ano',
            dia_numero     INTEGER NOT NULL,
            confirmado_em  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(origem, id_pessoa, plano_id, dia_numero)
        );
    """)


def _garantir_tabela_biblia_cache(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS biblia_texto_cache (
            versao      TEXT NOT NULL,
            livro       TEXT NOT NULL,
            capitulo    INTEGER NOT NULL,
            versos_json TEXT NOT NULL,
            obtido_em   TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (versao, livro, capitulo)
        );
    """)


def obter_capitulo_biblico_cache(versao, livro_abbrev, capitulo):
    """Retorna a lista de versos em cache para (versao, livro, capitulo), ou None."""
    with _conn(MASTER_DB) as conn:
        _garantir_tabela_biblia_cache(conn)
        row = conn.execute(
            """SELECT versos_json FROM biblia_texto_cache
               WHERE versao=? AND livro=? AND capitulo=?""",
            (versao, livro_abbrev, int(capitulo)),
        ).fetchone()
    return json.loads(row["versos_json"]) if row else None


def salvar_capitulo_biblico_cache(versao, livro_abbrev, capitulo, versos):
    with _conn(MASTER_DB) as conn:
        _garantir_tabela_biblia_cache(conn)
        conn.execute(
            """INSERT OR REPLACE INTO biblia_texto_cache (versao, livro, capitulo, versos_json)
               VALUES (?, ?, ?, ?)""",
            (versao, livro_abbrev, int(capitulo), json.dumps(versos, ensure_ascii=False)),
        )


def _garantir_tabela_biblia_audio_cache(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS biblia_audio_cache (
            versao     TEXT NOT NULL,
            chave      TEXT NOT NULL,
            audio_blob BLOB NOT NULL,
            obtido_em  TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (versao, chave)
        );
    """)


def obter_audio_biblico_cache(versao, chave):
    """Retorna os bytes do audio em cache para (versao, chave), ou None."""
    with _conn(MASTER_DB) as conn:
        _garantir_tabela_biblia_audio_cache(conn)
        row = conn.execute(
            """SELECT audio_blob FROM biblia_audio_cache
               WHERE versao=? AND chave=?""",
            (versao, chave),
        ).fetchone()
    return bytes(row["audio_blob"]) if row else None


def salvar_audio_biblico_cache(versao, chave, audio_bytes):
    with _conn(MASTER_DB) as conn:
        _garantir_tabela_biblia_audio_cache(conn)
        conn.execute(
            """INSERT OR REPLACE INTO biblia_audio_cache (versao, chave, audio_blob)
               VALUES (?, ?, ?)""",
            (versao, chave, audio_bytes),
        )


# ═══════════════════════════════════════════════════════════════════════
# Contribuicao online por Pix estatico (dizimo e ofertas pela pagina publica)
# ═══════════════════════════════════════════════════════════════════════

STATUS_CONTRIBUICAO_ONLINE = ("pendente", "confirmada", "rejeitada")


COMPROVANTE_EXTENSOES = ("png", "jpg", "jpeg", "webp", "pdf")
COMPROVANTE_MAX_BYTES = 5_000_000
COMPROVANTE_RETENCAO_DIAS = 30


def _garantir_tabela_contribuicoes_online(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contribuicoes_online (
            id_contribuicao INTEGER PRIMARY KEY AUTOINCREMENT,
            criado_em       TEXT NOT NULL,
            nome_doador     TEXT DEFAULT '',
            contato         TEXT DEFAULT '',
            tipo            TEXT NOT NULL,
            valor           REAL NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pendente',
            id_lancamento   INTEGER,
            confirmado_em   TEXT DEFAULT ''
        )
    """)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(contribuicoes_online)").fetchall()]
    for col, tipo in [
        ("comprovante", "BLOB"),
        ("comprovante_nome", "TEXT DEFAULT ''"),
        ("comprovante_enviado_em", "TEXT DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE contribuicoes_online ADD COLUMN {col} {tipo}")
    limite = datetime.datetime.now() - datetime.timedelta(days=COMPROVANTE_RETENCAO_DIAS)
    conn.execute(
        """UPDATE contribuicoes_online SET comprovante=NULL, comprovante_nome='',
               comprovante_enviado_em=''
           WHERE comprovante IS NOT NULL AND comprovante_enviado_em < ?""",
        (limite.isoformat(timespec="seconds"),),
    )


def _digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def _validar_comprovante(dados: bytes, extensao: str):
    from PIL import Image

    if extensao not in COMPROVANTE_EXTENSOES:
        raise ValueError("Envie o comprovante em PNG, JPG, WEBP ou PDF.")
    if not dados:
        raise ValueError("O arquivo do comprovante está vazio.")
    if len(dados) > COMPROVANTE_MAX_BYTES:
        raise ValueError("O comprovante deve ter até 5 MB.")
    if extensao == "pdf":
        valido = dados.startswith(b"%PDF")
    else:
        try:
            Image.open(io.BytesIO(dados)).verify()
            valido = True
        except (OSError, ValueError):
            valido = False
    if not valido:
        raise ValueError("Não foi possível ler o arquivo enviado.")


def anexar_comprovante_online(slug: str, id_contribuicao: int, dados: bytes, extensao: str,
                              nome_arquivo: str, contato: str | None = None):
    """Guarda o comprovante do Pix numa contribuicao pendente.

    Com `contato`, só aceita o envio se o telefone bater com o informado na
    contribuicao (usado pela pagina publica, que nao tem login).
    """
    _validar_comprovante(dados, extensao)
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabela_contribuicoes_online(conn)
        row = conn.execute(
            "SELECT status, contato FROM contribuicoes_online WHERE id_contribuicao=?",
            (id_contribuicao,),
        ).fetchone()
        if (row is None or row["status"] != "pendente"
                or (contato is not None and _digitos(row["contato"]) != _digitos(contato))):
            raise ValueError("Não encontramos uma contribuição pendente com esses dados.")
        conn.execute(
            """UPDATE contribuicoes_online SET comprovante=?, comprovante_nome=?,
                   comprovante_enviado_em=?
               WHERE id_contribuicao=?""",
            (dados, sanitizar(nome_arquivo)[:120],
             datetime.datetime.now().isoformat(timespec="seconds"), id_contribuicao),
        )


def obter_comprovante_online(slug: str, id_contribuicao: int) -> dict | None:
    db = _tenant_db(slug)
    if not db.exists():
        return None
    with _conn(db) as conn:
        _garantir_tabela_contribuicoes_online(conn)
        row = conn.execute(
            "SELECT comprovante, comprovante_nome FROM contribuicoes_online WHERE id_contribuicao=?",
            (id_contribuicao,),
        ).fetchone()
    if row is None or row["comprovante"] is None:
        return None
    return {"dados": bytes(row["comprovante"]), "nome": row["comprovante_nome"]}


_COLUNAS_CONTRIBUICAO = """id_contribuicao, criado_em, nome_doador, contato, tipo, valor, status,
    id_lancamento, confirmado_em, comprovante_nome, comprovante_enviado_em,
    (comprovante IS NOT NULL) AS tem_comprovante"""


def listar_contribuicoes_online(slug: str, status: str | None = None) -> list[dict]:
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_contribuicoes_online(conn)
        if status:
            rows = conn.execute(
                f"SELECT {_COLUNAS_CONTRIBUICAO} FROM contribuicoes_online "
                "WHERE status=? ORDER BY id_contribuicao DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_COLUNAS_CONTRIBUICAO} FROM contribuicoes_online "
                "ORDER BY id_contribuicao DESC LIMIT 200"
            ).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════
# Documentos emitidos a membros (carteirinha, cartas e certificados) com
# codigo de verificacao. O QR Code do documento aponta para a pagina publica
# ?verificar=<slug>.<codigo>, que confirma se o documento foi emitido.
# ═══════════════════════════════════════════════════════════════════════

TIPOS_DOCUMENTO_MEMBRO = (
    "Carteirinha",
    "Carta de Recomendação",
    "Carta de Transferência",
    "Certificado de Apresentação de Crianças",
    "Certificado de Batismo",
    "Certificado de Consagração de Obreiros",
    "Certificado de Treinamento de Lideranças",
)


def _garantir_tabela_documentos_emitidos(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documentos_emitidos (
            codigo          TEXT PRIMARY KEY,
            tipo            TEXT NOT NULL,
            id_cadastro     INTEGER,
            nome_titular    TEXT DEFAULT '',
            descricao       TEXT DEFAULT '',
            emitido_em      TEXT NOT NULL
        )
    """)


# ═══════════════════════════════════════════════════════════════════════
# QR Code de Pix enviado pela igreja (imagem), exibido junto ao QR gerado
# ═══════════════════════════════════════════════════════════════════════

CONFIG_PIX_QR = "pix_qr_imagem"
PIX_QR_EXTENSOES = ("png", "jpg", "jpeg", "webp")
PIX_QR_MAX_BYTES = 2_000_000
