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
        height: 56px;
        background: #0F6E56;
        display: flex;
        align-items: center;
        padding: 0 20px;
        gap: 8px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.2);
    }
    #fm-navbar .fm-logo {
        font-size: 1rem;
        font-weight: 700;
        color: white;
        margin-right: 12px;
        white-space: nowrap;
    }
    #fm-navbar img {
        height: 34px;
        object-fit: contain;
        margin-right: 12px;
    }
    #fm-navbar .fm-sep {
        width: 1px;
        height: 20px;
        background: rgba(255,255,255,0.25);
        margin: 0 6px;
    }
    #fm-navbar .fm-item {
        padding: 5px 14px;
        border-radius: 6px;
        font-size: 0.82rem;
        color: rgba(255,255,255,0.85);
        white-space: nowrap;
        cursor: pointer;
        transition: background 0.15s;
    }
    #fm-navbar .fm-item:hover {
        background: rgba(255,255,255,0.12);
        color: white;
    }
    #fm-navbar .fm-item.fm-ativo {
        background: rgba(255,255,255,0.2);
        color: white;
        font-weight: 700;
    }
    #fm-navbar .fm-sair {
        padding: 5px 12px;
        border-radius: 6px;
        font-size: 0.8rem;
        color: rgba(255,255,255,0.85);
        border: 1px solid rgba(255,255,255,0.3);
        cursor: pointer;
        white-space: nowrap;
        transition: background 0.15s;
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
    }
    #fm-navbar .fm-info-nome {
        font-size: 0.75rem;
        font-weight: 600;
        color: white;
    }
    #fm-navbar .fm-info-plano {
        font-size: 0.62rem;
        color: rgba(255,255,255,0.6);
    }

    .fm-hidden-btns {
        position: absolute;
        opacity: 0;
        pointer-events: none;
        height: 0;
        overflow: hidden;
    }

    .block-container {
        padding-top: 76px !important;
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
        ativo   = " fm-ativo" if pagina_atual == key else ""
        ic      = ICONES.get(key, "")
        onclick = "document.getElementById('fmbtn_" + key + "').click()"
        itens_html += (
            '<span class="fm-item' + ativo + '" onclick="' + onclick + '">'
            + ic + " " + label + "</span>"
        )

    onclick_sair = "document.getElementById('fmbtn_sair').click()"
    sair_html    = '<span class="fm-sair" onclick="' + onclick_sair + '">Sair</span>'

    st.markdown(
        '<div id="fm-navbar">'
        + logo_html
        + itens_html
        + '<div class="fm-info">'
        + '<div class="fm-info-nome">' + nome + '</div>'
        + '<div class="fm-info-plano">Plano ' + plano + '</div>'
        + '</div>'
        + sair_html
        + '</div>',
        unsafe_allow_html=True,
    )

    # Botoes ocultos acionados pelo JS
    st.markdown('<div class="fm-hidden-btns">', unsafe_allow_html=True)

    for key, (label, _) in paginas.items():
        st.markdown('<div id="fmbtn_' + key + '_wrap">', unsafe_allow_html=True)
        if st.button(label, key="navbar_btn_" + key):
            st.session_state["pagina"] = key
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div id="fmbtn_sair_wrap">', unsafe_allow_html=True)
    if st.button("Sair", key="navbar_btn_sair"):
        logout()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # JS mapeia IDs aos botoes reais
    st.markdown("""
    <script>
    function mapearBotoes() {
        var wraps = document.querySelectorAll('[id$="_wrap"]');
        wraps.forEach(function(wrap) {
            var id = wrap.id.replace('_wrap', '');
            var btn = wrap.querySelector('button');
            if (btn) { btn.id = id; }
        });
    }
    setTimeout(mapearBotoes, 300);
    setTimeout(mapearBotoes, 800);
    setTimeout(mapearBotoes, 1500);
    </script>
    """, unsafe_allow_html=True)


def _navbar_admin():
    logo_r = obter_logo_sistema()
    if logo_r:
        dados, ext = logo_r
        logo_html = '<img src="' + _img_b64(dados, ext) + '" style="height:34px;margin-right:12px"/>'
    else:
        logo_html = '<span class="fm-logo">FielMordomo</span>'

    onclick_sair = "document.getElementById('fmbtn_sair_admin').click()"

    st.markdown(
        '<div id="fm-navbar">'
        + logo_html
        + '<div class="fm-sep"></div>'
        + '<span style="color:rgba(255,255,255,0.85);font-size:0.85rem">Painel Administrador</span>'
        + '<div style="margin-left:auto">'
        + '<span class="fm-sair" onclick="' + onclick_sair + '">Sair</span>'
        + '</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="fm-hidden-btns"><div id="fmbtn_sair_admin_wrap">', unsafe_allow_html=True)
    if st.button("Sair", key="navbar_btn_sair_admin"):
        logout()
    st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown("""
    <script>
    setTimeout(function() {
        var wrap = document.getElementById('fmbtn_sair_admin_wrap');
        if (wrap) {
            var btn = wrap.querySelector('button');
            if (btn) btn.id = 'fmbtn_sair_admin';
        }
    }, 500);
    </script>
    """, unsafe_allow_html=True)


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
