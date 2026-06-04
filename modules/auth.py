"""
Autenticacao do FielMordomo.
"""

import html
import re
import urllib.parse
import streamlit as st

from data.repository import (
    autenticar_super_admin, autenticar_igreja, autenticar_tesoureiro,
    autenticar_ebd_secretario,
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


def _iniciar_sessao(modo: str, igreja=None, tesoureiro=None, secretario_ebd=None):
    _limpar_sessao()
    st.session_state["autenticado"] = True
    st.session_state["modo"] = modo
    if igreja is not None:
        st.session_state["igreja"] = igreja
    if tesoureiro is not None:
        st.session_state["tesoureiro"] = tesoureiro
    if secretario_ebd is not None:
        st.session_state["secretario_ebd"] = secretario_ebd


def _limpar_sessao():
    for key in (
        "autenticado", "modo", "igreja", "tesoureiro", "secretario_ebd",
        "pagina", "mostrar_recuperacao",
    ):
        st.session_state.pop(key, None)
    for key in list(st.session_state.keys()):
        if key.startswith(("df_", "lote_", "nl_counter_", "dashboard_", "_auth_", "_edit_", "_del_")):
            st.session_state.pop(key, None)


def _exibir_logo_sistema():
    resultado = obter_logo_sistema()
    if resultado:
        dados, ext = resultado
        st.image(dados, width=180)
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

    _, col, _ = st.columns([1, 2, 1])
    with col:
        _exibir_logo_sistema()
        st.markdown(
            "<p style='text-align:center;color:var(--color-text-secondary);"
            "font-size:0.9rem;margin-bottom:1.5rem'>"
            "Gestão Financeira para Igrejas</p>",
            unsafe_allow_html=True,
        )

        # Modo recuperacao de senha
        if st.session_state.get("mostrar_recuperacao"):
            _mostrar_recuperacao_senha()
            return False

        modo = st.radio(
            "Tipo de acesso",
            ["Igreja", "Tesoureiro", "EBD", "Administrador do sistema"],
            horizontal=True,
            label_visibility="collapsed",
        )
        st.divider()

        if modo == "Igreja":
            _login_igreja()
        elif modo == "Tesoureiro":
            _login_tesoureiro()
        elif modo == "EBD":
            _login_ebd()
        else:
            _login_admin()

    return False


def _login_igreja():
    with st.form("form_login_igreja"):
        st.markdown("#### Acesso da igreja")
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


def _login_ebd():
    with st.form("form_login_ebd"):
        st.markdown("#### Acesso da EBD")
        st.caption("Secretario de classe acessa somente chamada. Secretario geral acessa todo o modulo EBD.")
        slug = st.text_input("Identificador da igreja", placeholder="ex: ad-serrinha")
        usuario = st.text_input("Usuario da EBD")
        senha = st.text_input("Senha", type="password")

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
                st.error("Identificador, usuario ou senha incorretos, ou acesso inativo.")


def logout():
    _limpar_sessao()
    st.rerun()


def exigir_autenticacao() -> bool:
    return st.session_state.get("autenticado", False)


def modo_atual() -> str:
    return st.session_state.get("modo", "")
