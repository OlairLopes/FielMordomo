"""
FielMordomo - Gestao financeira para igrejas
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
    .fm-navbar {
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 999999;
        height: 56px;
        background: ##e6a50e;
        display: flex;
        align-items: center;
        padding: 0 20px;
        gap: 4px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    }
    .fm-brand-text {
        font-size: 1.05rem;
        font-weight: 700;
        color: white;
        margin-right: 12px;
        white-space: nowrap;
    }
    .fm-sep {
        width: 1px;
        height: 22px;
        background: rgba(255,255,255,0.25);
        margin: 0 8px;
        flex-shrink: 0;
    }
    .fm-nav-item {
        padding: 5px 12px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 500;
        color: rgba(255,255,255,0.8);
        white-space: nowrap;
    }
    .fm-nav-ativo {
        background: rgba(255,255,255,0.2);
        color: white;
        font-weight: 700;
        padding: 5px 12px;
        border-radius: 6px;
        font-size: 0.8rem;
        white-space: nowrap;
    }
    .fm-right {
        margin-left: auto;
        text-align: right;
        flex-shrink: 0;
    }
    .fm-igreja-nome {
        font-size: 0.75rem;
        font-weight: 600;
        color: white;
        white-space: nowrap;
    }
    .fm-igreja-plano {
        font-size: 0.62rem;
        color: rgba(255,255,255,0.6);
    }
    .fm-logo-img {
        height: 32px;
        width: auto;
        border-radius: 4px;
        object-fit: contain;
        margin-right: 10px;
        flex-shrink: 0;
    }
    .block-container { padding-top: 70px !important; }
    </style>
    """, unsafe_allow_html=True)


def _img_b64(dados, ext):
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext
    return "data:" + mime + ";base64," + base64.b64encode(dados).decode()


def _logo_tag(slug=""):
    if slug:
        r = obter_logo_igreja(slug)
        if r:
            return '<img src="' + _img_b64(r[0], r[1]) + '" class="fm-logo-img"/>'
    r = obter_logo_sistema()
    if r:
        return '<img src="' + _img_b64(r[0], r[1]) + '" class="fm-logo-img"/>'
    return '<span class="fm-brand-text">FielMordomo</span>'


def _navbar_igreja(pagina_atual, paginas, igreja, slug):
    ICONES = {
        "home":        "&#9962;",
        "cadastros":   "&#128100;",
        "lancamentos": "&#128181;",
        "relatorios":  "&#128203;",
        "dashboard":   "&#128202;",
    }

    itens = ""
    for key, (label, _) in paginas.items():
        ic = ICONES.get(key, "")
        if pagina_atual == key:
            itens += '<span class="fm-nav-ativo">' + ic + " " + label + "</span>"
        else:
            itens += '<span class="fm-nav-item">' + ic + " " + label + "</span>"

    nome  = igreja.get("nome", "")
    plano = igreja.get("plano", "").capitalize()

    st.markdown(
        '<div class="fm-navbar">'
        + _logo_tag(slug)
        + '<div class="fm-sep"></div>'
        + itens
        + '<div class="fm-right">'
        + '<div class="fm-igreja-nome">' + nome + "</div>"
        + '<div class="fm-igreja-plano">Plano ' + plano + "</div>"
        + "</div></div>",
        unsafe_allow_html=True,
    )

    ncols = len(paginas) + 1
    cols  = st.columns(ncols)
    for i, (key, (label, _)) in enumerate(paginas.items()):
        with cols[i]:
            tipo = "primary" if pagina_atual == key else "secondary"
            if st.button(label, key="nav_" + key,
                         use_container_width=True, type=tipo):
                st.session_state["pagina"] = key
                st.rerun()
    with cols[ncols - 1]:
        if st.button("Sair", key="nav_sair", use_container_width=True):
            logout()


def _navbar_admin():
    st.markdown(
        '<div class="fm-navbar">'
        + _logo_tag()
        + '<div class="fm-sep"></div>'
        + '<span class="fm-nav-ativo">Painel Administrador</span>'
        + "</div>",
        unsafe_allow_html=True,
    )
    if st.button("Sair", key="nav_sair_admin"):
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
