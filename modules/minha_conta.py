"""
Modulo para a igreja gerenciar a propria conta:
- Alterar senha
- Ver informacoes do plano
"""

import streamlit as st

from data.repository import igreja_alterar_senha
from utils.helpers import slug_da_sessao
from utils.planos import obter_plano, texto_limite, proximo_plano


def render():
    slug   = slug_da_sessao()
    igreja = st.session_state.get("igreja", {})

    st.subheader("👤 Minha conta")
    st.caption("Gerencie sua senha e informacoes da igreja.")

    # ── Informacoes da igreja ─────────────────────────────────────────────
    with st.expander("Informacoes da igreja", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Nome:**")
            st.markdown(f"### {igreja.get('nome', '-')}")
            st.markdown("**Identificador:**")
            st.code(igreja.get("slug", "-"))
        with col2:
            st.markdown("**E-mail:**")
            st.markdown(igreja.get("email_admin", "-"))

            plano   = igreja.get("plano", "basico")
            p_info  = obter_plano(plano)
            st.markdown("**Plano atual:**")
            st.markdown(
                f"<span style='background:{p_info['cor']};color:white;"
                f"padding:4px 12px;border-radius:20px;font-weight:600;"
                f"font-size:0.85rem'>{p_info['nome']}</span> — {p_info['preco']}",
                unsafe_allow_html=True,
            )
            st.caption(f"Limite: {texto_limite(plano)} membros")

    # ── Alterar senha ─────────────────────────────────────────────────────
    with st.expander("Alterar minha senha", expanded=False):
        st.caption("Para sua seguranca, informe a senha atual e a nova senha.")

        with st.form("form_alterar_senha"):
            senha_atual = st.text_input("Senha atual", type="password",
                                         key="ms_senha_atual")
            nova_senha  = st.text_input("Nova senha", type="password",
                                         key="ms_nova_senha",
                                         help="Minimo 6 caracteres.")
            conf_senha  = st.text_input("Confirmar nova senha", type="password",
                                         key="ms_conf_senha")

            if st.form_submit_button("Alterar senha", type="primary"):
                erros = []
                if not senha_atual:
                    erros.append("Informe a senha atual.")
                if len(nova_senha) < 6:
                    erros.append("Nova senha deve ter ao menos 6 caracteres.")
                if nova_senha != conf_senha:
                    erros.append("As senhas novas nao coincidem.")
                if senha_atual == nova_senha:
                    erros.append("A nova senha deve ser diferente da atual.")

                if erros:
                    for e in erros: st.error(e)
                else:
                    sucesso = igreja_alterar_senha(slug, senha_atual, nova_senha)
                    if sucesso:
                        st.success("✅ Senha alterada com sucesso!")
                        st.balloons()
                    else:
                        st.error("Senha atual incorreta. Tente novamente.")
