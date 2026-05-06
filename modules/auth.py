"""
Autenticacao do FielMordomo.
Dois tipos de acesso:
  - Super admin: acesso ao painel de gestao de igrejas
  - Tesoureiro: acesso aos dados financeiros de uma igreja especifica
"""

import streamlit as st
from data.repository import autenticar_super_admin, autenticar_igreja, inicializar_master


def tela_login():
    """Exibe tela de login e retorna True se autenticado."""
    if st.session_state.get("autenticado"):
        return True

    inicializar_master()

    st.markdown(
        """
        <div style="text-align:center;padding:2rem 0 1rem">
          <div style="font-size:2.5rem;font-weight:500;color:var(--color-text-primary)">
            FielMordomo
          </div>
          <div style="font-size:0.9rem;color:var(--color-text-secondary);margin-top:4px">
            Gestao financeira para igrejas
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    modo = st.radio(
        "Tipo de acesso",
        ["Igreja", "Administrador do sistema"],
        horizontal=True,
        label_visibility="collapsed",
    )

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

    st.caption(
        "Nao tem acesso? Entre em contato com o administrador do sistema para cadastrar sua igreja."
    )


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
