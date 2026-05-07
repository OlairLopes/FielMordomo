"""
FielMordomo - Gestao financeira para igrejas
SaaS multi-tenant com dados isolados por igreja
"""

import sys
import os
from pathlib import Path

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import streamlit as st

from data.repository import inicializar_master, obter_logo_igreja, obter_logo_sistema
from modules.auth import tela_login, logout, modo_atual

st.set_page_config(
    page_title="FielMordomo",
    page_icon="FM",
    layout="wide",
    initial_sidebar_state="auto",
)

inicializar_master()

if not tela_login():
    st.stop()

modo = modo_atual()

if modo == "admin":
    from admin import painel
    with st.sidebar:
        logo_sis = obter_logo_sistema()
        if logo_sis:
            dados, _ = logo_sis
            st.image(dados, width=140)
        else:
            st.markdown("### FielMordomo")
        st.caption("Painel do administrador")
        st.divider()
        if st.button("Sair", use_container_width=True):
            logout()
    painel.render()

elif modo == "igreja":
    from modules import home, cadastros, lancamentos, relatorios, graficos

    PAGINAS = {
        "home":        ("Inicio",              home),
        "cadastros":   ("Membros/Fornecedores", cadastros),
        "lancamentos": ("Lancamentos",          lancamentos),
        "relatorios":  ("Relatorios",           relatorios),
        "dashboard":   ("Dashboard",            graficos),
    }

    if "pagina" not in st.session_state:
        st.session_state["pagina"] = "home"

    with st.sidebar:
        igreja = st.session_state.get("igreja", {})
        slug   = igreja.get("slug", "")

        logo_ig = obter_logo_igreja(slug)
        if logo_ig:
            dados, _ = logo_ig
            st.image(dados, width=140)
        else:
            logo_sis = obter_logo_sistema()
            if logo_sis:
                dados, _ = logo_sis
                st.image(dados, width=140)
            else:
                st.markdown("### FielMordomo")

        st.caption(igreja.get("nome", ""))
        st.caption(f'Plano: {igreja.get("plano","").capitalize()}')
        st.divider()

        pagina_atual = st.session_state["pagina"]
        for key, (label, _) in PAGINAS.items():
            ativo = pagina_atual == key
            if st.button(
                label,
                key=f"menu_{key}",
                use_container_width=True,
                type="primary" if ativo else "secondary",
            ):
                st.session_state["pagina"] = key
                st.rerun()

        st.divider()
        if st.button("Sair", use_container_width=True):
            logout()

        st.caption("FielMordomo v1.0")

    if st.session_state["pagina"] != "home":
        if st.button("Voltar ao inicio", key="btn_back"):
            st.session_state["pagina"] = "home"
            st.rerun()
        st.divider()

    _, modulo = PAGINAS.get(st.session_state["pagina"], PAGINAS["home"])
    modulo.render()
