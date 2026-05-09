"""
Modulo de backup — exportacao e download de dados da igreja.
Suporta: CSV (cadastros + lancamentos) e SQLite completo.
Backup automatico: diario e semanal com controle por session_state.
"""

import io
import zipfile
import datetime
import streamlit as st
import pandas as pd

from data.repository import (
    carregar_cadastros, carregar_lancamentos, _tenant_db,
)
from utils.helpers import slug_da_sessao, formatar_moeda


def _nome_arquivo(prefixo: str, ext: str, slug: str) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefixo}_{slug}_{ts}.{ext}"


def _gerar_zip_csv(slug: str) -> bytes:
    df_cad  = carregar_cadastros(slug)
    df_lanc = carregar_lancamentos(slug)

    if not df_lanc.empty and "data" in df_lanc.columns:
        df_lanc = df_lanc.copy()
        df_lanc["data"] = pd.to_datetime(df_lanc["data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"cadastros_{slug}.csv",
                    df_cad.to_csv(index=False, encoding="utf-8-sig"))
        zf.writestr(f"lancamentos_{slug}.csv",
                    df_lanc.to_csv(index=False, encoding="utf-8-sig"))
        zf.writestr(f"resumo_{slug}.txt", _gerar_resumo(df_cad, df_lanc, slug))

    buf.seek(0)
    return buf.read()


def _gerar_sqlite(slug: str) -> bytes:
    db_path = _tenant_db(slug)
    if db_path.exists():
        return db_path.read_bytes()
    return b""


def _gerar_zip_completo(slug: str) -> bytes:
    df_cad  = carregar_cadastros(slug)
    df_lanc = carregar_lancamentos(slug)

    if not df_lanc.empty and "data" in df_lanc.columns:
        df_lanc = df_lanc.copy()
        df_lanc["data"] = pd.to_datetime(df_lanc["data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"cadastros_{slug}.csv",
                    df_cad.to_csv(index=False, encoding="utf-8-sig"))
        zf.writestr(f"lancamentos_{slug}.csv",
                    df_lanc.to_csv(index=False, encoding="utf-8-sig"))
        zf.writestr(f"resumo_{slug}.txt", _gerar_resumo(df_cad, df_lanc, slug))
        db_bytes = _gerar_sqlite(slug)
        if db_bytes:
            zf.writestr(f"banco_{slug}.db", db_bytes)

    buf.seek(0)
    return buf.read()


def _gerar_resumo(df_cad: pd.DataFrame, df_lanc: pd.DataFrame, slug: str) -> str:
    agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    linhas = [
        "=" * 50,
        "FIELMORDOMO — RESUMO DO BACKUP",
        "=" * 50,
        f"Igreja: {slug}",
        f"Data/hora: {agora}",
        "",
        "--- CADASTROS ---",
        f"Total: {len(df_cad)} registros",
    ]

    if not df_cad.empty and "tipo_cadastro" in df_cad.columns:
        membros      = len(df_cad[df_cad["tipo_cadastro"].str.upper() == "MEMBRO"])
        fornecedores = len(df_cad[df_cad["tipo_cadastro"].str.upper() == "FORNECEDOR"])
        linhas.append(f"  Membros: {membros}")
        linhas.append(f"  Fornecedores: {fornecedores}")

    linhas += ["", "--- LANCAMENTOS ---", f"Total: {len(df_lanc)} registros"]

    if not df_lanc.empty:
        if "valor" in df_lanc.columns:
            df_lanc = df_lanc.copy()
            df_lanc["valor"] = pd.to_numeric(df_lanc["valor"], errors="coerce").fillna(0)
        if "tipo" in df_lanc.columns:
            entradas = df_lanc[df_lanc["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
            saidas   = df_lanc[df_lanc["tipo"].str.upper() == "SAIDA"]["valor"].sum()
            linhas.append(f"  Total entradas: {formatar_moeda(entradas)}")
            linhas.append(f"  Total saidas:   {formatar_moeda(saidas)}")
            linhas.append(f"  Saldo:          {formatar_moeda(entradas - saidas)}")

    linhas += [
        "",
        "=" * 50,
        "FielMordomo — Sistema de Gestao Financeira",
        "=" * 50,
    ]
    return "\n".join(linhas)


def _verificar_backup_automatico(slug: str):
    agora = datetime.datetime.now()
    hoje  = agora.date()

    # Backup diario
    ultimo_diario = st.session_state.get(f"backup_diario_{slug}")
    if ultimo_diario != hoje:
        dados = _gerar_zip_completo(slug)
        st.session_state[f"backup_diario_{slug}"]       = hoje
        st.session_state[f"backup_diario_dados_{slug}"] = dados
        st.session_state[f"backup_diario_nome_{slug}"]  = _nome_arquivo("backup_diario", "zip", slug)

    # Backup semanal
    semana_atual   = agora.isocalendar()[1]
    ultimo_semanal = st.session_state.get(f"backup_semanal_{slug}")
    if ultimo_semanal != semana_atual:
        dados = _gerar_zip_completo(slug)
        st.session_state[f"backup_semanal_{slug}"]       = semana_atual
        st.session_state[f"backup_semanal_dados_{slug}"] = dados
        st.session_state[f"backup_semanal_nome_{slug}"]  = _nome_arquivo("backup_semanal", "zip", slug)


def render():
    slug = slug_da_sessao()
    st.subheader("Backup de dados")
    st.caption("Exporte e baixe os dados da sua igreja para guardar em seguranca.")

    _verificar_backup_automatico(slug)

    # ── Backup manual ─────────────────────────────────────────────────────
    with st.expander("Backup manual", expanded=True):
        st.markdown("Escolha o formato e clique para baixar:")
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**CSV (planilhas)**")
            st.caption("Cadastros e lancamentos em formato CSV — abre no Excel.")
            if st.button("Gerar CSV", key="btn_csv", use_container_width=True):
                dados = _gerar_zip_completo(slug)
                st.session_state["backup_manual_csv"]      = dados
                st.session_state["backup_manual_csv_nome"] = _nome_arquivo("backup_csv", "zip", slug)
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
                    st.session_state["backup_manual_db"]      = dados
                    st.session_state["backup_manual_db_nome"] = _nome_arquivo("banco", "db", slug)
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
            if st.button("Gerar backup completo", key="btn_completo", use_container_width=True):
                dados = _gerar_zip_completo(slug)
                st.session_state["backup_manual_completo"]      = dados
                st.session_state["backup_manual_completo_nome"] = _nome_arquivo("backup_completo", "zip", slug)
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

    # ── Backups automaticos ───────────────────────────────────────────────
    with st.expander("Backups automaticos", expanded=False):
        st.markdown("Gerados automaticamente ao acessar o sistema.")
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Backup diario**")
            ultimo = st.session_state.get(f"backup_diario_{slug}")
            st.caption(f"Gerado em: {ultimo.strftime('%d/%m/%Y') if ultimo else '-'}")
            dados_d = st.session_state.get(f"backup_diario_dados_{slug}")
            nome_d  = st.session_state.get(f"backup_diario_nome_{slug}", "backup_diario.zip")
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
            else:
                st.info("Nenhum backup diario disponivel.")

        with c2:
            st.markdown("**Backup semanal**")
            semana = st.session_state.get(f"backup_semanal_{slug}")
            st.caption(f"Semana: {semana if semana else '-'}")
            dados_s = st.session_state.get(f"backup_semanal_dados_{slug}")
            nome_s  = st.session_state.get(f"backup_semanal_nome_{slug}", "backup_semanal.zip")
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
            else:
                st.info("Nenhum backup semanal disponivel.")

    # ── Resumo dos dados ──────────────────────────────────────────────────
    with st.expander("Resumo dos dados", expanded=False):
        df_cad  = carregar_cadastros(slug)
        df_lanc = carregar_lancamentos(slug)
        resumo  = _gerar_resumo(df_cad, df_lanc, slug)
        st.code(resumo, language=None)
