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
    #MainMenu                         { display: none !important; }
    footer                            { display: none !important; }

    .fm-navbar {
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 999999;
        height: 56px;
        background: #0F6E56;
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
    .fm-nav-item.ativo {
        background: rgba(255,255,255,0.2);
        color: white;
        font-weight: 700;
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
    .block-container {
        padding-top: 70px !important;
    }
    </style>
    """, unsafe_allow_html=True)


def _img_b64(dados: bytes, ext: str) -> str:
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    return f"data:{mime};base64,{base64.b64encode(dados).decode()}"


def _logo_tag(slug: str = "") -> str:
    if slug:
        r = obter_logo_igreja(slug)
        if r:
            return f'<img src="{_img_b64(r[0],r[1])}" class="fm-logo-img"/>'
    r = obter_logo_sistema()
    if r:
        return f'<img src="{_img_b64(r[0],r[1])}" class="fm-logo-img"/>'
    return '<span class="fm-brand-text">FielMordomo</span>'


def _navbar_igreja(pagina_atual: str, paginas: dict, igreja: dict, slug: str):
    ICONES = {
        "home":        "⛪",
        "cadastros":   "👤",
        "lancamentos": "💵",
        "relatorios":  "📋",
        "dashboard":   "📊",
    }

    itens = ""
    for key, (label, _) in paginas.items():
        css = "fm-nav-item ativo" if pagina_
