"""
FielMordomo - Gestao financeira para igrejas
SaaS multi-tenant com dados isolados por igreja
"""

import sys
import os
import base64

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
    initial_sidebar_state="collapsed",
)


def _injetar_css():
    st.markdown("""
    <style>
    [data-testid="collapsedControl"] { display: none !important; }
    header[data-testid="stHeader"]   { display: none !important; }
    #MainMenu { display: none !important; }
    footer    { display: none !important; }

    [data-testid="stHorizontalBlock"]:first-of-type {
        background: #0F6E56;
        padding: 6px 16px;
        margin: 0 !important;
        gap: 4px !important;
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 99999;
    }
    [data-testid="stHorizontalBlock"]:first-of-type button {
        background: transparent !important;
        border: none !important;
        color: rgba(255,255,255,0.85) !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        padding: 5px 12px !important;
        border-radius: 6px !important;
    }
    [data-testid="stHorizontalBlock"]:first-of-type button:hover {
        background: rgba(255,255,255,0.12) !important;
        color: white !important;
    }
    [data-testid="stHorizontalBlock"]:first-of-type button[kind="primary"] {
        background: rgba(255,255,255,0.2) !important;
        color: white !important;
        font-weight: 700 !important;
    }
    .block-container {
        padding-top: 80px !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
    </style>
    """, unsafe_allow_html=True)


def _img_b64(dados, ext):
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext
    return "data:" + mime + ";base64," + base64.b64encode(dados).decode()


def _navbar_igreja(pagina_atual, paginas, igreja, slug):
    ICONES = {
        "home":        "⛪",
        "cadastros":   "👤",
        "lancamentos": "💵",
        "relatorios":  "📋",
        "dashboard":   "📊",
    }

    nome  = igreja.get("nome", "FielMordomo")
    plano = igreja.get("plano", "").capitalize()

    logo_r = obter_logo_igreja(slug) or obter_logo_sistema()

    n = len(paginas)
    proporcoes = [1.5] + [1] * n + [2, 0.8]
    cols = st.columns(proporcoes)

    with cols[0]:
        if logo_r:
            dados, ext = logo_r
            st.markdown(
                '<img src="' + _img_b64(dados, ext) + '" style="height:36px;'
                'object-fit:contain;margin-top:4px"/>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span style="color:white;font-weight:700;font-size:1rem">'
                'FielMordomo</span>',
                unsafe_allow_html=True,
            )

    for i, (key, (label, _)) in enumerate(paginas.items()):
        with cols[i + 1]:
            ativo = pagina_atual == key
            ic    = ICONES.get(key, "")
            if st.button(
                ic + " " + label,
                key="nav_" + key,
                use_container_width=True,
                type="primary" if ativo else "secondary",
            ):
                st.session_state["pagina"] = key
                st.rerun()

    with cols[n + 1]:
        st.markdown(
            '<div style="text-align:right;line-height:1.3;padding-top:6px">'
            '<span style="color:white;font-size:0.75rem;font-weight:600">'
            + nome + "</span><br>"
            '<span style="color:rgba(255,255,255,0.6);font-size:0.65rem">'
            "Plano " + plano + "</span></div>",
            unsafe_allow_html=True,
        )

    with cols[n + 2]:
        if st.button("Sair", key="nav_sair", use_container_width=True):
            logout()


def _navbar_admin():
    logo_r = obter_logo_sistema()
    cols   = st.columns([1.5, 4, 0.8])

    with cols[0]:
        if logo_r:
            dados, ext = logo_r
            st.markdown(
                '<img src="' + _img_b64(dados, ext) + '" style="height:36px;'
                'object-fit:contain;margin-top:4px"/>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span style="color:white;font-weight:700;font-size:1rem">'
                'FielMordomo</span>',
                unsafe_allow_html=True,
            )

    with cols[1]:
        st.markdown(
            '<span style="color:rgba(255,255,255,0.85);font-size:0.85rem">'
            '⚙️ Painel Administrador</span>',
            unsafe_allow_html=True,
        )

    with cols[2]:
        if st.button("Sair", key="nav_sair_admin", use_container_width=True):
            logout()


inicializar_master()

if not tela_login():
    st.stop()

_injetar_css()

modo = modo_atual()

if modo == "admin":
    from admin import painel
    _navbar_admin()
    painel.render()

elif modo == "igreja":
    from modules import home, cadastros, lancamentos, relatorios, graficos

    PAGINAS = {
        "home":        ("Inicio",      home),
        "cadastros":   ("Membros",     cadastros),
        "lancamentos": ("Lancamentos", lancamentos),
        "relatorios":  ("Relatorios",  relatorios),
        "dashboard":   ("Dashboard",   graficos),
    }

    if "pagina" not in st.session_state:
        st.session_state["pagina"] = "home"

    igreja = st.session_state.get("igreja", {})
    slug   = igreja.get("slug", "")

    _navbar_igreja(
        pagina_atual=st.session_state["pagina"],
        paginas=PAGINAS,
        igreja=igreja,
        slug=slug,
    )

    _, modulo = PAGINAS.get(st.session_state["pagina"], PAGINAS["home"])
    modulo.render()
