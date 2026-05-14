"""
Autenticacao do FielMordomo.
"""

import urllib.parse
import streamlit as st

from data.repository import (
    autenticar_super_admin, autenticar_igreja,
    inicializar_master, obter_logo_sistema, obter_config,
)


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
    email_admin  = obter_config("contato_email", "admin@fielmordomo.com")
    wpp_admin    = obter_config("contato_whatsapp", "")
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
        link_email = f"mailto:{email_admin}?subject={assunto}&body={corpo}"
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
        wpp_link = f"https://wa.me/55{wpp_admin}?text={msg_wpp}"
        st.markdown(
            f'<a href="{wpp_link}" target="_blank" '
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
            "Gestao financeira para igrejas</p>",
            unsafe_allow_html=True,
        )

        # Modo recuperacao de senha
        if st.session_state.get("mostrar_recuperacao"):
            _mostrar_recuperacao_senha()
            return False

        modo = st.radio(
            "Tipo de acesso",
            ["Igreja", "Administrador do sistema"],
            horizontal=True,
            label_visibility="collapsed",
        )
        st.divider()

        if modo == "Igreja":
            _login_igreja()
        else:
            _login_admin()

    return False


def _login_igreja():
    with st.form("form_login_igreja"):
        st.markdown("#### Acesso da igreja")
        slug  = st.text_input("Identificador da igreja", placeholder="ex: ad-serrinha")
        senha = st.text_input("Senha", type="password")

        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            if not slug or not senha:
                st.error("Preencha todos os campos.")
                return
            igreja = autenticar_igreja(slug.strip().lower(), senha)
            if igreja:
                st.session_state["autenticado"] = True
                st.session_state["modo"] = "igreja"
                st.session_state["igreja"] = igreja
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
            if autenticar_super_admin(usuario, senha):
                st.session_state["autenticado"] = True
                st.session_state["modo"] = "admin"
                st.toast("Acesso de administrador autorizado.")
                st.rerun()
            else:
                st.error("Credenciais invalidas.")


def logout():
    for key in ("autenticado", "modo", "igreja", "pagina", "mostrar_recuperacao"):
        st.session_state.pop(key, None)
    st.rerun()


def exigir_autenticacao() -> bool:
    return st.session_state.get("autenticado", False)


def modo_atual() -> str:
    return st.session_state.get("modo", "")
