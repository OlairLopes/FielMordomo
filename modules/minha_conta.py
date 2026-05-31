import logging

import streamlit as st

from data.repository import (
    DIAS_DIZIMISTA_ATIVO_DEFAULT,
    igreja_alterar_senha,
    obter_config_igreja,
    salvar_config_igreja,
    validar_nova_senha,
import streamlit as st

from data.repository import (
    igreja_alterar_senha,
    obter_config_igreja, salvar_config_igreja,
    DIAS_DIZIMISTA_ATIVO_DEFAULT,
)
from utils.helpers import slug_da_sessao
from utils.planos import obter_plano


LOGGER = logging.getLogger(__name__)
OPCOES_DIAS = [30, 60, 90, 120]


def _encerrar_sessao():
    for key in ("autenticado", "modo", "igreja", "pagina", "mostrar_recuperacao"):
        st.session_state.pop(key, None)
    for key in list(st.session_state.keys()):
        if key.startswith(("df_", "lote_", "nl_counter_", "dashboard_", "_auth_", "_edit_", "_del_")):
            st.session_state.pop(key, None)


def _config_dias(slug):
    valor = obter_config_igreja(
        slug, "dias_dizimista_ativo", str(DIAS_DIZIMISTA_ATIVO_DEFAULT)
    )
    try:
        dias = int(valor)
    except (ValueError, TypeError):
        dias = DIAS_DIZIMISTA_ATIVO_DEFAULT
    return dias if dias in OPCOES_DIAS else DIAS_DIZIMISTA_ATIVO_DEFAULT


def render():
    st.subheader("Minha Conta")

    slug = slug_da_sessao()
    igreja = st.session_state.get("igreja", {})

    if not isinstance(igreja, dict) or not igreja or not slug:
        st.error("Sessao invalida. Faca login novamente.")
        return

def render():
    st.subheader("Minha Conta")

    slug   = slug_da_sessao()
    igreja = st.session_state.get("igreja", {})

    if not igreja:
        st.error("Sessao invalida. Faca login novamente.")
        return

    # ── Dados da igreja ───────────────────────────────────────────────────
    st.markdown("### 🏛️ Dados da igreja")

    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Nome da igreja", value=igreja.get("nome", ""), disabled=True)
        st.text_input("Identificador (slug)", value=igreja.get("slug", ""), disabled=True)
    with col2:
        st.text_input("E-mail do admin", value=igreja.get("email_admin", ""), disabled=True)

        plano = igreja.get("plano", "basico")
        p_info = obter_plano(plano)
        st.text_input(
            "Plano atual",
            value=f"{p_info['nome']} - {p_info.get('preco', '')}",
            value=f"{p_info['nome']} — {p_info.get('preco', '')}",
            disabled=True,
        )

    st.caption(
        "Para alterar nome, e-mail ou plano, entre em contato com o administrador do sistema."
    )

    st.divider()
    st.markdown("### ⚙️ Configuracoes da igreja")
    st.caption("Personalize criterios usados nos relatorios, dashboard e comprovantes.")

    try:
        dias_atual = _config_dias(slug)
        assinatura_atual = obter_config_igreja(
            slug, "nome_assinatura_comprovante", "Responsavel"
        )
    except Exception:
        LOGGER.exception("Nao foi possivel carregar as configuracoes da igreja.")
        st.error("Nao foi possivel carregar as configuracoes. Tente novamente.")
        return

    idx_atual = OPCOES_DIAS.index(dias_atual)

    # ── Configuracoes da igreja (FASE 2) ──────────────────────────────────
    st.markdown("### ⚙️ Configuracoes da igreja")
    st.caption(
        "Personalize criterios que sao usados nos relatorios e no dashboard."
    )

    # Le valor atual da config
    try:
        dias_atual = int(obter_config_igreja(
            slug, "dias_dizimista_ativo", str(DIAS_DIZIMISTA_ATIVO_DEFAULT)
        ))
    except (ValueError, TypeError):
        dias_atual = DIAS_DIZIMISTA_ATIVO_DEFAULT

    OPCOES_DIAS = [30, 60, 90, 120]
    idx_atual = OPCOES_DIAS.index(dias_atual) if dias_atual in OPCOES_DIAS else 0

    with st.form("form_config_igreja"):
        st.markdown("**🙏 Dizimista ativo**")
        st.caption(
            "Um membro e considerado dizimista ativo se contribuiu com dizimo "
            "nos ultimos N dias."
            "Um membro e considerado **dizimista ativo** se contribuiu "
            "com dizimo nos ultimos N dias. Configure o periodo conforme a "
            "frequencia esperada de contribuicao da sua igreja."
        )

        dias_novo = st.selectbox(
            "Dias para considerar dizimista ativo",
            OPCOES_DIAS,
            index=idx_atual,
            format_func=lambda x: f"{x} dias" + (
                "  (mensal)" if x == 30 else
                "  (bimestral)" if x == 60 else
                "  (trimestral)" if x == 90 else
                "  (quadrimestral)"
            ),
            help="Padrao do sistema: 30 dias.",
        )

        assinatura_nova = st.text_input(
            "Nome da assinatura nos comprovantes",
            value=str(assinatura_atual or "Responsavel"),
            max_chars=100,
            help="Exemplo: Pr. Joao Silva ou Tesoureiro Responsavel.",
        )

        if st.form_submit_button("Salvar configuracoes", type="primary"):
            assinatura_nova = assinatura_nova.strip()
            if not assinatura_nova:
                st.error("Informe o nome da assinatura dos comprovantes.")
            else:
                try:
                    salvar_config_igreja(slug, "dias_dizimista_ativo", str(dias_novo))
                    salvar_config_igreja(
                        slug, "nome_assinatura_comprovante", assinatura_nova
                    )
                except Exception:
                    LOGGER.exception("Nao foi possivel salvar as configuracoes da igreja.")
                    st.error("Nao foi possivel salvar as configuracoes. Tente novamente.")
                else:
                    st.toast("Configuracoes salvas!")
                    st.rerun()

    st.divider()
    st.markdown("### 🔒 Alterar senha")
    st.caption(
        "Use uma senha longa e exclusiva. A nova senha deve possuir entre "
        "15 e 128 caracteres."
                "  (mensal)"     if x == 30  else
                "  (bimestral)"  if x == 60  else
                "  (trimestral)" if x == 90  else
                "  (quadrimestral)"
            ),
            help="Default do sistema: 30 dias.",
        )

        if st.form_submit_button("Salvar configuracoes", type="primary"):
            salvar_config_igreja(slug, "dias_dizimista_ativo", str(dias_novo))
            st.toast(f"Configuracao salva: dizimista ativo = {dias_novo} dias")
            st.rerun()

    st.divider()

    # ── Trocar senha ──────────────────────────────────────────────────────
    st.markdown("### 🔒 Alterar senha")
    st.caption(
        "Sua senha de acesso a esta igreja. Recomendamos usar uma senha forte "
        "com pelo menos 8 caracteres."
    )

    with st.form("form_trocar_senha", clear_on_submit=True):
        senha_atual = st.text_input("Senha atual", type="password")
        nova_senha = st.text_input("Nova senha", type="password")
        confirma = st.text_input("Confirmar nova senha", type="password")

        if st.form_submit_button("Alterar senha", type="primary"):
            erros = []
            if not senha_atual:
                erros.append("Informe a senha atual.")
            erros.extend(validar_nova_senha(nova_senha))
        nova_senha  = st.text_input("Nova senha", type="password")
        confirma    = st.text_input("Confirmar nova senha", type="password")

        if st.form_submit_button("Alterar senha", type="primary"):
            erros = []

            if not senha_atual:
                erros.append("Informe a senha atual.")
            if not nova_senha or len(nova_senha) < 6:
                erros.append("Nova senha deve ter ao menos 6 caracteres.")
            if nova_senha != confirma:
                erros.append("Nova senha e confirmacao nao coincidem.")

            if erros:
                for erro in dict.fromkeys(erros):
                    st.error(erro)
            else:
                try:
                    alterada = igreja_alterar_senha(slug, senha_atual, nova_senha)
                except Exception:
                    LOGGER.exception("Nao foi possivel alterar a senha da igreja.")
                    st.error("Nao foi possivel alterar a senha. Tente novamente.")
                else:
                    if alterada:
                        _encerrar_sessao()
                        st.success("Senha alterada. Entre novamente com a nova senha.")
                        st.rerun()
                    else:
                        st.error("Senha atual incorreta.")
                for e in erros:
                    st.error(e)
            else:
                if igreja_alterar_senha(slug, senha_atual, nova_senha):
                    st.success("✅ Senha alterada com sucesso!")
                    st.toast("Senha alterada!")
                else:
                    st.error("❌ Senha atual incorreta.")
