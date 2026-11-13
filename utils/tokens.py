"""Tokens de cor e estilos compartilhados (identidade visual do FielMordomo).

Use COR[...] em codigo Python (ex.: cores de graficos) e injete ESTILOS_PUBLICOS
nas telas publicas que precisam de classes CSS em vez de estilo inline.
"""
import streamlit as st
import streamlit.components.v1 as components

COR = {
    "navy": "#061B44",
    "navy_hover": "#0A2A66",
    "gold": "#D4AF37",
    "red": "#D62F3D",          # botao primario; contraste AA com texto branco
    "ink": "#10213A",
    "muted": "#607089",
    "surface": "#F6F8FB",
    "line": "#DCE4EE",
    "whatsapp": "#25D366",
}

ESTILOS_PUBLICOS = f"""
<style>
:root {{
    --fm-navy: {COR["navy"]};
    --fm-navy-hover: {COR["navy_hover"]};
    --fm-gold: {COR["gold"]};
    --fm-red: {COR["red"]};
    --fm-ink: {COR["ink"]};
    --fm-muted: {COR["muted"]};
    --fm-surface: {COR["surface"]};
    --fm-line: {COR["line"]};
    --fm-whatsapp: {COR["whatsapp"]};
}}
.fm-marca {{ text-align: center; padding: 1rem 0 0.5rem; }}
.fm-marca span {{ font-size: 2.2rem; font-weight: 600; color: var(--color-text-primary); }}
.fm-btn {{
    display: inline-block; color: #FFFFFF; padding: 10px 20px; border-radius: 8px;
    text-decoration: none; font-weight: 600; margin: 4px 4px 4px 0;
}}
.fm-btn-navy {{ background: var(--fm-navy); }}
.fm-btn-navy:hover {{ background: var(--fm-navy-hover); }}
.fm-btn-whatsapp {{ background: var(--fm-whatsapp); }}
.fm-link {{ color: var(--fm-navy); }}
.fm-btn-grande {{ padding: 12px 22px; font-weight: 700; }}
.fm-voltar {{ text-align: center; margin-top: 20px; }}
.fm-restrito {{
    max-width: 720px; margin: 80px auto; padding: 32px; border: 1px solid #DDDDDD;
    border-radius: 14px; text-align: center; font-family: Arial, sans-serif;
}}
.fm-restrito h2 {{ margin-bottom: 10px; color: var(--fm-navy); }}
.fm-restrito p {{ font-size: 1rem; color: #333333; line-height: 1.5; }}
.fm-restrito .fm-acao {{ margin-top: 18px; }}
.fm-restrito .fm-nota {{ margin-top: 16px; color: #777777; font-size: 0.85rem; }}
</style>
"""


def injetar_estilos_publicos() -> None:
    """Injeta as variaveis e classes das telas publicas (uma vez por execucao)."""
    st.markdown(ESTILOS_PUBLICOS, unsafe_allow_html=True)


_SCRIPT_IDIOMA = """
<script>
// fm-idioma: ajusta lang/translate do documento principal
(function () {
    // Executa dentro do iframe do componente e ajusta o documento principal.
    try {
        var doc = window.parent.document;
        if (!doc.getElementById("fm-idioma-css")) {
            var st = doc.createElement("style");
            st.id = "fm-idioma-css";
            st.textContent = 'div[data-testid="stElementContainer"]:has(> iframe[srcdoc*="fm-idioma"]){display:none}';
            doc.head.appendChild(st);
        }
        doc.documentElement.setAttribute("lang", "pt-BR");
        doc.documentElement.setAttribute("translate", "no");
        if (doc.body) {
            doc.body.setAttribute("translate", "no");
            doc.body.classList.add("notranslate");
        }
    } catch (e) {
        /* Sem acesso ao documento pai: nada a fazer. */
    }
})();
</script>
"""




def definir_idioma_pagina() -> None:
    """Declara lang="pt-BR" na pagina (WCAG 3.1.1). Scripts em st.markdown nao executam;
    por isso o ajuste roda dentro de um componente. O contêiner dele e escondido para
    nao deixar espaco vazio (o script continua executando em iframe oculto)."""
    components.html(_SCRIPT_IDIOMA, height=0)
