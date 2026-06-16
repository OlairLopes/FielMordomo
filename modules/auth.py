"""
Autenticacao do FielMordomo.
"""

import html
import re
import urllib.parse
import streamlit as st

from data.repository import (
    autenticar_super_admin, autenticar_igreja, autenticar_tesoureiro,
    autenticar_ebd_secretario, autenticar_orhafe_secretaria,
    autenticar_pastor_auxiliar, autenticar_recepcao,
    inicializar_master, obter_logo_sistema, obter_config,
)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalizar_email(email: str) -> str:
    email = str(email or "").strip()
    return email if EMAIL_RE.fullmatch(email) else ""


def _normalizar_whatsapp(numero: str) -> str:
    numero = "".join(c for c in str(numero or "") if c.isdigit())
    if numero and not numero.startswith("55"):
        numero = f"55{numero}"
    return numero


def _iniciar_sessao(
    modo: str,
    igreja=None,
    tesoureiro=None,
    secretario_ebd=None,
    secretaria_orhafe=None,
    pastor_auxiliar=None,
    recepcao=None,
):
    _limpar_sessao()
    st.session_state["autenticado"] = True
    st.session_state["modo"] = modo
    if igreja is not None:
        st.session_state["igreja"] = igreja
    if tesoureiro is not None:
        st.session_state["tesoureiro"] = tesoureiro
    if secretario_ebd is not None:
        st.session_state["secretario_ebd"] = secretario_ebd
    if secretaria_orhafe is not None:
        st.session_state["secretaria_orhafe"] = secretaria_orhafe
    if pastor_auxiliar is not None:
        st.session_state["pastor_auxiliar"] = pastor_auxiliar
    if recepcao is not None:
        st.session_state["recepcao"] = recepcao


def _limpar_sessao():
    for key in (
        "autenticado", "modo", "igreja", "tesoureiro", "secretario_ebd",
        "secretaria_orhafe", "pastor_auxiliar", "recepcao",
        "pagina", "mostrar_recuperacao",
    ):
        st.session_state.pop(key, None)
    for key in list(st.session_state.keys()):
        if key.startswith(("df_", "lote_", "nl_counter_", "dashboard_", "_auth_", "_edit_", "_del_")):
            st.session_state.pop(key, None)


def _exibir_logo_sistema():
    resultado = obter_logo_sistema()
    if resultado:
        dados, _ext = resultado
        st.image(dados, width=150)
    else:
        st.markdown(
            """
            <div style="text-align:center;padding:1rem 0 0.5rem">
              <span style="font-size:2.2rem;font-weight:600;
                           color:var(--color-text-primary)">
                FielMordomo
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )


LOGIN_OPCOES = [
    ("Gestor/Pastor", "Acesso principal", "Gestao completa da igreja"),
    ("Pastor Auxiliar", "Acesso pastoral", "Visitantes, pedidos e relatorios permitidos"),
    ("Tesoureiro", "Financeiro", "Lancamentos, membros e relatorios"),
    ("Recepcao", "Visitantes", "Registro de visitantes"),
    ("Escola Biblica", "Secretaria", "Chamada e gestao da Escola Biblica"),
    ("Circulo de Oracao", "Secretaria", "Chamada e relatorios do Circulo de Oracao"),
    ("Administrador do sistema", "Admin", "Painel geral da plataforma"),
]


def _login_css():
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 2.2rem !important;
                max-width: 1180px !important;
            }
            div[data-testid="stForm"] {
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 18px;
                padding: 1.4rem 1.5rem 1.5rem;
                box-shadow: 0 20px 45px rgba(6, 27, 68, .10);
            }
            .fm-login-side {
                background: linear-gradient(180deg, #061B44 0%, #0A0A0A 100%);
                border-radius: 24px;
                padding: 24px 20px;
                min-height: 680px;
                box-shadow: 0 24px 54px rgba(6, 27, 68, .28);
            }
            .fm-login-side * {
                color: #FFFFFF;
            }
            .fm-login-title {
                font-size: 1.25rem;
                font-weight: 800;
                margin-top: 12px;
                text-align: center;
            }
            .fm-login-subtitle {
                color: rgba(255,255,255,.72) !important;
                font-size: .86rem;
                text-align: center;
                margin-bottom: 20px;
            }
            .fm-login-card {
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 24px;
                padding: 30px;
                min-height: 680px;
                box-shadow: 0 20px 45px rgba(6, 27, 68, .08);
            }
            .fm-login-heading {
                color: #061B44;
                font-size: 1.75rem;
                font-weight: 850;
                margin-bottom: 6px;
            }
            .fm-login-muted {
                color: #64748B;
                font-size: .95rem;
                margin-bottom: 20px;
            }
            .fm-login-side div[data-testid="stImage"] {
                display: flex;
                justify-content: center;
            }
            .fm-login-side .stButton button {
                width: 100%;
                border: none !important;
                border-radius: 13px !important;
                padding: .78rem .9rem !important;
                margin-bottom: .28rem !important;
                text-align: left !important;
                color: rgba(255,255,255,.92) !important;
                background: rgba(255,255,255,.06) !important;
                font-weight: 700 !important;
            }
            .fm-login-side .stButton button:hover {
                background: rgba(212, 175, 55, .22) !important;
                color: #D4AF37 !important;
            }
            .fm-login-side .stButton button[kind="primary"] {
                background: rgba(212, 175, 55, .28) !important;
                color: #D4AF37 !important;
                border-left: 4px solid #D4AF37 !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _modo_login_atual():
    modos = [item[0] for item in LOGIN_OPCOES]
    modo = st.session_state.get("login_modo", modos[0])
    if modo not in modos:
        modo = modos[0]
    st.session_state["login_modo"] = modo
    return modo


def _selecionar_modo_login(modo):
    st.session_state["login_modo"] = modo
    st.session_state["mostrar_recuperacao"] = False
    st.rerun()


def _sidebar_login(modo_atual):
    st.markdown('<div class="fm-login-side">', unsafe_allow_html=True)
    _exibir_logo_sistema()
    st.markdown(
        """
        <div class="fm-login-title">FielMordomo</div>
        <div class="fm-login-subtitle">Gestao Financeira para Igrejas</div>
        """,
        unsafe_allow_html=True,
    )
    for modo, titulo, descricao in LOGIN_OPCOES:
        label = f"{titulo} | {modo}"
        ajuda = descricao
        if st.button(
            label,
            key=f"login_modo_{modo}",
            use_container_width=True,
            type="primary" if modo == modo_atual else "secondary",
            help=ajuda,
        ):
            _selecionar_modo_login(modo)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_login_por_modo(modo):
    if modo == "Gestor/Pastor":
        _login_igreja()
    elif modo == "Pastor Auxiliar":
        _login_pastor_auxiliar()
    elif modo == "Tesoureiro":
        _login_tesoureiro()
    elif modo == "Recepcao":
        _login_recepcao()
    elif modo == "Escola Biblica":
        _login_ebd()
    elif modo == "Circulo de Oracao":
        _login_orhafe()
    else:
        _login_admin()


def _mostrar_recuperacao_senha():
    """Tela com contato do admin para recuperacao de senha."""
    email_admin  = _normalizar_email(obter_config("contato_email", "admin@fielmordomo.com"))
    wpp_admin    = _normalizar_whatsapp(obter_config("contato_whatsapp", ""))
    mensagem     = obter_config(
        "contato_mensagem",
        "Entre em contato com o administrador do sistema para redefinir sua senha."
    )

    st.markdown("### 🔐 Recuperar senha")
    st.info(mensagem)

    st.markdown("**Canais de contato:**")

    if email_admin:
        assunto = urllib.parse.quote("Solicitacao de redefinicao de senha - FielMordomo")
        corpo = urllib.parse.quote(
            "Ola,\n\n"
            "Solicito a redefinicao de senha da minha igreja no sistema FielMordomo.\n\n"
            "Identificador da igreja (slug): \n"
            "Nome da igreja: \n"
            "Motivo: \n\n"
            "Obrigado!"
        )
        email_link = urllib.parse.quote(email_admin, safe="@._+-")
        link_email = html.escape(
            f"mailto:{email_link}?subject={assunto}&body={corpo}", quote=True
        )
        st.markdown(
            f'<a href="{link_email}" '
            f'style="display:inline-block;background:#0F6E56;color:white;'
            f'padding:10px 20px;border-radius:8px;text-decoration:none;'
            f'font-weight:600;margin:4px 4px 4px 0">'
            f'📧 Enviar e-mail ao administrador</a>',
            unsafe_allow_html=True,
        )
        st.caption(f"E-mail: **{email_admin}**")

    if wpp_admin:
        msg_wpp = urllib.parse.quote(
            "Ola! Preciso de ajuda para redefinir a senha da minha igreja no FielMordomo. "
            "Pode me ajudar?"
        )
        wpp_link = html.escape(f"https://wa.me/{wpp_admin}?text={msg_wpp}", quote=True)
        st.markdown(
            f'<a href="{wpp_link}" target="_blank" rel="noopener noreferrer" '
            f'style="display:inline-block;background:#25D366;color:white;'
            f'padding:10px 20px;border-radius:8px;text-decoration:none;'
            f'font-weight:600;margin:4px 4px 4px 0">'
            f'💬 Falar pelo WhatsApp</a>',
            unsafe_allow_html=True,
        )
        st.caption(f"WhatsApp: **{wpp_admin}**")

    st.divider()

    if st.button("← Voltar para o login", use_container_width=True):
        st.session_state["mostrar_recuperacao"] = False
        st.rerun()


def tela_login():
    if st.session_state.get("autenticado"):
        return True

    inicializar_master()
    _login_css()
    modo = _modo_login_atual()

    col_side, col_main = st.columns([0.95, 2.05], gap="large")
    with col_side:
        _sidebar_login(modo)

    with col_main:
        st.markdown('<div class="fm-login-card">', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="fm-login-heading">Acessar Sistema</div>
            <div class="fm-login-muted">
                Escolha o perfil de acesso na barra lateral e informe suas credenciais.
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.get("mostrar_recuperacao"):
            _mostrar_recuperacao_senha()
            st.markdown("</div>", unsafe_allow_html=True)
            return False

        _render_login_por_modo(modo)
        st.markdown("</div>", unsafe_allow_html=True)

    return False

def _login_igreja():
    with st.form("form_login_igreja"):
        st.markdown("#### Acesso do Gestor/Pastor")
        slug  = st.text_input("Identificador da igreja", placeholder="ex: ad-serrinha")
        senha = st.text_input("Senha", type="password")

        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            slug = slug.strip().lower()
            if not slug or not senha:
                st.error("Preencha todos os campos.")
                return
            igreja = autenticar_igreja(slug, senha)
            if igreja:
                _iniciar_sessao("igreja", igreja)
                st.toast(f"Bem-vindo, {igreja['nome']}!")
                st.rerun()
            else:
                st.error("Identificador ou senha incorretos, ou igreja inativa.")

    # Botao "Esqueci minha senha"
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔐 Esqueci minha senha", use_container_width=True, key="btn_esqueci"):
            st.session_state["mostrar_recuperacao"] = True
            st.rerun()
    with col2:
        st.caption("Nao tem acesso? Entre em contato com o administrador.")


def _login_admin():
    with st.form("form_login_admin"):
        st.markdown("#### Administrador do sistema")
        usuario = st.text_input("Usuario")
        senha   = st.text_input("Senha", type="password")

        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            usuario = usuario.strip()
            if not usuario or not senha:
                st.error("Preencha todos os campos.")
                return
            if autenticar_super_admin(usuario, senha):
                _iniciar_sessao("admin")
                st.toast("Acesso de administrador autorizado.")
                st.rerun()
            else:
                st.error("Credenciais invalidas.")


def _login_tesoureiro():
    with st.form("form_login_tesoureiro"):
        st.markdown("#### Acesso restrito do tesoureiro")
        st.caption("Este acesso permite somente registrar e consultar lancamentos.")
        slug = st.text_input("Identificador da igreja", placeholder="ex: ad-serrinha")
        usuario = st.text_input("Usuario do tesoureiro")
        senha = st.text_input("Senha", type="password")

        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            slug = slug.strip().lower()
            usuario = usuario.strip().lower()
            if not slug or not usuario or not senha:
                st.error("Preencha todos os campos.")
                return
            acesso = autenticar_tesoureiro(slug, usuario, senha)
            if acesso:
                _iniciar_sessao(
                    "tesoureiro",
                    igreja=acesso["igreja"],
                    tesoureiro=acesso["tesoureiro"],
                )
                st.toast(f"Bem-vindo, {acesso['tesoureiro']['nome']}!")
                st.rerun()
            else:
                st.error("Identificador, usuario ou senha incorretos, ou acesso inativo.")


def _login_pastor_auxiliar():
    with st.form("form_login_pastor_auxiliar"):
        st.markdown("#### Acesso do Pastor Auxiliar")
        st.caption("Acesso restrito a visitantes, aniversários, relatórios ministeriais e dashboard limitado.")
        slug = st.text_input("Identificador da igreja", placeholder="ex: ad-serrinha")
        usuario = st.text_input("Usuario do Pastor Auxiliar")
        senha = st.text_input("Senha", type="password")

        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            slug = slug.strip().lower()
            usuario = usuario.strip().lower()
            if not slug or not usuario or not senha:
                st.error("Preencha todos os campos.")
                return
            acesso = autenticar_pastor_auxiliar(slug, usuario, senha)
            if acesso:
                _iniciar_sessao(
                    "pastor_auxiliar",
                    igreja=acesso["igreja"],
                    pastor_auxiliar=acesso["pastor_auxiliar"],
                )
                st.toast(f"Bem-vindo, {acesso['pastor_auxiliar']['nome']}!")
                st.rerun()
            else:
                st.error("Identificador, usuario ou senha incorretos, ou acesso inativo.")


def _login_recepcao():
    with st.form("form_login_recepcao"):
        st.markdown("#### Acesso da Recepção")
        st.caption("Acesso restrito somente ao registro de visitantes.")
        slug = st.text_input("Identificador da igreja", placeholder="ex: ad-serrinha")
        usuario = st.text_input("Usuario da Recepção")
        senha = st.text_input("PIN de 4 digitos", type="password", max_chars=4)

        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            slug = slug.strip().lower()
            usuario = usuario.strip().lower()
            if not slug or not usuario or not senha:
                st.error("Preencha todos os campos.")
                return
            acesso = autenticar_recepcao(slug, usuario, senha)
            if acesso:
                _iniciar_sessao(
                    "recepcao",
                    igreja=acesso["igreja"],
                    recepcao=acesso["recepcao"],
                )
                st.toast(f"Bem-vindo, {acesso['recepcao']['nome']}!")
                st.rerun()
            else:
                st.error("Identificador, usuario ou PIN incorretos, ou acesso inativo.")


def _login_ebd():
    with st.form("form_login_ebd"):
        st.markdown("#### Acesso da Escola Bíblica")
        st.caption("Secretario de classe acessa somente chamada. Secretario geral acessa todo o modulo Escola Bíblica.")
        slug = st.text_input("Identificador da igreja", placeholder="ex: ad-serrinha")
        usuario = st.text_input("Usuario da Escola Bíblica")
        senha = st.text_input("PIN de 4 digitos", type="password", max_chars=4)

        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            slug = slug.strip().lower()
            usuario = usuario.strip().lower()
            if not slug or not usuario or not senha:
                st.error("Preencha todos os campos.")
                return
            acesso = autenticar_ebd_secretario(slug, usuario, senha)
            if acesso:
                _iniciar_sessao(
                    "secretario_ebd",
                    igreja=acesso["igreja"],
                    secretario_ebd=acesso["secretario_ebd"],
                )
                st.toast(f"Bem-vindo, {acesso['secretario_ebd']['nome']}!")
                st.rerun()
            else:
                st.error("Identificador, usuario ou PIN incorretos, ou acesso inativo.")


def _login_orhafe():
    with st.form("form_login_orhafe"):
        st.markdown("#### Acesso do Círculo de Oração")
        st.caption("Secretaria de chamada acessa somente a chamada. Secretaria geral acessa todo o módulo Círculo de Oração.")
        slug = st.text_input("Identificador da igreja", placeholder="ex: ad-serrinha")
        usuario = st.text_input("Usuário do Círculo de Oração")
        senha = st.text_input("PIN de 4 digitos", type="password", max_chars=4)

        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            slug = slug.strip().lower()
            usuario = usuario.strip().lower()
            if not slug or not usuario or not senha:
                st.error("Preencha todos os campos.")
                return
            acesso = autenticar_orhafe_secretaria(slug, usuario, senha)
            if acesso:
                _iniciar_sessao(
                    "secretaria_orhafe",
                    igreja=acesso["igreja"],
                    secretaria_orhafe=acesso["secretaria_orhafe"],
                )
                st.toast(f"Bem-vinda, {acesso['secretaria_orhafe']['nome']}!")
                st.rerun()
            else:
                st.error("Identificador, usuario ou PIN incorretos, ou acesso inativo.")


def logout():
    _limpar_sessao()
    st.rerun()


def exigir_autenticacao() -> bool:
    return st.session_state.get("autenticado", False)


def modo_atual() -> str:
    return st.session_state.get("modo", "")
