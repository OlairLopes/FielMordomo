import pandas as pd
import streamlit as st

from data.repository import carregar_lancamentos, carregar_cadastros
from utils.helpers import formatar_moeda, slug_da_sessao


def render():
    slug   = slug_da_sessao()
    igreja = st.session_state.get("igreja", {})

    st.title("Bem-vindo, " + igreja.get("nome", ""))
    st.caption("Plano: " + igreja.get("plano", "").capitalize() + "  |  Identificador: " + slug)
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

    tipo_col = df["tipo"].fillna("").str.strip().str.upper()
    entradas = df[tipo_col == "ENTRADA"]["valor"].sum()
    saidas   = df[tipo_col == "SAIDA"]["valor"].sum()
    saldo    = entradas - saidas

    membros = 0
    if not cad.empty:
        tc  = cad["tipo_cadastro"].fillna("").str.strip().str.upper()
        sit = cad["situacao"].fillna("").str.strip().str.upper()
        membros = len(cad[(tc == "MEMBRO") & (sit == "ATIVO")])

    ult = df.dropna(subset=["data"]).sort_values("data", ascending=False)
    if not ult.empty:
        ult_data = ult.iloc[0]["data"].strftime("%d/%m/%Y")
        ult_desc = str(ult.iloc[0]["categoria"]) + " - " + formatar_moeda(ult.iloc[0]["valor"])
    else:
        ult_data = "-"
        ult_desc = "-"

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Saldo",             formatar_moeda(saldo),    delta=formatar_moeda(saldo))
    k2.metric("Entradas",          formatar_moeda(entradas))
    k3.metric("Saidas",            formatar_moeda(saidas))
    k4.metric("Membros ativos",    str(membros))
    k5.metric("Ultimo lancamento", ult_data, delta=ult_desc, delta_color="off")

    st.divider()
    _cards_nav()



NAV = [
    ("cadastros",       "Membros e fornecedores", "Gerencie o cadastro de membros e fornecedores."),
    ("lancamentos",     "Lancamentos",            "Registre entradas e saidas financeiras."),
    ("relatorios",      "Relatorios",             "Filtre e exporte dados por periodo."),
    ("dashboard",       "Dashboard",              "Graficos e indicadores visuais."),
    ("aniversariantes", "🎂 Aniversariantes",      "Veja quem faz aniversario hoje, na semana ou no mes."),
]

def _cards_nav():
    st.subheader("Ir para")
    c1, c2 = st.columns(2)
    cols = [c1, c2] * ((len(NAV) + 1) // 2)
    for (page, title, desc), col in zip(NAV, cols):
        with col:
            with st.container(border=True):
                st.markdown("### " + title)
                st.caption(desc)
                if st.button("Abrir", key="home_card_" + page,
                             use_container_width=True, type="primary"):
                    st.session_state["pagina"] = page
                    st.rerun()
