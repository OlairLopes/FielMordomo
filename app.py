"""
FielMordomo - Gestao financeira para igrejas
SaaS multi-tenant com dados isolados por igreja
"""

import sys
import os
from pathlib import Path
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

NAVBAR_CSS = """
<style>
[data-testid="collapsedControl"] { display: none; }
header[data-testid="stHeader"]   { display: none; }

.fm-navbar {
    position: fixed;
    top: 0; left: 0; right: 0;
    z-index: 9999;
    height: 56px;
    background: #0F6E56;
    display: flex;
    align-items: center;
    padding: 0 24px;
    gap: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.18);
}
.fm-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-right: 16px;
}
.fm-brand-text {
    font-size: 1.1rem;
    font-weight: 700;
    color: white;
    letter-spacing: 0.02em;
}
.fm-sep {
    width: 1px;
    height: 24px;
    background: rgba(255,255,255,0.2);
    margin: 0 8px;
}
.fm-nav-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 0.82rem;
    font-weight: 500;
    color: rgba(255,255,255,0.82);
    cursor: pointer;
    border: none;
    background: transparent;
    transition: background 0.15s, color 0.15s;
    white-space: nowrap;
}
.fm-nav-item:hover {
    background: rgba(255,255,255,0.12);
    color: white;
}
.fm-nav-item.active {
    background: rgba(255,255,255,0.18);
    color: white;
    font-weight: 600;
}
.fm-igreja-info {
    margin-left: auto;
    text-align: right;
    line-height: 1.3;
}
.fm-igreja-nome {
    font-size: 0.78rem;
    font-weight: 600;
    color: white;
}
.fm-igreja-plano {
    font-size: 0.65rem;
    color: rgba(255,255,255,0.6);
}
.fm-content-pad { padding-top: 68px; }
.fm-logo-img {
    height: 34px;
    width: auto;
    border-radius: 4px;
    object-fit: contain;
}
</style>
"""


def _img_base64(dados: bytes, ext: str) -> str:
    mime = "image/jpeg" if ext in ("jpg","jpeg") else f"image/{ext}"
    return f"data:{mime};base64,{base64.b64encode(dados).decode()}"


def _renderizar_navbar(pagina_atual: str, paginas: dict, igreja: dict, slug: str):
    ICONES = {
        "home":        "⛪",
        "cadastros":   "👤",
        "lancamentos": "💵",
        "relatorios":  "📋",
        "dashboard":   "📊",
    }

    logo_tag = ""
    logo_ig  = obter_logo_igreja(slug)
    logo_sis = obter_logo_sistema()
    if logo_ig:
        dados, ext = logo_ig
        logo_tag = f'<img src="{_img_base64(dados,ext)}" class="fm-logo-img"/>'
    elif logo_sis:
        dados, ext = logo_sis
        logo_tag = f'<img src="{_img_base64(dados,ext)}" class="fm-logo-img"/>'

    itens_html = ""
    for key, (label, _) in paginas.items():
        ativo = "active" if pagina_atual == key else ""
        icone = ICONES.get(key, "")
        itens_html += f'<span class="fm-nav-item {ativo}">{icone} {label}</span>'

    nome_ig  = igreja.get("nome", "")
    plano_ig = igreja.get("plano", "").capitalize()

    html = f"""
    {NAVBAR_CSS}
    <div class="fm-navbar">
        <div class="fm-brand">
            {logo_tag if logo_tag else '<span class="fm-brand-text">FielMordomo</span>'}
        </div>
        <div class="fm-sep"></div>
        {itens_html}
        <div class="fm-igreja-info">
            <div class="fm-igreja-nome">{nome_ig}</div>
            <div class="fm-igreja-plano">Plano {plano_ig}</div>
        </div>
    </div>
    <div class="fm-content-pad"></div>
    """
    st.markdown(html, unsafe_allow_html=True)

    cols = st.columns(len(paginas) + 1)
    for i, (key, (label, _)) in enumerate(paginas.items()):
        with cols[i]:
            if st.button(label, key=f"nav_{key}", use_container_width=True,
                         type="primary" if pagina_atual == key else "secondary"):
                st.session_state["pagina"] = key
                st.rerun()
    with cols[len(paginas)]:
        if st.button("Sair", key="nav_sair", use_container_width=True):
            logout()


def _renderizar_navbar_admin():
    logo_sis = obter_logo_sistema()
    logo_tag = ""
    if logo_sis:
        dados, ext = logo_sis
        logo_tag = f'<img src="{_img_base64(dados,ext)}" class="fm-logo-img"/>'

    html = f"""
    {NAVBAR_CSS}
    <div class="fm-navbar">
        <div class="fm-brand">
            {logo_tag if logo_tag else '<span class="fm-brand-text">FielMordomo</span>'}
        </div>
        <div class="fm-sep"></div>
        <span class="fm-nav-item active">⚙️ Painel Administrador</span>
    </div>
    <div class="fm-content-pad"></div>
    """
    st.markdown(html, unsafe_allow_html=True)

    if st.button("Sair", key="nav_sair_admin"):
        logout()


inicializar_master()

if not tela_login():
    st.stop()

modo = modo_atual()

if modo == "admin":
    from admin import painel
    _renderizar_navbar_admin()
    painel.render()

elif modo == "igreja":
    from modules import home, cadastros, lancamentos, relatorios, graficos

    PAGINAS = {
        "home":        ("Inicio",       home),
        "cadastros":   ("Membros",      cadastros),
        "lancamentos": ("Lancamentos",  lancamentos),
        "relatorios":  ("Relatorios",   relatorios),
        "dashboard":   ("Dashboard",    graficos),
    }

    if "pagina" not in st.session_state:
        st.session_state["pagina"] = "home"

    igreja = st.session_state.get("igreja", {})
    slug   = igreja.get("slug", "")

    _renderizar_navbar(
        pagina_atual=st.session_state["pagina"],
        paginas=PAGINAS,
        igreja=igreja,
        slug=slug,
    )

    _, modulo = PAGINAS.get(st.session_state["pagina"], PAGINAS["home"])
    modulo.render()
