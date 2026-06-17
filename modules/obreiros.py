import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.repository import (
    listar_funcoes_obreiros,
    listar_obreiros_por_funcoes,
    listar_obreiros_reunioes,
    obter_obreiros_ata,
    relatorio_obreiros_frequencia,
    salvar_obreiros_chamada,
)
from utils.helpers import gerar_csv, slug_da_sessao


CORES = {
    "azul": "#0F3D5E",
    "verde": "#1D9E75",
    "laranja": "#F59E0B",
    "vermelho": "#DC2626",
    "roxo": "#7C3AED",
    "cinza": "#64748B",
}
CONFIG_PLOTLY = {"displayModeBar": False, "responsive": True}


def _hoje():
    return datetime.date.today()


def _inicio_mes():
    return _hoje().replace(day=1)


def _fmt_data(valor):
    try:
        return datetime.date.fromisoformat(str(valor)).strftime("%d/%m/%Y")
    except Exception:
        return str(valor or "")


def _pct(valor):
    try:
        return f"{float(valor):.1f}%"
    except Exception:
        return "0.0%"


def _moeda(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def _grafico_reunioes(reunioes):
    if reunioes.empty:
        st.info("Sem reunioes no periodo selecionado.")
        return
    dados = reunioes.sort_values("data")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Presentes",
        x=dados["data"].apply(_fmt_data),
        y=dados["presentes"],
        marker_color=CORES["verde"],
        text=dados["presentes"],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="Ausentes",
        x=dados["data"].apply(_fmt_data),
        y=dados["ausentes"],
        marker_color=CORES["vermelho"],
        text=dados["ausentes"],
        textposition="outside",
    ))
    fig.update_layout(
        title="Participacao nas reunioes de obreiros",
        barmode="group",
        height=430,
        margin=dict(t=60, b=60, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(gridcolor="#E2E8F0", fixedrange=True),
        xaxis=dict(fixedrange=True),
        legend=dict(orientation="h", y=1.12, x=0),
    )
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


def _grafico_frequencia(freq):
    if freq.empty:
        st.info("Sem frequencia individual no periodo.")
        return
    dados = freq.sort_values("frequencia_pct", ascending=True)
    fig = go.Figure(go.Bar(
        name="Frequencia",
        x=dados["frequencia_pct"],
        y=dados["nome"] + " (" + dados["funcao"].fillna("") + ")",
        orientation="h",
        marker_color=CORES["azul"],
        text=[_pct(v) for v in dados["frequencia_pct"]],
        textposition="outside",
    ))
    fig.update_layout(
        title="Frequencia individual dos obreiros",
        height=max(360, 46 * len(dados)),
        margin=dict(t=60, b=40, l=20, r=35),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(range=[0, 105], title="Frequencia (%)", fixedrange=True),
        yaxis=dict(title="", fixedrange=True),
        showlegend=True,
        legend=dict(orientation="h", y=1.12, x=0),
    )
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


def _resumo_funcoes(freq):
    if freq.empty:
        return pd.DataFrame(columns=["funcao", "obreiros", "presencas", "ausencias", "frequencia_pct"])
    resumo = freq.groupby("funcao", as_index=False).agg(
        obreiros=("id_cadastro", "nunique"),
        presencas=("presencas", "sum"),
        ausencias=("ausencias", "sum"),
    )
    total = resumo["presencas"] + resumo["ausencias"]
    resumo["frequencia_pct"] = (resumo["presencas"] / total.where(total > 0, 1) * 100).round(1)
    return resumo.sort_values("funcao")


def _grafico_funcoes(resumo):
    if resumo.empty:
        st.info("Sem resumo por funcao.")
        return
    fig = go.Figure(go.Bar(
        name="Frequencia media",
        x=resumo["funcao"],
        y=resumo["frequencia_pct"],
        marker_color=CORES["verde"],
        text=[_pct(v) for v in resumo["frequencia_pct"]],
        textposition="outside",
    ))
    fig.update_layout(
        title="Frequencia por funcao ministerial",
        height=430,
        margin=dict(t=60, b=90, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(range=[0, 105], gridcolor="#E2E8F0", fixedrange=True),
        xaxis=dict(fixedrange=True),
        showlegend=True,
        legend=dict(orientation="h", y=1.12, x=0),
    )
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


def _render_chamada(slug):
    st.markdown("### Chamada de obreiros")
    st.caption(
        "Selecione as funcoes ministeriais. Todos os membros ativos com essas funcoes "
        "serao inseridos automaticamente na folha de chamada."
    )

    funcoes = listar_funcoes_obreiros(slug)
    if not funcoes:
        st.warning("Nenhuma funcao encontrada no cadastro de membros.")
        return

    data = st.date_input("Data da reuniao", value=_hoje(), key="obreiros_data", format="DD/MM/YYYY")
    tema = st.text_input("Tema / pauta da reuniao", key="obreiros_tema")
    selecionadas = st.multiselect(
        "Funcoes que participarao da chamada",
        funcoes,
        default=[],
        key="obreiros_funcoes",
    )
    if not selecionadas:
        st.info("Selecione uma ou mais funcoes para gerar a folha de chamada.")
        return

    membros = listar_obreiros_por_funcoes(slug, selecionadas)
    if membros.empty:
        st.warning("Nenhum membro ativo encontrado para as funcoes selecionadas.")
        return

    st.markdown("#### Folha de chamada")
    st.caption(f"{len(membros)} obreiro(s) incluidos automaticamente.")
    c_marcar, c_desmarcar = st.columns(2)
    chaves_presenca = [
        f'obreiros_presenca_{data}_{int(row["id_cadastro"])}'
        for _, row in membros.iterrows()
    ]
    if c_marcar.button("Marcar todos", use_container_width=True, key=f"obreiros_marcar_todos_{data}"):
        for chave in chaves_presenca:
            st.session_state[chave] = True
        st.rerun()
    if c_desmarcar.button("Desmarcar todos", use_container_width=True, key=f"obreiros_desmarcar_todos_{data}"):
        for chave in chaves_presenca:
            st.session_state[chave] = False
        st.rerun()

    presencas = {}
    for funcao, grupo in membros.groupby("funcao"):
        with st.expander(f"{funcao} ({len(grupo)})", expanded=True):
            for _, row in grupo.iterrows():
                presencas[int(row["id_cadastro"])] = st.checkbox(
                    row["nome"],
                    value=True,
                    key=f'obreiros_presenca_{data}_{int(row["id_cadastro"])}',
                )

    c1, c2 = st.columns(2)
    visitantes = c1.number_input("Visitantes", min_value=0, step=1, value=0)
    ofertas = c2.number_input("Ofertas", min_value=0.0, step=1.0, value=0.0)
    observacoes = st.text_area("Observacoes")
    arquivo_ata = st.file_uploader(
        "Ata da reunião",
        type=["pdf", "doc", "docx", "png", "jpg", "jpeg"],
        help="Anexe a ata em PDF, Word ou imagem. Se a chamada ja tiver uma ata salva, ela sera mantida quando nenhum novo arquivo for enviado.",
        key=f"obreiros_ata_{data}",
    )

    presentes = sum(1 for v in presencas.values() if v)
    ausentes = len(presencas) - presentes
    m1, m2, m3 = st.columns(3)
    m1.metric("Matriculados na chamada", len(presencas))
    m2.metric("Presentes", presentes)
    m3.metric("Ausentes", ausentes)

    if st.button("Salvar chamada", type="primary", use_container_width=True):
        try:
            salvar_obreiros_chamada(
                slug,
                data.isoformat(),
                tema=tema,
                funcoes=selecionadas,
                presencas=presencas,
                visitantes=visitantes,
                ofertas=ofertas,
                observacoes=observacoes,
                ata_nome=arquivo_ata.name if arquivo_ata else "",
                ata_mime=arquivo_ata.type if arquivo_ata else "",
                ata_bytes=arquivo_ata.getvalue() if arquivo_ata else None,
            )
        except Exception as ex:
            st.error(str(ex))
        else:
            st.success("Chamada salva com sucesso.")
            st.rerun()


def _render_relatorios(slug):
    st.markdown("### Relatorios de obreiros")
    c1, c2, c3 = st.columns(3)
    inicio = c1.date_input("Data inicial", value=_inicio_mes(), key="obreiros_rel_ini", format="DD/MM/YYYY")
    fim = c2.date_input("Data final", value=_hoje(), key="obreiros_rel_fim", format="DD/MM/YYYY")
    funcoes = ["Todas"] + listar_funcoes_obreiros(slug)
    funcao = c3.selectbox("Funcao", funcoes, key="obreiros_rel_funcao")

    reunioes = listar_obreiros_reunioes(slug, inicio.isoformat(), fim.isoformat())
    freq = relatorio_obreiros_frequencia(
        slug,
        inicio.isoformat(),
        fim.isoformat(),
        "" if funcao == "Todas" else funcao,
    )
    resumo_funcoes = _resumo_funcoes(freq)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Reunioes", int(reunioes["id_reuniao"].nunique()) if not reunioes.empty else 0)
    c2.metric("Presentes", int(reunioes["presentes"].fillna(0).sum()) if not reunioes.empty else 0)
    c3.metric("Ausentes", int(reunioes["ausentes"].fillna(0).sum()) if not reunioes.empty else 0)
    c4.metric("Ofertas", _moeda(reunioes["ofertas"].fillna(0).sum()) if not reunioes.empty else _moeda(0))

    _grafico_reunioes(reunioes)
    _grafico_funcoes(resumo_funcoes)
    _grafico_frequencia(freq)

    with st.expander("Reunioes registradas", expanded=False):
        st.dataframe(reunioes, use_container_width=True, hide_index=True)
        st.download_button(
            "Baixar reunioes CSV",
            data=gerar_csv(reunioes),
            file_name="reunioes_obreiros.csv",
            mime="text/csv",
        )
        if not reunioes.empty and "tem_ata" in reunioes.columns:
            reunioes_com_ata = reunioes[reunioes["tem_ata"].fillna(0).astype(int) == 1].copy()
            if not reunioes_com_ata.empty:
                opcoes_ata = {
                    f'{_fmt_data(row["data"])} - {row["ata_nome"] or "Ata anexada"}': int(row["id_reuniao"])
                    for _, row in reunioes_com_ata.iterrows()
                }
                escolha_ata = st.selectbox(
                    "Ata anexada para download",
                    list(opcoes_ata.keys()),
                    key="obreiros_ata_download",
                )
                ata = obter_obreiros_ata(slug, opcoes_ata[escolha_ata])
                if ata:
                    st.download_button(
                        "Baixar ata da reunião",
                        data=ata["bytes"],
                        file_name=ata["nome"],
                        mime=ata["mime"],
                        use_container_width=True,
                    )
    with st.expander("Frequencia individual", expanded=False):
        st.dataframe(freq, use_container_width=True, hide_index=True)
        st.download_button(
            "Baixar frequencia CSV",
            data=gerar_csv(freq),
            file_name="frequencia_obreiros.csv",
            mime="text/csv",
        )


def render():
    st.subheader("Reunião de Obreiros")
    slug = slug_da_sessao()
    if not slug:
        st.error("Sessao invalida. Faca login novamente.")
        return
    if st.session_state.get("modo") == "secretario_geral":
        _render_chamada(slug)
        return
    tab_chamada, tab_relatorios = st.tabs(["Chamada", "Relatorios"])
    with tab_chamada:
        _render_chamada(slug)
    with tab_relatorios:
        _render_relatorios(slug)
