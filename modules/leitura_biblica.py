import datetime
import html
import logging

import pandas as pd
import streamlit as st

from data.repository import (
    PLANO_LEITURA_PADRAO,
    cadastrar_leitor_biblia,
    carregar_cadastros,
    confirmar_leitura_biblica,
    leitura_ja_confirmada,
    listar_igrejas,
    listar_planos_leitura_biblica,
    localizar_leitor_plano_biblico,
    obter_leitura_do_dia,
)
from utils.helpers import normalizar_data_digitada

LOGGER = logging.getLogger(__name__)


def _parse_data_nascimento(valor):
    texto = normalizar_data_digitada(str(valor or "").strip())
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


def _hero_html(planos):
    badges = "".join(
        f'<span class="leitura-hero-badge">{html.escape(p["nome"])}</span>' for p in planos
    )
    return _html_sem_indentacao(f"""
        <div class="leitura-hero">
            <span class="leitura-hero-eyebrow">Plano de leitura</span>
            <div class="leitura-hero-badges">{badges}</div>
            <h1 class="leitura-hero-title">Plano de Leitura Bíblica</h1>
            <p class="leitura-hero-subtitle">Leia a sua Bíblia todos os dias.</p>
        </div>
    """)


def _card_leitura_html(dia_numero, data_escolhida, passagens, tema=""):
    pills = "".join(
        f'<span class="leitura-pill">{html.escape(p.strip())}</span>'
        for p in passagens.split(";")
        if p.strip()
    )
    tema_html = (
        f'<p class="leitura-tema">{html.escape(tema)}</p>' if tema else ""
    )
    return _html_sem_indentacao(f"""
        <div class="leitura-card">
            <div class="leitura-card-header">
                <span class="leitura-day-badge">Dia {dia_numero}</span>
                <span class="leitura-date">{data_escolhida.strftime('%d/%m/%Y')}</span>
            </div>
            {tema_html}
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


def _identificar_leitor(slug):
    st.markdown("#### Cadastre-se para confirmar sua leitura")
    st.caption(
        "Membros cadastrados são reconhecidos automaticamente. Se você ainda não "
        "é membro, esse cadastro cria seu acesso como leitor do plano."
    )
    with st.form("form_identificar_leitor_leitura"):
        nome = st.text_input("Nome completo")
        c1, c2 = st.columns(2)
        cpf = c1.text_input("CPF")
        data_nascimento_txt = c2.text_input(
            "Data de nascimento", placeholder="Ex.: 26/06/1979 ou 26061979"
        )
        confirmar = st.form_submit_button("Continuar", type="primary")

    if not confirmar:
        return

    data_nascimento = _parse_data_nascimento(data_nascimento_txt)
    if not nome.strip() or not cpf or not data_nascimento:
        st.error("Informe nome, CPF e data de nascimento válidos.")
        return

    cadastro = localizar_leitor_plano_biblico(slug, cpf, data_nascimento)
    if not cadastro:
        try:
            cadastrar_leitor_biblia(slug, nome, cpf, data_nascimento)
        except ValueError as erro:
            st.error(str(erro))
            return
        cadastro = localizar_leitor_plano_biblico(slug, cpf, data_nascimento)

    st.session_state["leitura_cadastro"] = cadastro
    st.rerun()


def render_publico():
    st.markdown(_hero_html(listar_planos_leitura_biblica()), unsafe_allow_html=True)

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
            st.rerun()

    planos = listar_planos_leitura_biblica()
    opcoes_planos = {p["nome"]: p["id"] for p in planos}
    nomes_planos = list(opcoes_planos.keys())
    plano_id_atual = st.session_state.get("leitura_plano_id", PLANO_LEITURA_PADRAO)
    nome_atual = next(
        (nome for nome, pid in opcoes_planos.items() if pid == plano_id_atual),
        nomes_planos[0],
    )
    nome_escolhido = st.selectbox(
        "Plano de leitura", nomes_planos, index=nomes_planos.index(nome_atual)
    )
    plano_id = opcoes_planos[nome_escolhido]
    st.session_state["leitura_plano_id"] = plano_id

    data_escolhida = st.date_input(
        "Escolha o dia da leitura", value=datetime.date.today()
    )
    dia_numero = _dia_do_plano(data_escolhida)

    leitura = obter_leitura_do_dia(dia_numero, plano_id=plano_id)
    if not leitura:
        st.info("Leitura ainda não cadastrada para este dia.")
        return

    st.markdown(
        _card_leitura_html(
            dia_numero, data_escolhida, leitura["passagens"], leitura.get("tema", "")
        ),
        unsafe_allow_html=True,
    )

    origem = cadastro.get("origem")
    id_pessoa = cadastro.get("id_pessoa")
    if leitura_ja_confirmada(slug, origem, id_pessoa, dia_numero, plano_id=plano_id):
        st.success("✅ Leitura deste dia já confirmada. Continue firme!")
    else:
        if st.button("Confirmar leitura deste dia", type="primary"):
            confirmar_leitura_biblica(slug, origem, id_pessoa, dia_numero, plano_id=plano_id)
            st.rerun()
