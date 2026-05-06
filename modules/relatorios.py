import pandas as pd
import streamlit as st

from data.repository import carregar_lancamentos, carregar_cadastros
from utils.helpers import formatar_moeda, preparar_df, gerar_csv, slug_da_sessao


def render():
    slug = slug_da_sessao()
    st.subheader("Relatorios")

    df = carregar_lancamentos(slug)
    cad = carregar_cadastros(slug)

    if df.empty:
        st.info("Ainda nao ha lancamentos.")
        return

    df["data"]    = pd.to_datetime(df["data"], errors="coerce")
    df["valor"]   = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df["mes_ref"] = df["data"].dt.strftime("%m/%Y")

    membros_disp = sorted([n for n in cad[cad["tipo_cadastro"].str.upper() == "MEMBRO"]["nome"].dropna().unique() if n.strip()])
    meses_ord    = sorted(df["data"].dropna().dt.to_period("M").unique())
    meses_disp   = [m.strftime("%m/%Y") for m in meses_ord]

    c1, c2 = st.columns(2)
    with c1:
        membro_sel = st.selectbox("Filtrar por membro", ["Todos"] + membros_disp)
    with c2:
        mes_sel = st.selectbox("Filtrar por mes", ["Todos"] + meses_disp)

    df_f = df.copy()
    if membro_sel != "Todos":
        df_f = df_f[df_f["nome_cadastro"].fillna("").str.strip() == membro_sel]
    if mes_sel != "Todos":
        df_f = df_f[df_f["mes_ref"] == mes_sel]

    if df_f.empty:
        st.info("Nenhum lancamento para os filtros selecionados.")
        return

    ent  = df_f[df_f["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    sai  = df_f[df_f["tipo"].str.upper() == "SAIDA"]["valor"].sum()
    sald = ent - sai

    k1, k2, k3 = st.columns(3)
    k1.metric("Entradas", formatar_moeda(ent))
    k2.metric("Saidas",   formatar_moeda(sai))
    k3.metric("Saldo",    formatar_moeda(sald), delta=formatar_moeda(sald))

    st.write("### Total por categoria")
    res = df_f.groupby("categoria", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
    res_fmt = res.copy(); res_fmt["valor"] = res_fmt["valor"].apply(formatar_moeda)
    st.dataframe(res_fmt, use_container_width=True)

    st.write("### Dizimos por membro")
    diz = df_f[df_f["categoria"].str.upper() == "DIZIMO"]
    if diz.empty:
        st.info("Sem dizimos no periodo.")
    else:
        d_agg = diz.groupby(["id_cadastro", "nome_cadastro"], as_index=False)["valor"].sum().sort_values("valor", ascending=False)
        d_fmt = d_agg.copy(); d_fmt["valor"] = d_fmt["valor"].apply(formatar_moeda)
        st.dataframe(d_fmt, use_container_width=True)

    st.write("### Despesas por fornecedor")
    desp = df_f[(df_f["categoria"].str.upper() == "DESPESA") & (df_f["tipo_cadastro"].str.upper() == "FORNECEDOR")]
    if desp.empty:
        st.info("Sem despesas vinculadas a fornecedor.")
    else:
        d2 = desp.groupby(["id_cadastro", "nome_cadastro"], as_index=False)["valor"].sum().sort_values("valor", ascending=False)
        d2f = d2.copy(); d2f["valor"] = d2f["valor"].apply(formatar_moeda)
        st.dataframe(d2f, use_container_width=True)

    st.write("### Lancamentos detalhados")
    st.dataframe(preparar_df(df_f), use_container_width=True)

    st.divider()
    st.write("#### Exportar")
    col1, col2 = st.columns(2)
    df_exp = df_f.copy()
    df_exp["data"] = pd.to_datetime(df_exp["data"]).dt.strftime("%d/%m/%Y")
    with col1:
        st.download_button("CSV lancamentos", gerar_csv(df_exp), "lancamentos.csv", "text/csv")
    with col2:
        st.download_button("CSV resumo", gerar_csv(res_fmt), "resumo.csv", "text/csv")
