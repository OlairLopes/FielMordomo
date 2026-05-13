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
        background: #050c3b;
        display: flex;
        align-items: center;
        padding: 0 20px;
        gap: 4px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.2);
        pointer-events: none;
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
    .fm-btn-container {
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 9999999;
        height: 52px;
        display: flex;
        align-items: center;
        padding: 0 180px 0 160px;
        gap: 2px;
        pointer-events: none;
    }
    .fm-btn-container > div {
        pointer-events: all;
        flex: 1;
    }
    .fm-btn-container button {
        height: 36px !important;
        background: transparent !important;
        border: none !important;
        color: rgba(255,255,255,0.85) !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        border-radius: 6px !important;
        width: 100% !important;
        cursor: pointer !important;
        padding: 0 8px !important;
    }
    .fm-btn-container button:hover {
        background: rgba(255,255,255,0.12) !important;
        color: white !important;
    }
    .fm-btn-container button[kind="primary"] {
        background: rgba(255,255,255,0.2) !important;
        color: white !important;
        font-weight: 700 !important;
    }
    .fm-btn-sair {
        position: fixed;
        top: 8px;
        right: 20px;
        z-index: 9999999;
        pointer-events: all;
    }
    .fm-btn-sair button {
        height: 36px !important;
        background: transparent !important;
        border: 1px solid rgba(255,255,255,0.35) !important;
        color: rgba(255,255,255,0.85) !important;
        font-size: 0.78rem !important;
        border-radius: 6px !important;
        cursor: pointer !important;
        padding: 0 12px !important;
    }
    .fm-btn-sair button:hover {
        background: rgba(255,255,255,0.15) !important;
        color: white !important;
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
    "home":            "⛪",
    "cadastros":       "👤",
    "lancamentos":     "💵",
    "relatorios":      "📋",
    "dashboard":       "📊",
    "aniversariantes": "🎂",
    "backup":          "💾",
}
    nome   = igreja.get("nome", "FielMordomo")
    plano  = igreja.get("plano", "").capitalize()
    logo_r = obter_logo_igreja(slug) or obter_logo_sistema()

    if logo_r:
        dados, ext = logo_r
        logo_html = '<img src="' + _img_b64(dados, ext) + '"/>'
    else:
        logo_html = '<span class="fm-logo">FielMordomo</span>'

    st.markdown(
        '<div id="fm-navbar">'
        + logo_html
        + '<div class="fm-sep"></div>'
        + '<div class="fm-info">'
        + '<div class="fm-info-nome">' + nome + '</div>'
        + '<div class="fm-info-plano">Plano ' + plano + '</div>'
        + '</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="fm-btn-container">', unsafe_allow_html=True)
    cols = st.columns(len(paginas))
    for i, (key, (label, _)) in enumerate(paginas.items()):
        with cols[i]:
            ic    = ICONES.get(key, "")
            ativo = pagina_atual == key
            if st.button(
                ic + " " + label,
                key="nb_" + key,
                use_container_width=True,
                type="primary" if ativo else "secondary",
            ):
                st.session_state["pagina"] = key
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="fm-btn-sair">', unsafe_allow_html=True)
    if st.button("Sair", key="nb_sair"):
        logout()
    st.markdown('</div>', unsafe_allow_html=True)


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
        + '</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="fm-btn-sair">', unsafe_allow_html=True)
    if st.button("Sair", key="nb_sair_admin"):
        logout()
    st.markdown('</div>', unsafe_allow_html=True)


# ── Bootstrap ─────────────────────────────────────────────────────────────
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
    from modules import home, cadastros, lancamentos, relatorios, graficos, backup, aniversariantes
    PAGINAS = {
    "home":            ("Inicio",       home),
    "cadastros":       ("Membros",      cadastros),
    "lancamentos":     ("Lancamentos",  lancamentos),
    "relatorios":      ("Relatorios",   relatorios),
    "dashboard":       ("Dashboard",    graficos),
    "aniversariantes": ("Aniversarios", aniversariantes),
    "backup":          ("Backup",       backup),
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
