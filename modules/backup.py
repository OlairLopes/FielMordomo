"""
Modulo de backup — exportacao, download, envio ao OneDrive,
upload e recuperacao de dados da igreja.
"""

import io
import zipfile
import datetime
import requests
import streamlit as st
import pandas as pd

from data.repository import (
    carregar_cadastros, carregar_lancamentos, _tenant_db,
)
from utils.helpers import slug_da_sessao, formatar_moeda
from utils.planos import tem_backup_automatico, obter_plano, proximo_plano


def _nome_arquivo(prefixo, ext, slug):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return prefixo + "_" + slug + "_" + ts + "." + ext


def _gerar_sqlite(slug):
    db_path = _tenant_db(slug)
    if db_path.exists():
        return db_path.read_bytes()
    return b""


def _obter_token_onedrive():
    tenant_id = st.secrets["onedrive"]["tenant_id"]
    client_id = st.secrets["onedrive"]["client_id"]
    client_secret = st.secrets["onedrive"]["client_secret"]

    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }

    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _enviar_backup_onedrive(nome_arquivo, dados):
    token = _obter_token_onedrive()

    user_id = st.secrets["onedrive"]["user_id"]
    pasta_destino = st.secrets["onedrive"].get("pasta_destino", "FielMordomo")

    url = (
        f"https://graph.microsoft.com/v1.0/users/{user_id}"
        f"/drive/root:/{pasta_destino}/{nome_arquivo}:/content"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/zip",
    }

    resp = requests.put(url, headers=headers, data=dados, timeout=120)
    resp.raise_for_status()

    return resp.json()


def _gerar_resumo(df_cad, df_lanc, slug):
    agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    linhas = [
        "=" * 50,
        "FIELMORDOMO - RESUMO DO BACKUP",
        "=" * 50,
        "Igreja: " + slug,
        "Data/hora: " + agora,
        "",
        "--- CADASTROS ---",
        "Total: " + str(len(df_cad)) + " registros",
    ]

    if not df_cad.empty and "tipo_cadastro" in df_cad.columns:
        membros = len(df_cad[df_cad["tipo_cadastro"].str.upper() == "MEMBRO"])
        fornecedores = len(df_cad[df_cad["tipo_cadastro"].str.upper() == "FORNECEDOR"])

        linhas.append("  Membros: " + str(membros))
        linhas.append("  Fornecedores: " + str(fornecedores))

    linhas += [
        "",
        "--- LANCAMENTOS ---",
        "Total: " + str(len(df_lanc)) + " registros",
    ]

    if not df_lanc.empty:
        df_l = df_lanc.copy()

        if "valor" in df_l.columns:
            df_l["valor"] = pd.to_numeric(df_l["valor"], errors="coerce").fillna(0)

        if "tipo" in df_l.columns:
            entradas = df_l[df_l["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
            saidas = df_l[df_l["tipo"].str.upper() == "SAIDA"]["valor"].sum()

            linhas.append("  Total entradas: " + formatar_moeda(entradas))
            linhas.append("  Total saidas:   " + formatar_moeda(saidas))
            linhas.append("  Saldo:          " + formatar_moeda(entradas - saidas))

    linhas += [
        "",
        "=" * 50,
        "FielMordomo - Sistema de Gestao Financeira",
        "=" * 50,
    ]

    return "\n".join(linhas)


def _gerar_zip_completo(slug):
    df_cad = carregar_cadastros(slug)
    df_lanc = carregar_lancamentos(slug)

    if not df_lanc.empty and "data" in df_lanc.columns:
        df_lanc = df_lanc.copy()
        df_lanc["data"] = pd.to_datetime(
            df_lanc["data"],
            errors="coerce",
        ).dt.strftime("%d/%m/%Y").fillna("")

    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "cadastros_" + slug + ".csv",
            df_cad.to_csv(index=False, encoding="utf-8-sig"),
        )

        zf.writestr(
            "lancamentos_" + slug + ".csv",
            df_lanc.to_csv(index=False, encoding="utf-8-sig"),
        )

        zf.writestr(
            "resumo_" + slug + ".txt",
            _gerar_resumo(df_cad, df_lanc, slug),
        )

        db_bytes = _gerar_sqlite(slug)

        if db_bytes:
            zf.writestr("banco_" + slug + ".db", db_bytes)

    buf.seek(0)
    return buf.read()


def _tentar_enviar_onedrive(slug, nome, dados, tipo):
    try:
        _enviar_backup_onedrive(nome, dados)
        st.session_state[f"{tipo}_onedrive_{slug}"] = True
        st.session_state[f"{tipo}_onedrive_erro_{slug}"] = ""
        return True

    except Exception as e:
        st.session_state[f"{tipo}_onedrive_{slug}"] = False
        st.session_state[f"{tipo}_onedrive_erro_{slug}"] = str(e)
        return False


def _verificar_backup_automatico(slug):
    igreja = st.session_state.get("igreja", {})
    plano = igreja.get("plano", "basico")

    if not tem_backup_automatico(plano):
        return

    agora = datetime.datetime.now()
    hoje = agora.date()

    ultimo_diario = st.session_state.get("backup_diario_" + slug)

    if ultimo_diario != hoje:
        dados = _gerar_zip_completo(slug)
        nome = _nome_arquivo("backup_diario", "zip", slug)

        st.session_state["backup_diario_" + slug] = hoje
        st.session_state["backup_diario_dados_" + slug] = dados
        st.session_state["backup_diario_nome_" + slug] = nome

        _tentar_enviar_onedrive(
            slug=slug,
            nome=nome,
            dados=dados,
            tipo="backup_diario",
        )

    semana_atual = agora.isocalendar()[1]
    ultimo_semanal = st.session_state.get("backup_semanal_" + slug)

    if ultimo_semanal != semana_atual:
        dados = _gerar_zip_completo(slug)
        nome = _nome_arquivo("backup_semanal", "zip", slug)

        st.session_state["backup_semanal_" + slug] = semana_atual
        st.session_state["backup_semanal_dados_" + slug] = dados
        st.session_state["backup_semanal_nome_" + slug] = nome

        _tentar_enviar_onedrive(
            slug=slug,
            nome=nome,
            dados=dados,
            tipo="backup_semanal",
        )


def _extrair_sqlite_do_zip(dados_zip, slug):
    try:
        with zipfile.ZipFile(io.BytesIO(dados_zip), "r") as zf:
            arquivos = zf.namelist()
            nome_esperado = "banco_" + slug + ".db"

            if nome_esperado in arquivos:
                return zf.read(nome_esperado)

            for nome in arquivos:
                if nome.endswith(".db"):
                    return zf.read(nome)

        return b""

    except Exception:
        return b""


def _obter_ultimo_backup_para_restaurar(slug):
    opcoes = []

    if st.session_state.get("backup_manual_completo"):
        opcoes.append({
            "tipo": "Backup completo manual",
            "nome": st.session_state.get(
                "backup_manual_completo_nome",
                "backup_completo.zip",
            ),
            "dados": st.session_state.get("backup_manual_completo"),
            "formato": "zip",
            "prioridade": 4,
        })

    if st.session_state.get("backup_diario_dados_" + slug):
        opcoes.append({
            "tipo": "Backup diario automatico",
            "nome": st.session_state.get(
                "backup_diario_nome_" + slug,
                "backup_diario.zip",
            ),
            "dados": st.session_state.get("backup_diario_dados_" + slug),
            "formato": "zip",
            "prioridade": 3,
        })

    if st.session_state.get("backup_semanal_dados_" + slug):
        opcoes.append({
            "tipo": "Backup semanal automatico",
            "nome": st.session_state.get(
                "backup_semanal_nome_" + slug,
                "backup_semanal.zip",
            ),
            "dados": st.session_state.get("backup_semanal_dados_" + slug),
            "formato": "zip",
            "prioridade": 2,
        })

    if st.session_state.get("backup_manual_db"):
        opcoes.append({
            "tipo": "SQLite manual",
            "nome": st.session_state.get(
                "backup_manual_db_nome",
                "banco.db",
            ),
            "dados": st.session_state.get("backup_manual_db"),
            "formato": "db",
            "prioridade": 1,
        })

    if not opcoes:
        return None

    return sorted(opcoes, key=lambda x: x["prioridade"], reverse=True)[0]


def _recuperar_pelo_ultimo_backup(slug):
    backup = _obter_ultimo_backup_para_restaurar(slug)

    if not backup:
        return False, "Nenhum backup disponivel para recuperacao."

    try:
        db_path = _tenant_db(slug)

        if backup["formato"] == "zip":
            db_bytes = _extrair_sqlite_do_zip(backup["dados"], slug)
        else:
            db_bytes = backup["dados"]

        if not db_bytes:
            return False, "O backup selecionado nao possui banco SQLite valido."

        if db_path.exists():
            nome_seguro = _nome_arquivo("backup_antes_restauracao", "db", slug)
            db_seguro = db_path.with_name(nome_seguro)
            db_seguro.write_bytes(db_path.read_bytes())

        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(db_bytes)

        return True, (
            "Sistema recuperado com sucesso a partir de: "
            + backup["tipo"]
            + " — "
            + backup["nome"]
        )

    except Exception as e:
        return False, "Erro ao recuperar o sistema: " + str(e)


def _validar_e_obter_db_do_upload(arquivo, slug):
    if arquivo is None:
        return False, b"", "Nenhum arquivo enviado."

    nome = arquivo.name.lower()
    dados = arquivo.read()

    if nome.endswith(".db"):
        return True, dados, "Arquivo SQLite valido."

    if nome.endswith(".zip"):
        db_bytes = _extrair_sqlite_do_zip(dados, slug)

        if db_bytes:
            return True, db_bytes, "Backup ZIP valido."

        return False, b"", "O ZIP enviado nao possui arquivo .db valido."

    return False, b"", "Formato invalido. Envie um arquivo .zip ou .db."


def _recuperar_por_upload(slug, db_bytes):
    try:
        db_path = _tenant_db(slug)

        if not db_bytes:
            return False, "Arquivo de backup invalido."

        if db_path.exists():
            nome_seguro = _nome_arquivo(
                "backup_antes_upload_restauracao",
                "db",
                slug,
            )
            db_seguro = db_path.with_name(nome_seguro)
            db_seguro.write_bytes(db_path.read_bytes())

        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(db_bytes)

        return True, "Sistema recuperado com sucesso pelo backup enviado."

    except Exception as e:
        return False, "Erro ao recuperar backup enviado: " + str(e)


def render():
    slug = slug_da_sessao()

    st.subheader("Backup de dados")
    st.caption(
        "Exporte, baixe, envie ao OneDrive e recupere os dados da sua igreja com seguranca."
    )

    igreja = st.session_state.get("igreja", {})
    plano = igreja.get("plano", "basico")

    _verificar_backup_automatico(slug)

    with st.expander("Backup manual", expanded=True):
        st.markdown("Escolha o formato e clique para baixar:")

        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**CSV (planilhas)**")
            st.caption("Cadastros e lancamentos em CSV — abre no Excel.")

            if st.button("Gerar CSV", key="btn_csv", use_container_width=True):
                dados = _gerar_zip_completo(slug)
                st.session_state["backup_manual_csv"] = dados
                st.session_state["backup_manual_csv_nome"] = _nome_arquivo(
                    "backup_csv",
                    "zip",
                    slug,
                )
                st.toast("CSV gerado!")

            if "backup_manual_csv" in st.session_state:
                st.download_button(
                    "Baixar CSV",
                    data=st.session_state["backup_manual_csv"],
                    file_name=st.session_state["backup_manual_csv_nome"],
                    mime="application/zip",
                    key="dl_csv",
                    use_container_width=True,
                    type="primary",
                )

        with c2:
            st.markdown("**Banco de dados (SQLite)**")
            st.caption("Arquivo completo do banco — para restaurar o sistema.")

            if st.button("Gerar SQLite", key="btn_sqlite", use_container_width=True):
                dados = _gerar_sqlite(slug)

                if dados:
                    st.session_state["backup_manual_db"] = dados
                    st.session_state["backup_manual_db_nome"] = _nome_arquivo(
                        "banco",
                        "db",
                        slug,
                    )
                    st.toast("Banco gerado!")
                else:
                    st.error("Banco nao encontrado.")

            if "backup_manual_db" in st.session_state:
                st.download_button(
                    "Baixar SQLite",
                    data=st.session_state["backup_manual_db"],
                    file_name=st.session_state["backup_manual_db_nome"],
                    mime="application/octet-stream",
                    key="dl_sqlite",
                    use_container_width=True,
                    type="primary",
                )

        with c3:
            st.markdown("**Backup completo (ZIP)**")
            st.caption("CSV + banco SQLite + resumo em um unico arquivo.")

            if st.button(
                "Gerar backup completo",
                key="btn_completo",
                use_container_width=True,
            ):
                dados = _gerar_zip_completo(slug)
                nome = _nome_arquivo("backup_completo", "zip", slug)

                st.session_state["backup_manual_completo"] = dados
                st.session_state["backup_manual_completo_nome"] = nome

                st.toast("Backup completo gerado!")

            if "backup_manual_completo" in st.session_state:
                st.download_button(
                    "Baixar backup completo",
                    data=st.session_state["backup_manual_completo"],
                    file_name=st.session_state["backup_manual_completo_nome"],
                    mime="application/zip",
                    key="dl_completo",
                    use_container_width=True,
                    type="primary",
                )

    with st.expander("Enviar backup manual ao OneDrive", expanded=False):
        st.caption(
            "Envia o ultimo backup completo manual gerado para a pasta configurada no OneDrive."
        )

        if "backup_manual_completo" not in st.session_state:
            st.info("Gere primeiro um backup completo manual.")

        else:
            st.info(
                "Arquivo pronto para envio: "
                + st.session_state.get(
                    "backup_manual_completo_nome",
                    "backup_completo.zip",
                )
            )

            if st.button("Enviar ultimo backup completo ao OneDrive", use_container_width=True):
                try:
                    _enviar_backup_onedrive(
                        st.session_state["backup_manual_completo_nome"],
                        st.session_state["backup_manual_completo"],
                    )
                    st.success("Backup enviado ao OneDrive com sucesso.")

                except Exception as e:
                    st.error("Erro ao enviar backup ao OneDrive: " + str(e))

    if tem_backup_automatico(plano):
        with st.expander("Backups automaticos", expanded=False):
            st.markdown(
                "Gerados automaticamente ao acessar o sistema e enviados ao OneDrive."
            )

            c1, c2 = st.columns(2)

            with c1:
                st.markdown("**Backup diario**")

                ultimo = st.session_state.get("backup_diario_" + slug)
                st.caption(
                    "Gerado em: "
                    + (ultimo.strftime("%d/%m/%Y") if ultimo else "-")
                )

                dados_d = st.session_state.get("backup_diario_dados_" + slug)
                nome_d = st.session_state.get(
                    "backup_diario_nome_" + slug,
                    "backup_diario.zip",
                )

                if dados_d:
                    st.download_button(
                        "Baixar backup diario",
                        data=dados_d,
                        file_name=nome_d,
                        mime="application/zip",
                        key="dl_auto_diario",
                        use_container_width=True,
                        type="primary",
                    )

                    if st.session_state.get("backup_diario_onedrive_" + slug):
                        st.success("Enviado ao OneDrive.")
                    else:
                        erro = st.session_state.get(
                            "backup_diario_onedrive_erro_" + slug
                        )
                        if erro:
                            st.warning("Nao foi enviado ao OneDrive.")
                            st.caption(erro)
                else:
                    st.info("Nenhum backup diario disponivel.")

            with c2:
                st.markdown("**Backup semanal**")

                semana = st.session_state.get("backup_semanal_" + slug)
                st.caption("Semana: " + (str(semana) if semana else "-"))

                dados_s = st.session_state.get("backup_semanal_dados_" + slug)
                nome_s = st.session_state.get(
                    "backup_semanal_nome_" + slug,
                    "backup_semanal.zip",
                )

                if dados_s:
                    st.download_button(
                        "Baixar backup semanal",
                        data=dados_s,
                        file_name=nome_s,
                        mime="application/zip",
                        key="dl_auto_semanal",
                        use_container_width=True,
                        type="primary",
                    )

                    if st.session_state.get("backup_semanal_onedrive_" + slug):
                        st.success("Enviado ao OneDrive.")
                    else:
                        erro = st.session_state.get(
                            "backup_semanal_onedrive_erro_" + slug
                        )
                        if erro:
                            st.warning("Nao foi enviado ao OneDrive.")
                            st.caption(erro)
                else:
                    st.info("Nenhum backup semanal disponivel.")

    else:
        p_info = obter_plano(plano)

        with st.expander(
            "🔒 Backups automaticos (apenas Profissional e Premium)",
            expanded=False,
        ):
            st.warning(
                f"Backup automatico esta disponivel apenas nos planos "
                f"**Profissional** e **Premium**. Seu plano atual: **{p_info['nome']}**."
            )
            st.caption("Voce continua tendo acesso ao backup manual acima.")
            st.info(
                f"Upgrade para **{proximo_plano(plano).capitalize()}** "
                f"para ter backups diarios e semanais automaticos."
            )

    with st.expander("Recuperacao do sistema pelo ultimo backup", expanded=False):
        st.warning(
            "A recuperacao substitui o banco de dados atual pelo banco contido no ultimo backup disponivel."
        )

        ultimo_backup = _obter_ultimo_backup_para_restaurar(slug)

        if ultimo_backup:
            st.info(
                "Ultimo backup disponivel: "
                + ultimo_backup["tipo"]
                + " — "
                + ultimo_backup["nome"]
            )
        else:
            st.error("Nenhum backup disponivel para recuperacao.")

        confirmar = st.checkbox(
            "Confirmo que desejo restaurar o sistema usando o ultimo backup disponivel.",
            key="confirmar_restauracao_backup",
        )

        if st.button(
            "Restaurar sistema pelo ultimo backup",
            key="btn_restaurar_backup",
            use_container_width=True,
            type="primary",
        ):
            if not confirmar:
                st.warning("Marque a confirmacao antes de restaurar.")
            else:
                sucesso, mensagem = _recuperar_pelo_ultimo_backup(slug)

                if sucesso:
                    st.success(mensagem)
                    st.info(
                        "Recarregue a pagina ou reinicie o aplicativo para atualizar os dados."
                    )
                else:
                    st.error(mensagem)

    with st.expander("Upload e recuperacao por arquivo de backup", expanded=False):
        st.warning(
            "Use esta opcao para restaurar o sistema a partir de um arquivo .zip ou .db."
        )

        arquivo_backup = st.file_uploader(
            "Selecione um arquivo de backup",
            type=["zip", "db"],
            key="upload_backup_restauracao",
        )

        if arquivo_backup is not None:
            st.info("Arquivo selecionado: " + arquivo_backup.name)

        confirmar_upload = st.checkbox(
            "Confirmo que desejo substituir os dados atuais pelo arquivo enviado.",
            key="confirmar_restauracao_upload",
        )

        if st.button(
            "Restaurar sistema pelo arquivo enviado",
            key="btn_restaurar_upload",
            use_container_width=True,
            type="primary",
        ):
            if arquivo_backup is None:
                st.warning("Envie um arquivo de backup antes de restaurar.")

            elif not confirmar_upload:
                st.warning("Marque a confirmacao antes de restaurar.")

            else:
                valido, db_bytes, msg_validacao = _validar_e_obter_db_do_upload(
                    arquivo_backup,
                    slug,
                )

                if not valido:
                    st.error(msg_validacao)

                else:
                    sucesso, mensagem = _recuperar_por_upload(slug, db_bytes)

                    if sucesso:
                        st.success(mensagem)
                        st.info(
                            "Recarregue a pagina ou reinicie o aplicativo para atualizar os dados."
                        )
                    else:
                        st.error(mensagem)

    with st.expander("Resumo dos dados", expanded=False):
        df_cad = carregar_cadastros(slug)
        df_lanc = carregar_lancamentos(slug)
        resumo = _gerar_resumo(df_cad, df_lanc, slug)
        st.code(resumo, language=None)
