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
    section[data-testid="stSidebar"] { display: none !important; }

    #fm-navbar {
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 999999;
        height: 52px;
        background: #1b84e0;
        display: flex;
        align-items: center;
        padding: 0 20px;
        gap: 4px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.2);
    }
    #fm-navbar .fm-logo {
        font-size: 1rem;
        font-weight: 700;
        color: white;
        margin-right: 10px;
        white-space: nowrap;
    }
    #fm-navbar img {
        height: 32px;
        object-fit: contain;
        margin-right: 10px;
    }
    #fm-navbar .fm-sep {
        width: 1px;
        height: 20px;
        background: rgba(255,255,255,0.25);
        margin: 0 8px;
        flex-shrink: 0;
    }
    #fm-navbar .fm-item {
        padding: 5px 13px;
        border-radius: 6px;
        font-size: 0.8rem;
        color: rgba(255,255,255,0.85);
        white-space: nowrap;
        cursor: pointer;
        user-select: none;
        text-decoration: none;
    }
    #fm-navbar .fm-item:hover {
        background: rgba(255,255,255,0.12);
        color: white;
    }
    #fm-navbar .fm-ativo {
        background: rgba(255,255,255,0.2) !important;
        color: white !important;
        font-weight: 700;
    }
    #fm-navbar .fm-sair {
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 0.78rem;
        color: rgba(255,255,255,0.85);
        border: 1px solid rgba(255,255,255,0.35);
        cursor: pointer;
        white-space: nowrap;
        text-decoration: none;
    }
    #fm-navbar .fm-sair:hover {
        background: rgba(255,255,255,0.15);
        color: white;
    }
    #fm-navbar .fm-info {
        margin-left: auto;
        text-align: right;
        line-height: 1.3;
        margin-right: 12px;
        flex-shrink: 0;
    }
    #fm-navbar .fm-info-nome {
        font-size: 0.73rem;
        font-weight: 600;
        color: white;
        white-space: nowrap;
    }
    #fm-navbar .fm-info-plano {
        font-size: 0.6rem;
        color: rgba(255,255,255,0.6);
    }
    .block-container {
        padding-top: 70px !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
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

    nome   = igreja.get("nome", "FielMordomo")
    plano  = igreja.get("plano", "").capitalize()
    logo_r = obter_logo_igreja(slug) or obter_logo_sistema()

    if logo_r:
        dados, ext = logo_r
        logo_html = '<img src="' + _img_b64(dados, ext) + '"/>'
    else:
        logo_html = '<span class="fm-logo">FielMordomo</span>'

    itens_html = '<div class="fm-sep"></div>'
    for key, (label, _) in paginas.items():
        ativo = ' fm-ativo' if pagina_atual == key else ''
        ic    = ICONES.get(key, '')
        itens_html += (
            '<a class="fm-item' + ativo + '" href="?page=' + key + '" target="_self">'
            + ic + ' ' + label + '</a>'
        )

    st.markdown(
        '<div id="fm-navbar">'
        + logo_html
        + itens_html
        + '<div class="fm-info">'
        + '<div class="fm-info-nome">' + nome + '</div>'
        + '<div class="fm-info-plano">Plano ' + plano + '</div>'
        + '</div>'
        + '<a class="fm-sair" href="?sair=1" target="_self">Sair</a>'
        + '</div>',
        unsafe_allow_html=True,
    )


def _navbar_admin():
    logo_r = obter_logo_sistema()
    if logo_r:
        dados, ext = logo_r
        logo_html = '<img src="' + _img_b64(dados, ext) + '"/>'
    else:
        logo_html = '<span class="fm-logo">FielMordomo</span>'

    st.markdown(
        '<div id="fm-navbar">'
        + logo_html
        + '<div class="fm-sep"></div>'
        + '<span style="color:rgba(255,255,255,0.85);font-size:0.85rem">Painel Administrador</span>'
        + '<div style="margin-left:auto">'
        + '<a class="fm-sair" href="?sair=1" target="_self">Sair</a>'
        + '</div></div>',
        unsafe_allow_html=True,
    )


# ── Bootstrap ─────────────────────────────────────────────────────────────
inicializar_master()

if not tela_login():
    st.stop()

_injetar_css()

# Navegacao via query params
params = st.query_params

if "sair" in params:
    st.query_params.clear()
    logout()

if "page" in params:
    pagina_req = params["page"]
    paginas_validas = ["home", "cadastros", "lancamentos", "relatorios", "dashboard"]
    if pagina_req in paginas_validas:
        st.session_state["pagina"] = pagina_req
    st.query_params.clear()
    st.rerun()

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
