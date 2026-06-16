"""
FielMordomo - ponto de entrada da aplicacao Streamlit.

Mantem as rotas publicas separadas da area autenticada e carrega os modulos
internos sob demanda para isolar falhas de telas secundarias.
"""

import base64
import html
import importlib
import logging
import os
import sys
from urllib.parse import urlsplit

import streamlit as st


LOGGER = logging.getLogger(__name__)
DOMINIO_OFICIAL = "https://fielmordomo.com.br"
DOMINIOS_PERMITIDOS_PADRAO = {
    "fielmordomo.com.br",
    "www.fielmordomo.com.br",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
}
PAGINAS_INSTITUCIONAIS = {
    "", "inicio", "sobre", "recursos", "contato", "privacidade", "termos",
    "atualizar-cadastro", "pedidos-oracao",
}
ROTA_LOGIN = "login"
TAMANHO_MAXIMO_LOGO = 5 * 1024 * 1024
MIMES_LOGO = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
PAGINAS_IGREJA = {
    "home": ("Inicio", "modules.home"),
    "cadastros": ("Membros", "modules.cadastros"),
    "lancamentos": ("Lancamentos", "modules.lancamentos"),
    "relatorios": ("Relatorios", "modules.relatorios"),
    "dashboard": ("Dashboard", "modules.dashboard"),
    "ebd": ("Escola Bíblica", "modules.ebd"),
    "orhafe": ("Círculo de Oração", "modules.orhafe"),
    "obreiros": ("Obreiros", "modules.obreiros"),
    "visitantes": ("Visitantes", "modules.visitantes"),
    "pedidos_oracao": ("Pedidos de Oracao", "modules.pedidos_oracao"),
    "tesoureiros": ("Tesoureiros", "modules.tesoureiros"),
    "aniversariantes": ("Aniversarios", "modules.aniversariantes"),
    "backup": ("Backup", "modules.backup"),
    "minha_conta": ("Minha conta", "modules.minha_conta"),
}
PAGINAS_TESOUREIRO = {
    "lancamentos": ("Lancamentos", "modules.lancamentos"),
    "cadastros": ("Membros", "modules.cadastros"),
    "relatorios": ("Relatorios", "modules.relatorios"),
}
PAGINAS_PASTOR_AUXILIAR = {
    "visitantes": ("Visitantes", "modules.visitantes"),
    "pedidos_oracao": ("Pedidos de Oracao", "modules.pedidos_oracao"),
    "dashboard": ("Dashboard", "modules.dashboard"),
    "ebd": ("Relatórios Escola Bíblica", "modules.ebd"),
    "orhafe": ("Relatórios Círculo de Oração", "modules.orhafe"),
    "aniversariantes": ("Aniversários", "modules.aniversariantes"),
}
PAGINAS_RECEPCAO = {
    "visitantes": ("Visitantes", "modules.visitantes"),
}
PAGINAS_EBD = {
    "ebd": ("Escola Bíblica", "modules.ebd"),
}


_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


st.set_page_config(
    page_title="FielMordomo",
    page_icon="FM",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _importar(caminho):
    return importlib.import_module(caminho)


def _repository():
    return _importar("data.repository")


def _auth():
    return _importar("modules.auth")


def _validar_contrato_auth(auth):
    funcoes_obrigatorias = ("tela_login", "modo_atual", "logout")
    ausentes = [
        nome for nome in funcoes_obrigatorias
        if not callable(getattr(auth, nome, None))
    ]
    if not ausentes:
        return
    LOGGER.error(
        "Modulo modules.auth incompativel. Funcoes ausentes: %s.",
        ", ".join(ausentes),
    )
    st.error(
        "A atualizacao do sistema esta incompleta. "
        "Publique tambem o arquivo modules/auth.py atualizado."
    )
    st.stop()


def _dominios_permitidos():
    adicionais = {
        host.strip().lower()
        for host in os.environ.get("FIELMORDOMO_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    }
    return DOMINIOS_PERMITIDOS_PADRAO | adicionais


def _host_atual():
    try:
        bruto = st.context.headers.get("host", "")
    except Exception:
        bruto = ""
    bruto = str(bruto or "").split(",", 1)[0].strip()
    if not bruto or any(c in bruto for c in "\r\n"):
        return ""
    try:
        return str(urlsplit(f"//{bruto}").hostname or "").strip().lower()
    except ValueError:
        return ""


def _bloquear_acesso_fora_do_dominio_oficial():
    """
    Camada complementar de apresentacao.

    A restricao efetiva de hosts deve ser configurada no proxy reverso ou no
    provedor de hospedagem, antes que a requisicao alcance o Streamlit.
    """
    host = _host_atual()
    if not host:
        return
    if host in _dominios_permitidos():
        return
    host_html = html.escape(host, quote=True)
    st.markdown(
        f"""
        <div style="max-width:720px;margin:80px auto;padding:32px;border:1px solid #ddd;
                    border-radius:14px;text-align:center;font-family:Arial,sans-serif;">
            <h2 style="margin-bottom:10px;color:#061B44;">Acesso restrito</h2>
            <p style="font-size:1rem;color:#333;line-height:1.5;">
                O FielMordomo deve ser acessado somente pelo dominio oficial.
            </p>
            <p style="margin-top:18px;">
                <a href="{DOMINIO_OFICIAL}" target="_self"
                   style="display:inline-block;background:#061B44;color:white;text-decoration:none;
                          padding:12px 22px;border-radius:8px;font-weight:700;">
                    Abrir FielMordomo
                </a>
            </p>
            <p style="margin-top:16px;color:#777;font-size:0.85rem;">
                Dominio detectado: {host_html}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


def _pagina_publica_atual():
    pagina = st.query_params.get("pagina", "inicio")
    if isinstance(pagina, list):
        pagina = pagina[0] if pagina else "inicio"
    return str(pagina or "inicio").strip().lower()


def _resolver_rota_publica():
    pagina = _pagina_publica_atual()
    if pagina in PAGINAS_INSTITUCIONAIS:
        _importar("modules.institucional").render_institucional()
        st.stop()
    if pagina == ROTA_LOGIN:
        return
    st.error("Pagina nao encontrada.")
    st.markdown('[Voltar para o inicio](?pagina=inicio)')
    st.stop()


def _esc(valor):
    return html.escape(str(valor if valor is not None else ""), quote=True)


def _injetar_css():
    st.markdown(
        """
        <meta name="google" content="notranslate">
        <meta name="translate" content="no">
        <style>
        html,body,.stApp,[data-testid="stAppViewContainer"] {
            -webkit-locale:"pt-BR";
        }
        .stApp,[data-testid="stAppViewContainer"],
        section[data-testid="stSidebar"],
        [data-testid="stSidebarContent"],
        [data-testid="stMarkdownContainer"],
        label,button,input,textarea,select {
            translate:no;
        }
        .notranslate { translate:no; }
        header[data-testid="stHeader"] {background:transparent!important;height:3rem!important}
        #MainMenu,footer {display:none!important}
        [data-testid="stSidebarCollapsedControl"] {display:flex!important;visibility:visible!important;
            opacity:1!important;position:fixed!important;top:12px!important;left:12px!important;
            z-index:999999!important;background:#061B44!important;border-radius:10px!important;
            padding:6px!important;box-shadow:0 2px 10px rgba(0,0,0,.30)!important}
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stSidebarCollapsedControl"] svg {color:white!important;fill:white!important}
        button[kind="header"] {color:white!important;background:#061B44!important;border-radius:10px!important}
        button[kind="header"] svg {color:white!important;fill:white!important}
        section[data-testid="stSidebar"] {background:linear-gradient(180deg,#061B44 0%,#0A0A0A 100%)!important}
        section[data-testid="stSidebar"] * {color:white!important}
        section[data-testid="stSidebar"] .stButton button {width:100%;background:transparent!important;
            border:none!important;color:rgba(255,255,255,.92)!important;text-align:left!important;
            padding:10px 14px!important;font-size:.95rem!important;border-radius:8px!important;
            margin-bottom:2px!important;transition:.2s}
        section[data-testid="stSidebar"] .stButton button:hover {background:rgba(212,175,55,.18)!important;
            color:#D4AF37!important}
        section[data-testid="stSidebar"] .stButton button[kind="primary"] {
            background:rgba(212,175,55,.25)!important;color:#D4AF37!important;font-weight:700!important;
            border-left:3px solid #D4AF37!important}
        .sidebar-logo {text-align:center;padding:10px 0 16px;border-bottom:1px solid rgba(212,175,55,.35);
            margin-bottom:14px}
        .sidebar-logo img {max-width:140px;max-height:90px;object-fit:contain}
        .sidebar-info {text-align:center;font-size:.78rem;color:rgba(255,255,255,.85)!important;
            margin:0 0 14px;padding:0 6px}
        .sidebar-info b {color:#D4AF37!important}
        .sidebar-info .plano {font-size:.68rem;color:rgba(255,255,255,.65)!important;margin-top:2px}
        .block-container {padding-top:3.5rem!important;padding-left:2rem!important;
            padding-right:2rem!important;max-width:100%!important}
        </style>
        <script>
        (function () {
            const root = window.parent && window.parent.document
                ? window.parent.document
                : document;
            root.documentElement.setAttribute("lang", "pt-BR");
            root.documentElement.setAttribute("translate", "no");
            root.body && root.body.setAttribute("translate", "no");
            root.body && root.body.classList.add("notranslate");
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


def _img_b64(dados, extensao):
    extensao = str(extensao or "").strip().lower().replace(".", "")
    mime = MIMES_LOGO.get(extensao)
    if not mime:
        raise ValueError("Formato de logo nao permitido.")
    if not isinstance(dados, (bytes, bytearray, memoryview)):
        raise TypeError("Logo invalido.")
    dados = bytes(dados)
    if not dados or len(dados) > TAMANHO_MAXIMO_LOGO:
        raise ValueError("Logo invalido ou maior que 5 MB.")
    return f"data:{mime};base64,{base64.b64encode(dados).decode('ascii')}"


def _logo_sidebar(slug=None):
    repo = _repository()
    if slug:
        return (
            repo.obter_logo_sidebar_igreja(slug)
            or repo.obter_logo_sidebar_sistema()
            or repo.obter_logo_igreja(slug)
            or repo.obter_logo_sistema()
        )
    return repo.obter_logo_sidebar_sistema() or repo.obter_logo_sistema()


def _render_logo_sidebar(slug=None):
    try:
        logo = _logo_sidebar(slug)
        if logo:
            dados, extensao = logo
            src = _img_b64(dados, extensao)
            st.markdown(
                f'<div class="sidebar-logo"><img src="{src}" alt="FielMordomo"></div>',
                unsafe_allow_html=True,
            )
            return
    except Exception:
        LOGGER.exception("Nao foi possivel renderizar o logo da sidebar.")
    st.markdown(
        '<div class="sidebar-logo" style="font-size:1.4rem;font-weight:700;color:white">'
        "FielMordomo</div>",
        unsafe_allow_html=True,
    )


def _sidebar_igreja(pagina_atual, igreja):
    with st.sidebar:
        _render_logo_sidebar(igreja.get("slug", ""))
        st.markdown(
            '<div class="sidebar-info">'
            f'<b>{_esc(igreja.get("nome", "FielMordomo"))}</b>'
            f'<div class="plano">Plano {_esc(str(igreja.get("plano", "")).capitalize())}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        for chave, (rotulo, _) in PAGINAS_IGREJA.items():
            if st.button(
                rotulo,
                key=f"sb_{chave}",
                use_container_width=True,
                type="primary" if pagina_atual == chave else "secondary",
            ):
                st.session_state["pagina"] = chave
                st.rerun()
        st.divider()
        if st.button("Sair", key="sb_sair", use_container_width=True):
            _auth().logout()


def _sidebar_admin():
    with st.sidebar:
        _render_logo_sidebar()
        st.markdown(
            '<div class="sidebar-info"><b>Administrador</b>'
            '<div class="plano">Painel do sistema</div></div>',
            unsafe_allow_html=True,
        )
        st.divider()
        if st.button("Sair", key="sb_sair_admin", use_container_width=True):
            _auth().logout()


def _sidebar_tesoureiro(pagina_atual, igreja, tesoureiro):
    with st.sidebar:
        _render_logo_sidebar(igreja.get("slug", ""))
        st.markdown(
            '<div class="sidebar-info">'
            f'<b>{_esc(tesoureiro.get("nome", "Tesoureiro"))}</b>'
            '<div class="plano">Acesso restrito operacional</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        for chave, (rotulo, _) in PAGINAS_TESOUREIRO.items():
            if st.button(
                rotulo,
                key=f"sb_tesoureiro_{chave}",
                use_container_width=True,
                type="primary" if pagina_atual == chave else "secondary",
            ):
                st.session_state["pagina"] = chave
                st.rerun()
        st.divider()
        if st.button("Sair", key="sb_sair_tesoureiro", use_container_width=True):
            _auth().logout()


def _sidebar_secretario_ebd(igreja, secretario):
    perfil = "Secretario geral" if secretario.get("perfil") == "geral" else "Secretario de classe"
    classe = secretario.get("classe") or "Escola Bíblica"
    with st.sidebar:
        _render_logo_sidebar(igreja.get("slug", ""))
        st.markdown(
            '<div class="sidebar-info">'
            f'<b>{_esc(secretario.get("nome", "Secretario Escola Bíblica"))}</b>'
            f'<div class="plano">{_esc(perfil)} - {_esc(classe)}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Escola Bíblica", key="sb_secretario_ebd", use_container_width=True, type="primary"):
            st.session_state["pagina"] = "ebd"
            st.rerun()
        st.divider()
        if st.button("Sair", key="sb_sair_secretario_ebd", use_container_width=True):
            _auth().logout()


def _sidebar_secretaria_orhafe(igreja, secretaria):
    perfil = "Secretaria geral" if secretaria.get("perfil") == "geral" else "Secretaria de chamada"
    with st.sidebar:
        _render_logo_sidebar(igreja.get("slug", ""))
        st.markdown(
            '<div class="sidebar-info">'
            f'<b>{_esc(secretaria.get("nome", "Secretaria Círculo de Oração"))}</b>'
            f'<div class="plano">{_esc(perfil)} - Círculo de Oração</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Círculo de Oração", key="sb_secretaria_orhafe", use_container_width=True, type="primary"):
            st.session_state["pagina"] = "orhafe"
            st.rerun()
        st.divider()
        if st.button("Sair", key="sb_sair_secretaria_orhafe", use_container_width=True):
            _auth().logout()


def _sidebar_pastor_auxiliar(pagina_atual, igreja, pastor):
    with st.sidebar:
        _render_logo_sidebar(igreja.get("slug", ""))
        st.markdown(
            '<div class="sidebar-info">'
            f'<b>{_esc(pastor.get("nome", "Pastor Auxiliar"))}</b>'
            '<div class="plano">Acesso restrito pastoral</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        for chave, (rotulo, _) in PAGINAS_PASTOR_AUXILIAR.items():
            if st.button(
                rotulo,
                key=f"sb_pastor_auxiliar_{chave}",
                use_container_width=True,
                type="primary" if pagina_atual == chave else "secondary",
            ):
                st.session_state["pagina"] = chave
                st.rerun()
        st.divider()
        if st.button("Sair", key="sb_sair_pastor_auxiliar", use_container_width=True):
            _auth().logout()


def _sidebar_recepcao(igreja, recepcao):
    with st.sidebar:
        _render_logo_sidebar(igreja.get("slug", ""))
        st.markdown(
            '<div class="sidebar-info">'
            f'<b>{_esc(recepcao.get("nome", "Recepção"))}</b>'
            '<div class="plano">Acesso restrito a visitantes</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Visitantes", key="sb_recepcao_visitantes", use_container_width=True, type="primary"):
            st.session_state["pagina"] = "visitantes"
            st.rerun()
        st.divider()
        if st.button("Sair", key="sb_sair_recepcao", use_container_width=True):
            _auth().logout()


def _renderizar_admin():
    _sidebar_admin()
    try:
        _importar("admin.painel").render()
    except Exception:
        LOGGER.exception("Falha ao carregar o painel administrativo.")
        st.error("Nao foi possivel carregar o painel administrativo. Consulte o log do sistema.")


def _renderizar_igreja():
    igreja = st.session_state.get("igreja", {})
    if not isinstance(igreja, dict) or not igreja.get("slug"):
        st.error("Sessao invalida. Faca login novamente.")
        if st.button("Voltar ao login"):
            _auth().logout()
        return
    pagina = st.session_state.get("pagina", "home")
    if pagina not in PAGINAS_IGREJA:
        pagina = "home"
        st.session_state["pagina"] = pagina
    _sidebar_igreja(pagina, igreja)
    _, caminho_modulo = PAGINAS_IGREJA[pagina]
    try:
        _importar(caminho_modulo).render()
    except Exception as ex:
        LOGGER.exception("Falha ao carregar a pagina %s.", pagina)
        st.error(
            "Nao foi possivel carregar esta pagina. "
            f"Tipo do erro: {type(ex).__name__}. Consulte o log do sistema."
        )


def _renderizar_tesoureiro():
    igreja = st.session_state.get("igreja", {})
    tesoureiro = st.session_state.get("tesoureiro", {})
    if not isinstance(igreja, dict) or not igreja.get("slug") or not isinstance(tesoureiro, dict):
        st.error("Sessao invalida. Faca login novamente.")
        if st.button("Voltar ao login"):
            _auth().logout()
        return
    pagina = st.session_state.get("pagina", "lancamentos")
    if pagina not in PAGINAS_TESOUREIRO:
        pagina = "lancamentos"
        st.session_state["pagina"] = pagina
    _sidebar_tesoureiro(pagina, igreja, tesoureiro)
    _, caminho_modulo = PAGINAS_TESOUREIRO[pagina]
    try:
        _importar(caminho_modulo).render()
    except Exception as ex:
        LOGGER.exception("Falha ao carregar a pagina %s para o tesoureiro.", pagina)
        st.error(
            "Nao foi possivel carregar esta pagina. "
            f"Tipo do erro: {type(ex).__name__}. Consulte o log do sistema."
        )


def _renderizar_secretario_ebd():
    igreja = st.session_state.get("igreja", {})
    secretario = st.session_state.get("secretario_ebd", {})
    if not isinstance(igreja, dict) or not igreja.get("slug") or not isinstance(secretario, dict):
        st.error("Sessao invalida. Faca login novamente.")
        if st.button("Voltar ao login"):
            _auth().logout()
        return
    st.session_state["pagina"] = "ebd"
    _sidebar_secretario_ebd(igreja, secretario)
    try:
        _importar("modules.ebd").render()
    except Exception as ex:
        LOGGER.exception("Falha ao carregar Escola Bíblica para secretario.")
        st.error(
            "Nao foi possivel carregar esta pagina. "
            f"Tipo do erro: {type(ex).__name__}. Consulte o log do sistema."
        )


def _renderizar_secretaria_orhafe():
    igreja = st.session_state.get("igreja", {})
    secretaria = st.session_state.get("secretaria_orhafe", {})
    if not isinstance(igreja, dict) or not igreja.get("slug") or not isinstance(secretaria, dict):
        st.error("Sessao invalida. Faca login novamente.")
        if st.button("Voltar ao login"):
            _auth().logout()
        return
    st.session_state["pagina"] = "orhafe"
    _sidebar_secretaria_orhafe(igreja, secretaria)
    try:
        _importar("modules.orhafe").render()
    except Exception as ex:
        LOGGER.exception("Falha ao carregar Círculo de Oração para secretaria.")
        st.error(
            "Nao foi possivel carregar esta pagina. "
            f"Tipo do erro: {type(ex).__name__}. Consulte o log do sistema."
        )


def _renderizar_pastor_auxiliar():
    igreja = st.session_state.get("igreja", {})
    pastor = st.session_state.get("pastor_auxiliar", {})
    if not isinstance(igreja, dict) or not igreja.get("slug") or not isinstance(pastor, dict):
        st.error("Sessao invalida. Faca login novamente.")
        if st.button("Voltar ao login"):
            _auth().logout()
        return
    pagina = st.session_state.get("pagina", "visitantes")
    if pagina not in PAGINAS_PASTOR_AUXILIAR:
        pagina = "visitantes"
        st.session_state["pagina"] = pagina
    _sidebar_pastor_auxiliar(pagina, igreja, pastor)
    _, caminho_modulo = PAGINAS_PASTOR_AUXILIAR[pagina]
    try:
        _importar(caminho_modulo).render()
    except Exception as ex:
        LOGGER.exception("Falha ao carregar a pagina %s para pastor auxiliar.", pagina)
        st.error(
            "Nao foi possivel carregar esta pagina. "
            f"Tipo do erro: {type(ex).__name__}. Consulte o log do sistema."
        )


def _renderizar_recepcao():
    igreja = st.session_state.get("igreja", {})
    recepcao = st.session_state.get("recepcao", {})
    if not isinstance(igreja, dict) or not igreja.get("slug") or not isinstance(recepcao, dict):
        st.error("Sessao invalida. Faca login novamente.")
        if st.button("Voltar ao login"):
            _auth().logout()
        return
    st.session_state["pagina"] = "visitantes"
    _sidebar_recepcao(igreja, recepcao)
    try:
        _importar("modules.visitantes").render()
    except Exception as ex:
        LOGGER.exception("Falha ao carregar visitantes para recepcao.")
        st.error(
            "Nao foi possivel carregar esta pagina. "
            f"Tipo do erro: {type(ex).__name__}. Consulte o log do sistema."
        )


def main():
    _bloquear_acesso_fora_do_dominio_oficial()
    _resolver_rota_publica()
    auth = _auth()
    _validar_contrato_auth(auth)
    if not auth.tela_login():
        st.stop()
    _injetar_css()
    modo = auth.modo_atual()
    if modo == "admin":
        _renderizar_admin()
    elif modo == "igreja":
        _renderizar_igreja()
    elif modo == "tesoureiro":
        _renderizar_tesoureiro()
    elif modo == "secretario_ebd":
        _renderizar_secretario_ebd()
    elif modo == "secretaria_orhafe":
        _renderizar_secretaria_orhafe()
    elif modo == "pastor_auxiliar":
        _renderizar_pastor_auxiliar()
    elif modo == "recepcao":
        _renderizar_recepcao()
    else:
        st.error("Modo de acesso invalido. Faca login novamente.")
        if st.button("Sair"):
            auth.logout()


if __name__ == "__main__":
    main()
