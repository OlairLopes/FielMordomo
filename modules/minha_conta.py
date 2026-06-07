import logging

import streamlit as st

from data.repository import (
    DIAS_DIZIMISTA_ATIVO_DEFAULT,
    adicionar_subcategoria_despesa,
    definir_senha_pastoral,
    excluir_subcategoria_despesa,
    igreja_alterar_senha,
    listar_subcategorias_despesa,
    obter_config_igreja,
    salvar_config_igreja,
    senha_pastoral_configurada,
    validar_nova_senha,
)
from utils.helpers import slug_da_sessao
from utils.planos import obter_plano


LOGGER = logging.getLogger(__name__)
OPCOES_DIAS = [30, 60, 90, 120]
MENSAGEM_ESCALA_EBD_PADRAO = """Paz do Senhor, {nome}!

Voce esta escalado(a) para servir na EBD.
Data: {data}
Classe: {classe}
Funcao: {funcao}
Tema: {tema}

Contamos com sua presenca e dedicacao. Deus abencoe!"""


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


def _numero_config(valor, padrao=0.0):
    texto = str(valor or "").strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = float(texto)
    except (TypeError, ValueError):
        return float(padrao)
    return numero if numero >= 0 else float(padrao)


def render():
    st.subheader("Minha Conta")

    slug = slug_da_sessao()
    igreja = st.session_state.get("igreja", {})

    if not isinstance(igreja, dict) or not igreja or not slug:
        st.error("Sessao invalida. Faca login novamente.")
        return

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
        reserva_atual = _numero_config(
            obter_config_igreja(slug, "reserva_financeira_disponivel", "0")
        )
        meta_reserva_atual = int(_numero_config(
            obter_config_igreja(slug, "meta_reserva_meses", "3"), 3
        ))
        mensagem_ebd_atual = obter_config_igreja(
            slug, "mensagem_whatsapp_escala_ebd", MENSAGEM_ESCALA_EBD_PADRAO
        )
        codigo_cadastro_atual = obter_config_igreja(
            slug, "codigo_atualizacao_cadastral", ""
        )
    except Exception:
        LOGGER.exception("Nao foi possivel carregar as configuracoes da igreja.")
        st.error("Nao foi possivel carregar as configuracoes. Tente novamente.")
        return

    idx_atual = OPCOES_DIAS.index(dias_atual)

    with st.form("form_config_igreja"):
        st.markdown("**🙏 Dizimista ativo**")
        st.caption(
            "Um membro e considerado dizimista ativo se contribuiu com dizimo "
            "nos ultimos N dias."
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

        st.markdown("**Saude financeira**")
        st.caption(
            "Informe a reserva financeira separada para emergencias e a meta de cobertura. "
            "Esses valores alimentam o painel de saude financeira."
        )
        reserva_nova = st.text_input(
            "Reserva financeira disponivel",
            value=f"{reserva_atual:.2f}".replace(".", ","),
            help="Informe apenas recursos realmente disponiveis como reserva.",
        )
        opcoes_meta = list(range(1, 13))
        meta_reserva_nova = st.selectbox(
            "Meta de cobertura da reserva",
            opcoes_meta,
            index=opcoes_meta.index(meta_reserva_atual) if meta_reserva_atual in opcoes_meta else 2,
            format_func=lambda meses: f"{meses} mes(es)",
        )

        st.markdown("**Mensagem da escala da EBD**")
        st.caption(
            "Use as variaveis {nome}, {data}, {classe}, {funcao} e {tema}. "
            "Elas serao preenchidas automaticamente ao gerar o aviso pelo WhatsApp."
        )
        mensagem_ebd_nova = st.text_area(
            "Modelo da mensagem WhatsApp para professores da EBD",
            value=str(mensagem_ebd_atual or MENSAGEM_ESCALA_EBD_PADRAO),
            height=180,
        )

        st.markdown("**Atualizacao cadastral publica**")
        st.caption(
            "Codigo divulgado internamente para membros atualizarem ou enviarem "
            "pre-cadastro pela pagina institucional."
        )
        codigo_cadastro_novo = st.text_input(
            "Codigo de atualizacao cadastral",
            value=str(codigo_cadastro_atual or ""),
            max_chars=30,
            help="Exemplo: AD2026 ou MEMBROS2026.",
        )

        if st.form_submit_button("Salvar configuracoes", type="primary"):
            assinatura_nova = assinatura_nova.strip()
            reserva_numero = _numero_config(reserva_nova, -1)
            if not assinatura_nova:
                st.error("Informe o nome da assinatura dos comprovantes.")
            elif reserva_numero < 0:
                st.error("Informe uma reserva financeira valida.")
            else:
                try:
                    salvar_config_igreja(slug, "dias_dizimista_ativo", str(dias_novo))
                    salvar_config_igreja(
                        slug, "nome_assinatura_comprovante", assinatura_nova
                    )
                    salvar_config_igreja(
                        slug, "reserva_financeira_disponivel", f"{reserva_numero:.2f}"
                    )
                    salvar_config_igreja(
                        slug, "meta_reserva_meses", str(meta_reserva_nova)
                    )
                    salvar_config_igreja(
                        slug, "mensagem_whatsapp_escala_ebd", mensagem_ebd_nova.strip()
                    )
                    salvar_config_igreja(
                        slug, "codigo_atualizacao_cadastral", codigo_cadastro_novo.strip()
                    )
                except Exception:
                    LOGGER.exception("Nao foi possivel salvar as configuracoes da igreja.")
                    st.error("Nao foi possivel salvar as configuracoes. Tente novamente.")
                else:
                    st.toast("Configuracoes salvas!")
                    st.rerun()

    st.divider()
    st.markdown("### Subcategorias de despesas")
    st.caption(
        "Cadastre as classificacoes usadas nos lancamentos de saida. "
        "Essa lista pertence a esta igreja e aparece no modulo Lancamentos."
    )

    try:
        subcategorias = listar_subcategorias_despesa(slug)
    except Exception:
        LOGGER.exception("Nao foi possivel carregar as subcategorias de despesa.")
        subcategorias = []
        st.error("Nao foi possivel carregar as subcategorias.")

    if subcategorias:
        st.dataframe(
            [{"Subcategoria": nome} for nome in subcategorias],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Nenhuma subcategoria cadastrada.")

    with st.form("form_adicionar_subcategoria", clear_on_submit=True):
        nova_subcategoria = st.text_input(
            "Nova subcategoria",
            max_chars=80,
            placeholder="Exemplo: Agua, Energia, Missoes, Manutencao...",
        )
        if st.form_submit_button("Adicionar subcategoria", type="primary"):
            nome = nova_subcategoria.strip()
            if not nome:
                st.error("Informe o nome da subcategoria.")
            else:
                try:
                    adicionada = adicionar_subcategoria_despesa(nome, slug)
                except Exception:
                    LOGGER.exception("Nao foi possivel adicionar a subcategoria.")
                    st.error("Nao foi possivel adicionar a subcategoria.")
                else:
                    if adicionada:
                        st.toast("Subcategoria adicionada!")
                        st.rerun()
                    else:
                        st.warning("Essa subcategoria ja existe ou e invalida.")

    if subcategorias:
        with st.form("form_excluir_subcategoria"):
            remover_subcategoria = st.selectbox(
                "Subcategoria para excluir",
                subcategorias,
                help=(
                    "A exclusao remove a opcao da lista. Lancamentos antigos "
                    "continuam preservando o texto ja salvo."
                ),
            )
            confirmar_remocao = st.checkbox(
                "Confirmo que desejo remover esta subcategoria da lista"
            )
            if st.form_submit_button("Excluir subcategoria"):
                if not confirmar_remocao:
                    st.error("Confirme a exclusao antes de continuar.")
                else:
                    try:
                        excluir_subcategoria_despesa(remover_subcategoria, slug)
                    except Exception:
                        LOGGER.exception("Nao foi possivel excluir a subcategoria.")
                        st.error("Nao foi possivel excluir a subcategoria.")
                    else:
                        st.toast("Subcategoria excluida.")
                        st.rerun()

    st.divider()
    st.markdown("### Senha do acompanhamento pastoral")
    st.caption(
        "Cadastre uma senha exclusiva para proteger os dados individuais de contribuicao. "
        "Ela deve ser diferente da senha principal da igreja."
    )
    try:
        pastoral_configurada = senha_pastoral_configurada(slug)
    except Exception:
        LOGGER.exception("Nao foi possivel consultar a senha pastoral.")
        pastoral_configurada = False
        st.error("Nao foi possivel verificar a configuracao da senha pastoral.")
    else:
        if pastoral_configurada:
            st.success("Senha pastoral cadastrada. Use o formulario para substitui-la.")
        else:
            st.warning("Cadastre uma senha pastoral para liberar o acompanhamento pastoral.")

    with st.form("form_senha_pastoral", clear_on_submit=True):
        senha_principal = st.text_input(
            "Senha principal da igreja",
            type="password",
            key="senha_principal_para_pastoral",
        )
        nova_senha_pastoral = st.text_input(
            "Nova senha pastoral",
            type="password",
            key="nova_senha_pastoral",
        )
        confirma_senha_pastoral = st.text_input(
            "Confirmar senha pastoral",
            type="password",
            key="confirma_senha_pastoral",
        )
        if st.form_submit_button(
            "Salvar senha pastoral" if not pastoral_configurada else "Alterar senha pastoral",
            type="primary",
        ):
            erros = []
            if not senha_principal:
                erros.append("Informe a senha principal da igreja.")
            erros.extend(validar_nova_senha(nova_senha_pastoral))
            if nova_senha_pastoral != confirma_senha_pastoral:
                erros.append("Senha pastoral e confirmacao nao coincidem.")

            if erros:
                for erro in dict.fromkeys(erros):
                    st.error(erro)
            else:
                try:
                    alterada = definir_senha_pastoral(
                        slug, senha_principal, nova_senha_pastoral
                    )
                except ValueError as ex:
                    st.error(str(ex))
                except Exception:
                    LOGGER.exception("Nao foi possivel salvar a senha pastoral.")
                    st.error("Nao foi possivel salvar a senha pastoral. Tente novamente.")
                else:
                    if alterada:
                        st.success("Senha pastoral salva com sucesso.")
                        st.rerun()
                    else:
                        st.error("Senha principal incorreta.")

    st.divider()
    st.markdown("### Alterar senha principal")
    st.caption(
        "Use uma senha longa e exclusiva. A nova senha deve possuir entre "
        "15 e 128 caracteres."
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
