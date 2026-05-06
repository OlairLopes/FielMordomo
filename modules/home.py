import pandas as pd
import streamlit as st

from data.repository import carregar_lancamentos, carregar_cadastros
from utils.helpers import formatar_moeda, slug_da_sessao


def render():
    slug  = slug_da_sessao()
    igreja = st.session_state.get("igreja", {})

    st.title(f"Bem-vindo, {igreja.get('nome', '')}")
    st.caption(f"Plano: {igreja.get('plano', '').capitalize()}  |  Identificador: {slug}")
    st.divider()

    try:
        df  = carregar_lancamentos(slug)
        cad = carregar_cadastros(slug)
    except Exception:
        st.info("Ainda nao ha dados. Comece pelos cadastros.")
        _cards_nav()
        return

    if df.empty:
        st.info("Ainda nao ha lancamentos. Comece cadastrando membros.")
        _cards_nav()
        return

    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df["data"]  = pd.to_datetime(df["data"], errors="coerce")

    entradas = df[df["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    saidas   = df[df["tipo"].str.upper() == "SAIDA"]["valor"].sum()
    saldo    = entradas - saidas
    membros  = len(cad[
        (cad["tipo_cadastro"].str.upper() == "MEMBRO") &
        (cad["situacao"].str.upper() == "ATIVO")
    ])

    ult = df.dropna(subset=["data"]).sort_values("data", ascending=False)
    ult_data = ult.iloc[0]["data"].strftime("%d/%m/%Y") if not ult.empty else "-"
    ult_desc = f'{ult.iloc[0]["categoria"]} - {formatar_moeda(ult.iloc[0]["valor"])}' if not ult.empty else "-"

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Saldo", formatar_moeda(saldo), delta=formatar_moeda(saldo))
    k2.metric("Entradas", formatar_moeda(entradas))
    k3.metric("Saidas", formatar_moeda(saidas))
    k4.metric("Membros ativos", str(membros))
    k5.metric("Ultimo lancamento", ult_data, delta=ult_desc, delta_color="off")

    st.divider()
    _cards_nav()


NAV = [
    ("cadastros",   "Membros e fornecedores", "Gerencie o cadastro de membros e fornecedores."),
    ("lancamentos", "Lancamentos",             "Registre entradas e saidas financeiras."),
    ("relatorios",  "Relatorios",              "Filtre e exporte dados por periodo."),
    ("dashboard",   "Dashboard",               "Graficos e indicadores visuais."),
]


def _cards_nav():
    st.subheader("Ir para")
    c1, c2 = st.columns(2)
    cols = [c1, c2, c1, c2]
    for (page, title, desc), col in zip(NAV, cols):
        with col:
            with st.container(border=True):
                st.markdown(f"### {title}")
                st.caption(desc)
                if st.button("Abrir", key=f"nav_{page}", use_container_width=True, type="primary"):
                    st.session_state["pagina"] = page
                    st.rerun()
