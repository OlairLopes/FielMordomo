"""
Camada de persistencia multi-tenant.
"""

import os
import re
import sqlite3
import hashlib
import shutil
import datetime
from contextlib import contextmanager
from pathlib import Path

import pandas as pd


def _data_dir() -> Path:
    env = os.environ.get("FIELMORDOMO_DATA_DIR")
    if env:
        p = Path(env)
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        p = Path(base) / "FielMordomo"
    else:
        p = Path.home() / ".fielmordomo"
    p.mkdir(parents=True, exist_ok=True)
    return p


DATA_DIR    = _data_dir()
MASTER_DB   = DATA_DIR / "master.db"
TENANTS_DIR = DATA_DIR / "tenants"
LOGOS_DIR   = DATA_DIR / "logos"
BACKUP_DIR  = DATA_DIR / "backups"

TENANTS_DIR.mkdir(exist_ok=True)
LOGOS_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)


def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode()).hexdigest()


def slugify(texto: str) -> str:
    t = texto.lower().strip()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")[:40]


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


# ── LOGO PRINCIPAL DO SISTEMA ─────────────────────────────────────────────

def salvar_logo_sistema(dados, extensao):
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


# ── LOGO PRINCIPAL DA IGREJA ──────────────────────────────────────────────

def salvar_logo_igreja(slug, dados, extensao):
    for f in LOGOS_DIR.glob(f"{slug}.*"):
        if f.stem.startswith("sidebar_"):
            continue
        f.unlink()
    caminho = LOGOS_DIR / f"{slug}.{extensao}"
    caminho.write_bytes(dados)
    return caminho


def obter_logo_igreja(slug):
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = LOGOS_DIR / f"{slug}.{ext}"
        if p.exists():
            return p.read_bytes(), ext
    return None


# ── LOGO DA SIDEBAR (SISTEMA) ─────────────────────────────────────────────

def salvar_logo_sidebar_sistema(dados, extensao):
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


# ── LOGO DA SIDEBAR (IGREJA) ──────────────────────────────────────────────

def salvar_logo_sidebar_igreja(slug, dados, extensao):
    for f in LOGOS_DIR.glob(f"sidebar_{slug}.*"):
        f.unlink()
    caminho = LOGOS_DIR / f"sidebar_{slug}.{extensao}"
    caminho.write_bytes(dados)
    return caminho


def obter_logo_sidebar_igreja(slug):
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = LOGOS_DIR / f"sidebar_{slug}.{ext}"
        if p.exists():
            return p.read_bytes(), ext
    return None


@contextmanager
def _conn(db_path):
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _tenant_db(slug):
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
        """)
        existe = conn.execute("SELECT 1 FROM super_admin LIMIT 1").fetchone()
        if not existe:
            conn.execute(
                "INSERT INTO super_admin (usuario, senha_hash) VALUES (?, ?)",
                ("admin", hash_senha("fielmordomo2024")),
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
                valor           REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS config_igreja (
                chave TEXT PRIMARY KEY,
                valor TEXT
            );
        """)


def _garantir_colunas_lancamentos(conn):
    """Adiciona colunas novas em bancos antigos sem perder dados."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(lancamentos)").fetchall()]
    for col, tipo in [
        ("subcategoria",    "TEXT DEFAULT ''"),
        ("forma_pagamento", "TEXT DEFAULT 'Dinheiro'"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE lancamentos ADD COLUMN {col} {tipo}")


def listar_igrejas():
    with _conn(MASTER_DB) as conn:
        return pd.read_sql_query(
            "SELECT id, nome, slug, email_admin, plano, ativa, criada_em FROM igrejas ORDER BY nome",
            conn,
        )


def buscar_igreja_por_slug(slug):
    with _conn(MASTER_DB) as conn:
        row = conn.execute("SELECT * FROM igrejas WHERE slug=? AND ativa=1", (slug,)).fetchone()
    return dict(row) if row else None


def criar_igreja(igreja):
    with _conn(MASTER_DB) as conn:
        cur = conn.execute(
            """INSERT INTO igrejas (nome, slug, email_admin, senha_hash, plano)
               VALUES (?, ?, ?, ?, ?)""",
            (sanitizar(igreja.nome), igreja.slug, sanitizar(igreja.email_admin),
             igreja.senha_hash, igreja.plano),
        )
    inicializar_tenant(igreja.slug)
    return cur.lastrowid


def atualizar_igreja(id_igreja, nome, email, plano, ativa):
    with _conn(MASTER_DB) as conn:
        conn.execute(
            "UPDATE igrejas SET nome=?, email_admin=?, plano=?, ativa=? WHERE id=?",
            (sanitizar(nome), sanitizar(email), plano, int(ativa), id_igreja),
        )


def redefinir_senha_igreja(id_igreja, nova_senha):
    with _conn(MASTER_DB) as conn:
        conn.execute("UPDATE igrejas SET senha_hash=? WHERE id=?",
                     (hash_senha(nova_senha), id_igreja))


def excluir_igreja(id_igreja, slug):
    _fazer_backup(MASTER_DB)
    _fazer_backup(_tenant_db(slug))
    with _conn(MASTER_DB) as conn:
        conn.execute("DELETE FROM igrejas WHERE id=?", (id_igreja,))


def autenticar_super_admin(usuario, senha):
    with _conn(MASTER_DB) as conn:
        row = conn.execute(
            "SELECT 1 FROM super_admin WHERE usuario=? AND senha_hash=?",
            (usuario, hash_senha(senha)),
        ).fetchone()
    return row is not None


def autenticar_igreja(slug, senha):
    with _conn(MASTER_DB) as conn:
        row = conn.execute(
            "SELECT * FROM igrejas WHERE slug=? AND senha_hash=? AND ativa=1",
            (slug, hash_senha(senha)),
        ).fetchone()
    return dict(row) if row else None


def alterar_senha_super_admin(usuario, nova_senha):
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
        ("cpf",             "TEXT DEFAULT ''"),
        ("data_nascimento", "TEXT DEFAULT ''"),
        ("sexo",            "TEXT DEFAULT ''"),
        ("telefone",        "TEXT DEFAULT ''"),
        ("logradouro",      "TEXT DEFAULT ''"),
        ("numero",          "TEXT DEFAULT ''"),
        ("bairro",          "TEXT DEFAULT ''"),
        ("cidade",          "TEXT DEFAULT ''"),
        ("cep",             "TEXT DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE cadastros ADD COLUMN {col} {tipo}")


def inserir_cadastro(slug, c):
    db = _tenant_db(slug)
    cpf_limpo = "".join(d for d in c.cpf if d.isdigit()) if c.cpf else ""
    cep_limpo = "".join(d for d in c.cep if d.isdigit()) if c.cep else ""
    with _conn(db) as conn:
        _garantir_colunas_cadastros(conn)
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
        _garantir_colunas_cadastros(conn)
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
        df["data"]  = pd.to_datetime(df["data"], errors="coerce")
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    return df


def inserir_lancamento(slug, l):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_colunas_lancamentos(conn)
        cur = conn.execute(
            """INSERT INTO lancamentos
               (data, tipo, categoria, subcategoria, id_cadastro, nome_cadastro, tipo_cadastro,
                descricao, forma_pagamento, valor)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                l.data.isoformat() if hasattr(l.data, "isoformat") else str(l.data),
                l.tipo, l.categoria,
                sanitizar(getattr(l, "subcategoria", "")),
                int(l.id_cadastro) if l.id_cadastro else None,
                sanitizar(l.nome_cadastro), l.tipo_cadastro,
                sanitizar(l.descricao),
                getattr(l, "forma_pagamento", "Dinheiro"),
                float(l.valor),
            ),
        )
        return cur.lastrowid


def atualizar_lancamento(slug, l):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_colunas_lancamentos(conn)
        conn.execute(
            """UPDATE lancamentos SET data=?, tipo=?, categoria=?, subcategoria=?, id_cadastro=?,
               nome_cadastro=?, tipo_cadastro=?, descricao=?, forma_pagamento=?, valor=?
               WHERE id_lancamento=?""",
            (
                l.data.isoformat() if hasattr(l.data, "isoformat") else str(l.data),
                l.tipo, l.categoria,
                sanitizar(getattr(l, "subcategoria", "")),
                int(l.id_cadastro) if l.id_cadastro else None,
                sanitizar(l.nome_cadastro), l.tipo_cadastro,
                sanitizar(l.descricao),
                getattr(l, "forma_pagamento", "Dinheiro"),
                float(l.valor),
                l.id_lancamento,
            ),
        )


def excluir_lancamento(slug, id_lancamento):
    _fazer_backup(_tenant_db(slug))
    db = _tenant_db(slug)
    with _conn(db) as conn:
        conn.execute("DELETE FROM lancamentos WHERE id_lancamento=?", (id_lancamento,))


# ── Configuracoes gerais do sistema (master) ──────────────────────────────

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
    """Permite igreja trocar a propria senha validando a atual."""
    igreja = autenticar_igreja(slug, senha_atual)
    if not igreja:
        return False
    with _conn(MASTER_DB) as conn:
        conn.execute(
            "UPDATE igrejas SET senha_hash=? WHERE slug=?",
            (hash_senha(nova_senha), slug),
        )
    return True


# ── Configuracoes por igreja (tenant) — FASE 2 ────────────────────────────

# Default escolhido pela igreja se nao configurada
DIAS_DIZIMISTA_ATIVO_DEFAULT = 30


def _garantir_tabela_config_igreja(conn):
    """Cria tabela de configuracoes especificas da igreja no banco tenant."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_igreja (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)


def obter_config_igreja(slug: str, chave: str, padrao: str = "") -> str:
    """Le uma configuracao especifica da igreja."""
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
    """Grava uma configuracao especifica da igreja."""
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_config_igreja(conn)
        conn.execute(
            "INSERT OR REPLACE INTO config_igreja (chave, valor) VALUES (?, ?)",
            (chave, valor),
        )


# ── Subcategorias de despesa (configuradas pelo admin) ────────────────────

SUBCATEGORIAS_DESPESA_PADRAO = [
    "Alimentacao",
    "Limpeza e higienizacao",
    "Construcao",
    "Reforma",
    "Manutencao",
    "Agua e luz",
    "Internet e telefone",
    "Material de escritorio",
    "Combustivel",
    "Outras despesas",
]


def _garantir_tabela_subcategorias_despesa(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subcategorias_despesa (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            nome  TEXT NOT NULL UNIQUE,
            ordem INTEGER DEFAULT 0
        )
    """)


def listar_subcategorias_despesa() -> list:
    """Retorna lista de nomes das subcategorias de despesa cadastradas."""
    with _conn(MASTER_DB) as conn:
        _garantir_tabela_subcategorias_despesa(conn)
        qtd = conn.execute("SELECT COUNT(*) AS n FROM subcategorias_despesa").fetchone()["n"]
        if qtd == 0:
            for i, nome in enumerate(SUBCATEGORIAS_DESPESA_PADRAO):
                conn.execute(
                    "INSERT OR IGNORE INTO subcategorias_despesa (nome, ordem) VALUES (?, ?)",
                    (nome, i),
                )
        rows = conn.execute(
            "SELECT nome FROM subcategorias_despesa ORDER BY ordem, nome"
        ).fetchall()
    return [r["nome"] for r in rows]


def adicionar_subcategoria_despesa(nome: str) -> bool:
    nome = sanitizar(nome).strip()
    if not nome:
        return False
    with _conn(MASTER_DB) as conn:
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


def excluir_subcategoria_despesa(nome: str):
    with _conn(MASTER_DB) as conn:
        _garantir_tabela_subcategorias_despesa(conn)
        conn.execute("DELETE FROM subcategorias_despesa WHERE nome=?", (nome,))


# ── Restauracao de backup ─────────────────────────────────────────────────

def restaurar_backup_zip(zip_bytes: bytes) -> dict:
    """
    Restaura todas as igrejas a partir de um ZIP gerado pelo painel admin.

    Procura arquivos no padrao: <slug>/banco_<slug>.db
    Faz backup automatico dos bancos atuais antes de sobrescrever.

    Retorna dict com:
        - sucesso: lista de slugs restaurados
        - erros: lista de mensagens de erro
        - igrejas_recriadas: slugs que precisaram ser recriados no master.db
    """
    import io
    import zipfile

    resultado = {
        "sucesso": [],
        "erros": [],
        "igrejas_recriadas": [],
    }

    try:
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            arquivos = zf.namelist()

            # Identifica igrejas presentes no ZIP (<slug>/banco_<slug>.db)
            bancos_zip = {}
            for nome in arquivos:
                if nome.endswith(".db") and "/banco_" in nome:
                    partes = nome.split("/")
                    if len(partes) == 2:
                        slug_zip = partes[0]
                        bancos_zip[slug_zip] = nome

            if not bancos_zip:
                resultado["erros"].append(
                    "Nenhum arquivo de banco (.db) encontrado no ZIP. "
                    "Estrutura esperada: <slug>/banco_<slug>.db"
                )
                return resultado

            # Backup automatico do master.db antes de mexer
            try:
                _fazer_backup(MASTER_DB)
            except Exception:
                pass

            # Lista de slugs ja existentes no sistema
            slugs_existentes = set()
            try:
                with _conn(MASTER_DB) as conn:
                    rows = conn.execute("SELECT slug FROM igrejas").fetchall()
                    slugs_existentes = {r["slug"] for r in rows}
            except Exception:
                pass

            # Restaura cada banco
            for slug_zip, caminho_zip in bancos_zip.items():
                try:
                    db_destino = _tenant_db(slug_zip)

                    # Backup automatico do banco atual antes de sobrescrever
                    if db_destino.exists():
                        try:
                            _fazer_backup(db_destino)
                        except Exception:
                            pass

                    # Le os bytes do ZIP e escreve no destino
                    dados_db = zf.read(caminho_zip)
                    db_destino.write_bytes(dados_db)

                    # Verifica se a igreja existe no master.db
                    if slug_zip not in slugs_existentes:
                        try:
                            with _conn(db_destino) as conn_t:
                                conn_t.execute(
                                    "SELECT COUNT(*) FROM cadastros"
                                ).fetchone()

                            with _conn(MASTER_DB) as conn_m:
                                conn_m.execute(
                                    """INSERT INTO igrejas (nome, slug, email_admin, senha_hash, plano, ativa)
                                       VALUES (?, ?, ?, ?, ?, ?)""",
                                    (
                                        slug_zip.replace("-", " ").title(),
                                        slug_zip,
                                        f"admin@{slug_zip}.com",
                                        hash_senha("fielmordomo2024"),
                                        "basico",
                                        1,
                                    ),
                                )
                            resultado["igrejas_recriadas"].append(slug_zip)
                        except Exception as ex_recriacao:
                            resultado["erros"].append(
                                f"{slug_zip}: banco restaurado mas erro ao recriar no master: {ex_recriacao}"
                            )

                    resultado["sucesso"].append(slug_zip)

                except Exception as ex:
                    resultado["erros"].append(f"{slug_zip}: {ex}")

    except zipfile.BadZipFile:
        resultado["erros"].append("Arquivo ZIP invalido ou corrompido.")
    except Exception as ex:
        resultado["erros"].append(f"Erro geral: {ex}")

    return resultado
