import datetime
import html
import logging

import pandas as pd
import streamlit as st

from data.repository import (
    cadastrar_leitor_biblia,
    carregar_cadastros,
    confirmar_leitura_biblica,
    leitura_ja_confirmada,
    listar_igrejas,
    localizar_leitor_plano_biblico,
    obter_leitura_do_dia,
)

LOGGER = logging.getLogger(__name__)


def _parse_data_nascimento(valor):
    texto = str(valor or "").strip()
    if not texto:
        return ""
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return ""


def _dia_do_plano(data):
    return min(data.timetuple().tm_yday, 365)


def _html_sem_indentacao(html_final):
    return "\n".join(linha.strip() for linha in str(html_final).splitlines() if linha.strip())


def _card_leitura_html(dia_numero, data_escolhida, passagens):
    pills = "".join(
        f'<span class="leitura-pill">{html.escape(p.strip())}</span>'
        for p in passagens.split(";")
        if p.strip()
    )
    return _html_sem_indentacao(f"""
        <div class="leitura-card">
            <div class="leitura-card-header">
                <span class="leitura-day-badge">Dia {dia_numero}</span>
                <span class="leitura-date">{data_escolhida.strftime('%d/%m/%Y')}</span>
            </div>
            <p class="leitura-passagens-label">Passagens de hoje</p>
            <div class="leitura-passagens">{pills}</div>
        </div>
    """)


def _selecionar_igreja_publica():
    try:
        igrejas = listar_igrejas()
    except Exception:
        LOGGER.exception("Nao foi possivel carregar a lista de igrejas.")
        igrejas = pd.DataFrame()

    if igrejas.empty:
        st.error("Nenhuma igreja cadastrada no sistema.")
        return None

    igrejas = igrejas[igrejas["ativa"].astype(int) == 1].copy()
    if igrejas.empty:
        st.error("Nenhuma igreja ativa encontrada.")
        return None

    opcoes = {
        f'{row["nome"]} ({row["slug"]})': str(row["slug"])
        for _, row in igrejas.sort_values("nome").iterrows()
    }

    with st.form("form_identificar_igreja_leitura"):
        st.markdown("#### Identificação da igreja")
        selecionada = st.selectbox("Igreja / congregação", list(opcoes.keys()))
        continuar = st.form_submit_button("Continuar", type="primary")
    if not continuar:
        return None

    slug = opcoes.get(selecionada, "").strip().lower()
    if not slug:
        st.error("Selecione uma igreja.")
        return None
    try:
        carregar_cadastros(slug)
    except Exception:
        LOGGER.exception("Falha ao carregar cadastros para o plano de leitura.")
        st.error("Nao foi possivel localizar essa igreja.")
        return None
    st.session_state["leitura_slug"] = slug
    return slug


def _cadastrar_novo_leitor(slug, cpf, data_nascimento):
    st.markdown("##### Cadastre-se como leitor")
    st.caption(
        "Você pode participar do plano de leitura mesmo sem ser membro desta igreja."
    )
    with st.form("form_cadastrar_leitor_biblia"):
        nome = st.text_input("Nome completo")
        telefone = st.text_input("Telefone (opcional)")
        confirmar = st.form_submit_button("Cadastrar como leitor", type="primary")

    if not confirmar:
        return

    if not nome.strip():
        st.error("Informe seu nome completo.")
        return

    try:
        cadastrar_leitor_biblia(slug, nome, cpf, data_nascimento, telefone)
    except ValueError as erro:
        st.error(str(erro))
        return

    st.session_state.pop("leitura_nao_encontrado", None)
    st.session_state["leitura_cadastro"] = localizar_leitor_plano_biblico(
        slug, cpf, data_nascimento
    )
    st.rerun()


def _identificar_leitor(slug):
    st.markdown("#### Identifique-se para confirmar sua leitura")
    with st.form("form_identificar_leitor_leitura"):
        c1, c2 = st.columns(2)
        cpf = c1.text_input("CPF")
        data_nascimento_txt = c2.text_input(
            "Data de nascimento", placeholder="Ex.: 26/06/1979"
        )
        localizar = st.form_submit_button("Localizar meu cadastro", type="primary")

    if localizar:
        data_nascimento = _parse_data_nascimento(data_nascimento_txt)
        if not cpf or not data_nascimento:
            st.error("Informe CPF e data de nascimento válidos.")
            return

        cadastro = localizar_leitor_plano_biblico(slug, cpf, data_nascimento)
        if cadastro:
            st.session_state.pop("leitura_nao_encontrado", None)
            st.session_state["leitura_cadastro"] = cadastro
            st.rerun()
            return

        st.session_state["leitura_nao_encontrado"] = {
            "cpf": cpf,
            "data_nascimento": data_nascimento,
        }

    pendente = st.session_state.get("leitura_nao_encontrado")
    if pendente:
        st.warning(
            "Cadastro não localizado. Se você é membro, procure a secretaria da sua "
            "igreja para atualizar seu cadastro. Se não é membro, cadastre-se abaixo "
            "para participar do plano de leitura."
        )
        _cadastrar_novo_leitor(slug, pendente["cpf"], pendente["data_nascimento"])


def render_publico():
    st.markdown("## Plano de Leitura Bíblica")
    st.caption(
        "Acompanhe o plano de leitura da Bíblia em 1 ano da Sociedade Bíblica do Brasil "
        "e confirme sua leitura diária."
    )

    slug = st.session_state.get("leitura_slug")
    if not slug:
        slug = _selecionar_igreja_publica()
        if not slug:
            return

    cadastro = st.session_state.get("leitura_cadastro")
    if not cadastro:
        _identificar_leitor(slug)
        return

    col_info, col_trocar = st.columns([3, 1])
    with col_info:
        st.success(
            f"Leitor: {cadastro.get('nome', '')} — {cadastro.get('igreja_nome', slug)}"
        )
    with col_trocar:
        if st.button("Trocar igreja/membro"):
            st.session_state.pop("leitura_slug", None)
            st.session_state.pop("leitura_cadastro", None)
            st.session_state.pop("leitura_nao_encontrado", None)
            st.rerun()

    data_escolhida = st.date_input(
        "Escolha o dia da leitura", value=datetime.date.today()
    )
    dia_numero = _dia_do_plano(data_escolhida)

    leitura = obter_leitura_do_dia(dia_numero)
    if not leitura:
        st.info("Leitura ainda não cadastrada para este dia.")
        return

    st.markdown(
        _card_leitura_html(dia_numero, data_escolhida, leitura["passagens"]),
        unsafe_allow_html=True,
    )

    origem = cadastro.get("origem")
    id_pessoa = cadastro.get("id_pessoa")
    if leitura_ja_confirmada(slug, origem, id_pessoa, dia_numero):
        st.success("✅ Leitura deste dia já confirmada. Continue firme!")
    else:
        if st.button("Confirmar leitura deste dia", type="primary"):
            confirmar_leitura_biblica(slug, origem, id_pessoa, dia_numero)
            st.rerun()
