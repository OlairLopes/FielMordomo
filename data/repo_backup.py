"""Dominio: backup."""
import sqlite3
import logging
import secrets
from pathlib import Path
import pandas as pd
from data import repo_base as _base
from data.repo_base import (
    LOGGER, TAMANHO_MAXIMO_ARQUIVOS_ZIP, TAMANHO_MAXIMO_ZIP, _conn, _copia_consistente_sqlite,
    _df_csv_seguro, _fazer_backup, _garantir_colunas_cadastros, _garantir_colunas_lancamentos,
    _garantir_tabela_pastores_auxiliares, _garantir_tabela_permissoes_usuarios,
    _garantir_tabela_recepcao, _garantir_tabela_secretarios_gerais, _garantir_tabela_tesoureiros,
    _garantir_tabelas_ebd, _garantir_tabelas_eventos, _garantir_tabelas_obreiros,
    _garantir_tabelas_orhafe, _garantir_tabelas_pedidos_oracao, _garantir_tabelas_visitantes,
    _substituir_banco_validado, _tenant_db, _validar_logo, _validar_slug, carregar_cadastros,
    carregar_lancamentos, hash_senha, inicializar_master, inicializar_tenant
)


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
        ).dt.strftime("%d/%m/%Y").fillna("")

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
        _garantir_tabelas_ebd(conn)
        _garantir_tabelas_orhafe(conn)
        _garantir_tabelas_obreiros(conn)
        _garantir_tabelas_visitantes(conn)
        _garantir_tabelas_pedidos_oracao(conn)
        _garantir_tabelas_eventos(conn)
        _garantir_tabela_permissoes_usuarios(conn)
        _garantir_tabela_pastores_auxiliares(conn)
        _garantir_tabela_secretarios_gerais(conn)
        _garantir_tabela_recepcao(conn)
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
                _fazer_backup(_base.MASTER_DB)
            except (OSError, sqlite3.Error):
                logging.exception("Erro ignorado silenciosamente")

            slugs_existentes = set()
            try:
                with _conn(_base.MASTER_DB) as conn:
                    rows = conn.execute("SELECT slug FROM igrejas").fetchall()
                    slugs_existentes = {r["slug"] for r in rows}
            except sqlite3.Error:
                logging.exception("Erro ignorado silenciosamente")

            if arquivo_master:
                try:
                    dados_master = zf.read(arquivo_master)
                    _substituir_banco_validado(
                        _base.MASTER_DB, dados_master, {"igrejas", "super_admin"}
                    )
                    resultado["master_restaurado"] = True

                    try:
                        with _conn(_base.MASTER_DB) as conn:
                            rows = conn.execute("SELECT slug FROM igrejas").fetchall()
                            slugs_existentes = {r["slug"] for r in rows}
                    except sqlite3.Error:
                        logging.exception("Erro ignorado silenciosamente")
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
                    destino_logo = _base.LOGOS_DIR / nome_arquivo
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
                        except (OSError, sqlite3.Error):
                            logging.exception("Erro ignorado silenciosamente")

                    dados_db = zf.read(caminho_zip)
                    _substituir_banco_validado(
                        db_destino, dados_db, {"cadastros", "lancamentos"}
                    )

                    if slug_zip not in slugs_existentes:
                        try:
                            with _conn(db_destino) as conn_t:
                                conn_t.execute("SELECT COUNT(*) FROM cadastros").fetchone()

                            with _conn(_base.MASTER_DB) as conn_m:
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
