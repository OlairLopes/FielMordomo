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


def restaurar_backup_zip(zip_bytes: bytes) -> dict:
    import io
    import zipfile

    resultado = {
        "sucesso_tenants": [],
        "master_restaurado": False,
        "logos_restaurados": 0,
        "erros": [],
        "igrejas_recriadas": [],
    }

    try:
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            arquivos = zf.namelist()
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
                        slug_zip = partes[0]
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
                    MASTER_DB.write_bytes(dados_master)
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
                    if not nome_arquivo:
                        continue
                    dados_logo = zf.read(caminho_logo)
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
                    db_destino.write_bytes(dados_db)

                    if slug_zip not in slugs_existentes:
                        try:
                            with _conn(db_destino) as conn_t:
                                conn_t.execute("SELECT COUNT(*) FROM cadastros").fetchone()

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

                    resultado["sucesso_tenants"].append(slug_zip)
                except Exception as ex:
                    resultado["erros"].append(f"{slug_zip}: {ex}")

    except zipfile.BadZipFile:
        resultado["erros"].append("Arquivo ZIP invalido ou corrompido.")
    except Exception as ex:
        resultado["erros"].append(f"Erro geral: {ex}")

    return resultado
