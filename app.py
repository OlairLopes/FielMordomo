"""
FielMordomo - Gestao financeira para igrejas
SaaS multi-tenant com dados isolados por igreja
"""

import base64
import html
import os
import sys

import streamlit as st

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from data.repository import (
    inicializar_master,
    obter_logo_igreja,
    obter_logo_sistema,
    obter_logo_sidebar_igreja,
    obter_logo_sidebar_sistema,
)
from modules.auth import tela_login, logout, modo_atual

st.set_page_config(
    page_title="FielMordomo",
    page_icon="FM",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _esc(valor):
    return html.escape(str(valor if valor is not None else ""), quote=True)


def _injetar_css():
    css = """
    <style>
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 3rem !important;
    }

    #MainMenu {
        display: none !important;
    }

    footer {
        display: none !important;
    }

    [data-testid="stSidebarCollapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        position: fixed !important;
        top: 12px !important;
        left: 12px !important;
        z-index: 999999 !important;
        background: #061B44 !important;
        border-radius: 10px !important;
        padding: 6px !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.30) !important;
    }

    [data-testid="stSidebarCollapsedControl"] button,
    [data-testid="stSidebarCollapsedControl"] svg {
        color: white !important;
        fill: white !important;
    }

    button[kind="header"] {
        color: white !important;
        background: #061B44 !important;
        border-radius: 10px !important;
    }

    button[kind="header"] svg {
        color: white !important;
        fill: white !important;
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #061B44 0%, #0A0A0A 100%) !important;
    }

    section[data-testid="stSidebar"] * {
        color: white !important;
    }

    section[data-testid="stSidebar"] .stButton button {
        width: 100%;
        background: transparent !important;
        border: none !important;
        color: rgba(255,255,255,0.92) !important;
        text-align: left !important;
        padding: 10px 14px !important;
        font-size: 0.95rem !important;
        border-radius: 8px !important;
        margin-bottom: 2px !important;
        transition: 0.2s;
    }

    section[data-testid="stSidebar"] .stButton button:hover {
        background: rgba(212,175,55,0.18) !important;
        color: #D4AF37 !important;
    }

    section[data-testid="stSidebar"] .stButton button[kind="primary"] {
        background: rgba(212,175,55,0.25) !important;
        color: #D4AF37 !important;
        font-weight: 700 !important;
        border-left: 3px solid #D4AF37 !important;
    }

    .sidebar-logo {
        text-align: center;
        padding: 10px 0 16px 0;
        border-bottom: 1px solid rgba(212,175,55,0.35);
        margin-bottom: 14px;
    }

    .sidebar-logo img {
        max-width: 140px;
        max-height: 90px;
        object-fit: contain;
    }

    .sidebar-info {
        text-align: center;
        font-size: 0.78rem;
        color: rgba(255,255,255,0.85) !important;
        margin: 0 0 14px 0;
        padding: 0 6px;
    }

    .sidebar-info b {
        color: #D4AF37 !important;
    }

    .sidebar-info .plano {
        font-size: 0.68rem;
        color: rgba(255,255,255,0.65) !important;
        margin-top: 2px;
    }

    .block-container {
        padding-top: 3.5rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def _img_b64(dados, ext):
    ext = str(ext or "").lower()
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext
    return "data:" + mime + ";base64," + base64.b64encode(dados).decode()


def _logo_para_sidebar_igreja(slug):
    return (
        obter_logo_sidebar_igreja(slug)
        or obter_logo_sidebar_sistema()
        or obter_logo_igreja(slug)
        or obter_logo_sistema()
    )


def _logo_para_sidebar_admin():
    return obter_logo_sidebar_sistema() or obter_logo_sistema()


def _sidebar_igreja(pagina_atual, paginas, igreja, slug):
    icones = {
        "home": "🏠",
        "cadastros": "👤",
        "lancamentos": "💵",
        "relatorios": "📋",
        "dashboard": "📊",
        "aniversariantes": "🎂",
        "backup": "💾",
        "minha_conta": "⚙️",
    }

    with st.sidebar:
        logo_r = _logo_para_sidebar_igreja(slug)

        if logo_r:
            dados, ext = logo_r
            st.markdown(
                f'<div class="sidebar-logo">'
                f'<img src="{_img_b64(dados, ext)}"/>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="sidebar-logo" style="font-size:1.4rem;font-weight:700;color:white">'
                'FielMordomo</div>',
                unsafe_allow_html=True,
            )

        nome = _esc(igreja.get("nome", "FielMordomo"))
        plano = _esc(str(igreja.get("plano", "")).capitalize())

        st.markdown(
            f'<div class="sidebar-info">'
            f'<b>{nome}</b>'
            f'<div class="plano">Plano {plano}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        for key, (label, _) in paginas.items():
            icone = icones.get(key, "")
            ativo = pagina_atual == key

            if st.button(
                f"{icone}  {label}",
                key=f"sb_{key}",
                use_container_width=True,
                type="primary" if ativo else "secondary",
            ):
                st.session_state["pagina"] = key
                st.rerun()

        st.markdown(
            '<hr style="border:none;border-top:1px solid rgba(212,175,55,0.35);margin:12px 0">',
            unsafe_allow_html=True,
        )

        if st.button("🚪  Sair", key="sb_sair", use_container_width=True):
            logout()


def _sidebar_admin():
    with st.sidebar:
        logo_r = _logo_para_sidebar_admin()

        if logo_r:
            dados, ext = logo_r
            st.markdown(
                f'<div class="sidebar-logo">'
                f'<img src="{_img_b64(dados, ext)}"/>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="sidebar-logo" style="font-size:1.4rem;font-weight:700;color:white">'
                'FielMordomo</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div class="sidebar-info"><b>Administrador</b>'
            '<div class="plano">Painel do sistema</div></div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<hr style="border:none;border-top:1px solid rgba(212,175,55,0.35);margin:12px 0">',
            unsafe_allow_html=True,
        )

        if st.button("🚪  Sair", key="sb_sair_admin", use_container_width=True):
            logout()


inicializar_master()

if not tela_login():
    st.stop()

_injetar_css()

modo = modo_atual()

if modo == "admin":
    from admin import painel

    _sidebar_admin()
    painel.render()

elif modo == "igreja":
    from modules import (
        home,
        cadastros,
        lancamentos,
        relatorios,
        graficos,
        backup,
        aniversariantes,
        minha_conta,
    )

    paginas = {
        "home": ("Inicio", home),
        "cadastros": ("Membros", cadastros),
        "lancamentos": ("Lancamentos", lancamentos),
        "relatorios": ("Relatorios", relatorios),
        "dashboard": ("Dashboard", graficos),
        "aniversariantes": ("Aniversarios", aniversariantes),
        "backup": ("Backup", backup),
        "minha_conta": ("Minha conta", minha_conta),
    }

    if st.session_state.get("pagina") not in paginas:
        st.session_state["pagina"] = "home"

    igreja = st.session_state.get("igreja", {})
    slug = igreja.get("slug", "")

    _sidebar_igreja(
        pagina_atual=st.session_state["pagina"],
        paginas=paginas,
        igreja=igreja,
        slug=slug,
    )

    _, modulo = paginas.get(st.session_state["pagina"], paginas["home"])
    modulo.render()

else:
    st.error("Modo de acesso invalido. Faca login novamente.")
    if st.button("Sair"):
        logout()
