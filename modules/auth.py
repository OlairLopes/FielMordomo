"""
Autenticacao do FielMordomo.
"""

import streamlit as st
from data.repository import (
    autenticar_super_admin, autenticar_igreja,
    inicializar_master, obter_logo_sistema,
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

    st.caption("Nao tem acesso? Entre em contato com o administrador do sistema.")


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
    for key in ("autenticado", "modo", "igreja", "pagina"):
        st.session_state.pop(key, None)
    st.rerun()


def exigir_autenticacao() -> bool:
    return st.session_state.get("autenticado", False)


def modo_atual() -> str:
    return st.session_state.get("modo", "")
