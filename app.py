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
    header[data-testid="stHeader"] { display: none !important; }
    #MainMenu { display: none !important; }
    footer { display: none !important; }

    /* Botao hamburguer sempre visivel */
    [data-testid="stSidebarCollapsedControl"] {
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
        position: fixed !important;
        top: 12px !important;
        left: 12px !important;
        z-index: 999999 !important;
        background: #061B44 !important;
        border-radius: 8px !important;
        padding: 6px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25) !important;
    }

    [data-testid="stSidebarCollapsedControl"] svg,
    [data-testid="stSidebarCollapsedControl"] button {
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
        color: rgba(255,255,255,0.9) !important;
        text-align: left !important;
        padding: 10px 14px !important;
        font-size: 0.95rem !important;
        border-radius: 8px !important;
        margin-bottom: 2px !important;
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
        max-width: 130px;
        max-height: 80px;
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
    """, unsafe_allow_html=True)


def _img_b64(dados, ext):
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext
    return "data:" + mime + ";base64," + base64.b64encode(dados).decode()


def _sidebar_igreja(pagina_atual, paginas, igreja, slug):
    ICONES = {
        "home":            "🏠",
        "cadastros":       "👤",
        "lancamentos":     "💵",
        "relatorios":      "📋",
        "dashboard":       "📊",
        "aniversariantes": "🎂",
        "backup":          "💾",
        "minha_conta":     "⚙️",
    }

    with st.sidebar:
        logo_r = obter_logo_igreja(slug) or obter_logo_sistema()

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

        nome = igreja.get("nome", "FielMordomo")
        plano = igreja.get("plano", "").capitalize()

        st.markdown(
            f'<div class="sidebar-info">'
            f'<b>{nome}</b>'
            f'<div class="plano">Plano {plano}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        for key, (label, _) in paginas.items():
            ic = ICONES.get(key, "")
            ativo = pagina_atual == key

            if st.button(
                f"{ic}  {label}",
                key=f"sb_{key}",
                use_container_width=True,
                type="primary" if ativo else "secondary",
            ):
                st.session_state["pagina"] = key
                st.rerun()

        st.markdown(
            '<hr style="border:none;border-top:1px solid rgba(212,175,55,0.35);'
            'margin:12px 0">',
            unsafe_allow_html=True,
        )

        if st.button("🚪  Sair", key="sb_sair", use_container_width=True):
            logout()


def _sidebar_admin():
    with st.sidebar:
        logo_r = obter_logo_sistema()

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
            '<hr style="border:none;border-top:1px solid rgba(212,175,55,0.35);'
            'margin:12px 0">',
            unsafe_allow_html=True,
        )

        if st.button("🚪  Sair", key="sb_sair_admin", use_container_width=True):
            logout()


# ── Bootstrap ─────────────────────────────────────────────────────────────
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

    PAGINAS = {
        "home":            ("Inicio",       home),
        "cadastros":       ("Membros",      cadastros),
        "lancamentos":     ("Lancamentos",  lancamentos),
        "relatorios":      ("Relatorios",   relatorios),
        "dashboard":       ("Dashboard",    graficos),
        "aniversariantes": ("Aniversarios", aniversariantes),
        "backup":          ("Backup",       backup),
        "minha_conta":     ("Minha conta",  minha_conta),
    }

    if "pagina" not in st.session_state:
        st.session_state["pagina"] = "home"

    igreja = st.session_state.get("igreja", {})
    slug = igreja.get("slug", "")

    _sidebar_igreja(
        pagina_atual=st.session_state["pagina"],
        paginas=PAGINAS,
        igreja=igreja,
        slug=slug,
    )

    _, modulo = PAGINAS.get(st.session_state["pagina"], PAGINAS["home"])
    modulo.render()
