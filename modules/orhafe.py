import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.repository import (
    carregar_cadastros,
    carregar_orhafe_presencas,
    encerrar_orhafe_matricula,
    listar_orhafe_coordenadoras,
    listar_orhafe_lideres,
    listar_orhafe_matriculas,
    listar_orhafe_reunioes,
    relatorio_orhafe_frequencia,
    salvar_orhafe_chamada,
    salvar_orhafe_coordenadora,
    salvar_orhafe_lider,
    salvar_orhafe_matricula,
)
from utils.helpers import confirmar_exclusao, gerar_csv, slug_da_sessao


CORES = {
    "azul": "#0F3D5E",
    "verde": "#1D9E75",
    "laranja": "#F59E0B",
    "vermelho": "#DC2626",
    "cinza": "#64748B",
    "roxo": "#7C3AED",
}
CONFIG_PLOTLY = {"displayModeBar": False, "responsive": True}


def _hoje():
    return datetime.date.today()


def _inicio_mes():
    hoje = _hoje()
    return hoje.replace(day=1)


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


def _membros_opcoes(slug):
    df = carregar_cadastros(slug)
    if df.empty:
        return {}, df
    membros = df[
        (df["tipo_cadastro"].astype(str).str.upper() == "MEMBRO")
        & (df["situacao"].astype(str).str.upper() == "ATIVO")
    ].copy()
    membros = membros.sort_values("nome")
    opcoes = {
        f'{int(row["id_cadastro"])} - {row["nome"]}': int(row["id_cadastro"])
        for _, row in membros.iterrows()
    }
    return opcoes, membros


def _lideres_opcoes(df_lideres):
    return {
        f'{int(row["id_lider"])} - {row["nome"]}': int(row["id_lider"])
        for _, row in df_lideres.iterrows()
    }


def _metricas_chamadas(reunioes):
    if reunioes.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Reunioes", 0)
        c2.metric("Presentes", 0)
        c3.metric("Visitantes", 0)
        c4.metric("Ofertas", _moeda(0))
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Reunioes", int(reunioes["id_reuniao"].nunique()))
    c2.metric("Presentes", int(reunioes["presentes"].fillna(0).sum()))
    c3.metric("Visitantes", int(reunioes["visitantes"].fillna(0).sum()))
    c4.metric("Ofertas", _moeda(reunioes["ofertas"].fillna(0).sum()))


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
        name="Visitantes",
        x=dados["data"].apply(_fmt_data),
        y=dados["visitantes"],
        marker_color=CORES["laranja"],
        text=dados["visitantes"],
        textposition="outside",
    ))
    fig.update_layout(
        title="Participacao nas reunioes",
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
    dados = freq.copy()
    total = dados["presencas"] + dados["ausencias"]
    dados["frequencia_pct"] = (dados["presencas"] / total.where(total > 0, 1) * 100).round(1)
    dados = dados.sort_values("frequencia_pct")
    fig = go.Figure(go.Bar(
        name="Frequencia",
        x=dados["frequencia_pct"],
        y=dados["nome"],
        orientation="h",
        marker_color=CORES["azul"],
        text=[_pct(v) for v in dados["frequencia_pct"]],
        textposition="outside",
    ))
    fig.update_layout(
        title="Frequencia das matriculadas",
        height=max(360, 48 * len(dados)),
        margin=dict(t=60, b=40, l=20, r=35),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(range=[0, 105], title="Frequencia (%)", fixedrange=True),
        yaxis=dict(title="", fixedrange=True),
        showlegend=True,
        legend=dict(orientation="h", y=1.12, x=0),
    )
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


def _totais_reunioes(reunioes):
    if reunioes.empty:
        return {
            "Matriculadas": 0,
            "Presentes": 0,
            "Ausentes": 0,
            "Visitantes": 0,
            "Ofertas": 0.0,
            "Reunioes": 0,
        }
    return {
        "Matriculadas": int(reunioes["matriculadas"].fillna(0).sum()),
        "Presentes": int(reunioes["presentes"].fillna(0).sum()),
        "Ausentes": int(reunioes["ausentes"].fillna(0).sum()),
        "Visitantes": int(reunioes["visitantes"].fillna(0).sum()),
        "Ofertas": float(reunioes["ofertas"].fillna(0).sum()),
        "Reunioes": int(reunioes["id_reuniao"].nunique()),
    }


def _resumo_lideres(reunioes):
    if reunioes.empty:
        return pd.DataFrame(
            columns=[
                "lider", "reunioes", "matriculadas", "presentes",
                "ausentes", "visitantes", "ofertas", "frequencia_pct",
            ]
        )
    resumo = reunioes.copy()
    resumo["lider"] = resumo["lider"].fillna("").replace("", "Sem lider")
    resumo = resumo.groupby("lider", as_index=False).agg(
        reunioes=("id_reuniao", "nunique"),
        matriculadas=("matriculadas", "sum"),
        presentes=("presentes", "sum"),
        ausentes=("ausentes", "sum"),
        visitantes=("visitantes", "sum"),
        ofertas=("ofertas", "sum"),
    )
    total = resumo["presentes"] + resumo["ausentes"]
    resumo["frequencia_pct"] = (
        resumo["presentes"] / total.where(total > 0, 1) * 100
    ).round(1)
    return resumo.sort_values("lider")


def _grafico_totais_orhafe(titulo, dados):
    if not dados:
        st.info("Sem dados para gerar o grafico.")
        return
    df = pd.DataFrame(
        [{"Indicador": chave, "Total": valor} for chave, valor in dados.items()]
    )
    fig = go.Figure(go.Bar(
        name="Total",
        x=df["Indicador"],
        y=df["Total"],
        marker_color=[
            CORES["azul"], CORES["verde"], CORES["vermelho"],
            CORES["laranja"], CORES["roxo"], CORES["cinza"],
        ][:len(df)],
        text=[
            _moeda(v) if str(k) == "Ofertas" else str(int(v))
            for k, v in dados.items()
        ],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Total: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title=titulo,
        height=430,
        margin=dict(t=60, b=80, l=25, r=25),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(fixedrange=True),
        yaxis=dict(fixedrange=True, gridcolor="#E2E8F0"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


def _grafico_resumo_lideres(resumo):
    if resumo.empty:
        st.info("Sem dados por lider para o periodo selecionado.")
        return
    dados = resumo.sort_values("presentes", ascending=True)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Presentes",
        x=dados["presentes"],
        y=dados["lider"],
        orientation="h",
        marker_color=CORES["verde"],
        text=dados["presentes"],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="Visitantes",
        x=dados["visitantes"],
        y=dados["lider"],
        orientation="h",
        marker_color=CORES["laranja"],
        text=dados["visitantes"],
        textposition="outside",
    ))
    fig.update_layout(
        title="Resumo por lider",
        barmode="group",
        height=max(360, 70 * len(dados)),
        margin=dict(t=60, b=40, l=20, r=35),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(fixedrange=True, gridcolor="#E2E8F0"),
        yaxis=dict(title="", fixedrange=True),
        showlegend=True,
        legend=dict(orientation="h", y=1.12, x=0),
    )
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


def _render_coordenadoras(slug):
    coordenadoras = listar_orhafe_coordenadoras(slug)
    st.markdown(
        """
        <style>
        .orhafe-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:.35rem 0 1rem}
        .orhafe-card{border:1px solid #E2E8F0;border-radius:14px;padding:14px 16px;background:#fff;
            box-shadow:0 10px 28px rgba(15,61,94,.08)}
        .orhafe-card small{display:block;color:#64748B;margin-top:4px}
        @media(max-width:900px){.orhafe-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:560px){.orhafe-grid{grid-template-columns:1fr}}
        </style>
        """,
        unsafe_allow_html=True,
    )
    if coordenadoras.empty:
        st.warning("Cadastre as 4 coordenadoras fixas na aba Configuracoes.")
        return
    cards = []
    for _, row in coordenadoras.head(4).iterrows():
        cards.append(
            f"""<div class="orhafe-card">
                <b>{row["nome"]}</b>
                <small>{row.get("funcao", "") or "Coordenadora"}</small>
                <small>{row.get("telefone", "") or ""}</small>
            </div>"""
        )
    st.markdown(f'<div class="orhafe-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def _render_matriculas(slug):
    st.markdown("### Matriculas")
    st.caption("Matricule participantes buscando diretamente no cadastro de membros.")
    op_membros, df_membros = _membros_opcoes(slug)
    with st.form("form_orhafe_matricula"):
        if not op_membros:
            st.warning("Nao ha membros ativos disponiveis para matricula.")
            membro_label = None
        else:
            membro_label = st.selectbox("Membro", list(op_membros.keys()))
        c1, c2 = st.columns(2)
        data_inicio = c1.date_input("Data de inicio", value=_hoje())
        observacoes = c2.text_input("Observacoes")
        if st.form_submit_button("Matricular", type="primary"):
            if not membro_label:
                st.error("Selecione um membro.")
            else:
                id_cadastro = op_membros[membro_label]
                salvar_orhafe_matricula(
                    slug,
                    "",
                    id_cadastro=id_cadastro,
                    data_inicio=data_inicio.isoformat(),
                    observacoes=observacoes,
                )
                st.success("Matricula salva.")
                st.rerun()

    matriculas = listar_orhafe_matriculas(slug, incluir_inativas=True)
    if matriculas.empty:
        st.info("Nenhuma matricula cadastrada.")
        return
    exibir = matriculas.copy()
    exibir["situacao_matricula"] = exibir["ativa"].map({1: "Ativa", 0: "Encerrada"})
    exibir["data_inicio"] = exibir["data_inicio"].apply(_fmt_data)
    st.dataframe(
        exibir[["nome", "telefone", "funcao", "congregacao", "situacao_matricula", "data_inicio", "observacoes"]],
        use_container_width=True,
        hide_index=True,
    )
    ativas = matriculas[matriculas["ativa"] == 1]
    if not ativas.empty:
        encerrar = st.selectbox(
            "Encerrar matricula",
            ["Selecione"] + [
                f'{int(row["id_matricula"])} - {row["nome"]}'
                for _, row in ativas.iterrows()
            ],
        )
        if encerrar != "Selecione" and confirmar_exclusao(
            f"encerrar_orhafe_{encerrar}", "Encerrar matricula selecionada"
        ):
            encerrar_orhafe_matricula(slug, int(encerrar.split(" - ")[0]), _hoje().isoformat())
            st.success("Matricula encerrada.")
            st.rerun()


def _render_chamada(slug):
    st.markdown("### Chamada ORHAFE")
    lideres = listar_orhafe_lideres(slug)
    if lideres.empty:
        st.warning("Cadastre ate 5 lideres na aba Configuracoes antes de registrar chamada.")
        return
    matriculas = listar_orhafe_matriculas(slug)
    if matriculas.empty:
        st.warning("Cadastre matriculas antes de registrar chamada.")
        return

    chamadas_salvas = listar_orhafe_reunioes(slug)
    modo = st.radio(
        "Modo",
        ["Nova chamada", "Editar chamada salva"] if not chamadas_salvas.empty else ["Nova chamada"],
        horizontal=True,
    )
    reuniao_atual = None
    if modo == "Editar chamada salva":
        op_reunioes = {
            f'{int(row["id_reuniao"])} - {_fmt_data(row["data"])} - {row.get("lider", "") or "sem lider"}': row
            for _, row in chamadas_salvas.iterrows()
        }
        reuniao_label = st.selectbox("Chamada salva", list(op_reunioes.keys()))
        reuniao_atual = op_reunioes[reuniao_label]
        data_reuniao = datetime.date.fromisoformat(str(reuniao_atual["data"]))
    else:
        data_reuniao = st.date_input("Data da reuniao", value=_hoje())

    lider_opcoes = _lideres_opcoes(lideres)
    lider_labels = list(lider_opcoes.keys())
    lider_index = 0
    if reuniao_atual is not None and reuniao_atual.get("id_lider"):
        for idx, label in enumerate(lider_labels):
            if lider_opcoes[label] == int(reuniao_atual["id_lider"]):
                lider_index = idx
                break

    presencas_salvas = {}
    visitantes_salvos = []
    tema_atual = ""
    obs_atual = ""
    ofertas_atual = 0.0
    if reuniao_atual is not None:
        tema_atual = reuniao_atual.get("tema", "")
        obs_atual = reuniao_atual.get("observacoes", "")
        ofertas_atual = float(reuniao_atual.get("ofertas", 0) or 0)
        df_pres = carregar_orhafe_presencas(slug, int(reuniao_atual["id_reuniao"]))
        for _, row in df_pres.iterrows():
            if int(row.get("visitante", 0) or 0):
                visitantes_salvos.append(row["nome"])
            elif row.get("id_matricula"):
                presencas_salvas[int(row["id_matricula"])] = bool(row["presente"])

    with st.form("form_orhafe_chamada"):
        c1, c2 = st.columns(2)
        lider_label = c1.selectbox("Lider da chamada", lider_labels, index=lider_index)
        tema = c2.text_input("Tema/assunto da oracao", value=tema_atual)
        ofertas = st.number_input(
            "Ofertas",
            min_value=0.0,
            step=1.0,
            value=ofertas_atual,
            format="%.2f",
        )
        obs = st.text_area("Observacoes", value=obs_atual)

        with st.expander("Lista de chamada", expanded=True):
            dados = matriculas[["id_matricula", "nome"]].copy()
            dados["presente"] = dados["id_matricula"].apply(
                lambda x: presencas_salvas.get(int(x), True)
            )
            editado = st.data_editor(
                dados,
                hide_index=True,
                use_container_width=True,
                disabled=["id_matricula", "nome"],
                column_config={
                    "id_matricula": st.column_config.NumberColumn("ID"),
                    "nome": st.column_config.TextColumn("Nome"),
                    "presente": st.column_config.CheckboxColumn("Presente"),
                },
            )

        with st.expander("Visitantes", expanded=False):
            st.caption("Informe uma visitante por linha e marque a coluna Visitante.")
            base_visitantes = pd.DataFrame(
                {
                    "nome": visitantes_salvos + ["", "", ""],
                    "visitante": [True] * len(visitantes_salvos) + [False, False, False],
                }
            )
            visitantes_edit = st.data_editor(
                base_visitantes,
                hide_index=True,
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "nome": st.column_config.TextColumn("Nome da visitante"),
                    "visitante": st.column_config.CheckboxColumn("Visitante"),
                },
            )

        qtd_matriculadas = int(len(editado))
        qtd_presentes = int(editado["presente"].fillna(False).astype(bool).sum())
        qtd_ausentes = max(qtd_matriculadas - qtd_presentes, 0)
        qtd_visitantes = int(
            visitantes_edit[
                visitantes_edit["visitante"].fillna(False).astype(bool)
                & visitantes_edit["nome"].astype(str).str.strip().ne("")
            ].shape[0]
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Matriculadas", qtd_matriculadas)
        m2.metric("Presentes", qtd_presentes)
        m3.metric("Ausentes", qtd_ausentes)
        m4.metric("Visitantes", qtd_visitantes)

        if st.form_submit_button("Salvar chamada", type="primary"):
            presencas = {
                int(row["id_matricula"]): bool(row["presente"])
                for _, row in editado.iterrows()
            }
            visitantes = visitantes_edit[
                visitantes_edit["visitante"].fillna(False).astype(bool)
            ]["nome"].astype(str).str.strip().tolist()
            salvar_orhafe_chamada(
                slug,
                data_reuniao.isoformat(),
                id_lider=lider_opcoes[lider_label],
                tema=tema,
                observacoes=obs,
                presencas=presencas,
                visitantes=visitantes,
                ofertas=ofertas,
            )
            st.success("Chamada salva.")
            st.rerun()


def _render_relatorios(slug):
    st.markdown("### Relatorios ORHAFE")
    c1, c2 = st.columns(2)
    inicio = c1.date_input("Data inicial", value=_inicio_mes(), key="orhafe_rel_ini")
    fim = c2.date_input("Data final", value=_hoje(), key="orhafe_rel_fim")
    if inicio > fim:
        st.error("A data inicial nao pode ser maior que a data final.")
        return

    reunioes = listar_orhafe_reunioes(slug, inicio.isoformat(), fim.isoformat())
    freq = relatorio_orhafe_frequencia(slug, inicio.isoformat(), fim.isoformat())
    resumo_lideres = _resumo_lideres(reunioes)

    st.markdown("#### Relatorio geral")
    if reunioes.empty:
        st.info("Nenhuma reuniao registrada no periodo selecionado.")
    else:
        totais = _totais_reunioes(reunioes)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de reunioes", totais["Reunioes"])
        c2.metric("Total de presentes", totais["Presentes"])
        c3.metric("Total de ausentes", totais["Ausentes"])
        c4.metric("Total de visitantes", totais["Visitantes"])
        c5, c6 = st.columns(2)
        c5.metric("Total de matriculadas nas chamadas", totais["Matriculadas"])
        c6.metric("Total de ofertas", _moeda(totais["Ofertas"]))

        st.markdown("#### Grafico por lider")
        lideres = sorted(reunioes["lider"].fillna("Sem lider").astype(str).unique().tolist())
        lider_escolhida = st.selectbox("Escolha a lider", lideres, key="grafico_orhafe_lider")
        reunioes_lider = reunioes[
            reunioes["lider"].fillna("Sem lider").astype(str) == lider_escolhida
        ]
        _grafico_totais_orhafe(
            f"Resumo da lider {lider_escolhida}",
            _totais_reunioes(reunioes_lider),
        )

        st.markdown("#### Grafico geral do ORHAFE")
        _grafico_totais_orhafe("Resumo geral do ORHAFE", totais)

        st.markdown("#### Evolucao das reunioes")
        _grafico_reunioes(reunioes)

    st.markdown("#### Resumo por lider")
    _grafico_resumo_lideres(resumo_lideres)
    if not resumo_lideres.empty:
        tabela_lideres = resumo_lideres.copy()
        tabela_lideres["frequencia_pct"] = tabela_lideres["frequencia_pct"].apply(_pct)
        tabela_lideres["ofertas"] = tabela_lideres["ofertas"].apply(_moeda)
        st.dataframe(tabela_lideres, use_container_width=True, hide_index=True)
        st.download_button(
            "Baixar relatorio de lideres CSV",
            data=gerar_csv(resumo_lideres),
            file_name="relatorio_orhafe_lideres.csv",
            mime="text/csv",
        )

    st.markdown("#### Frequencia das matriculadas")
    _grafico_frequencia(freq)

    with st.expander("Reunioes registradas", expanded=False):
        if reunioes.empty:
            st.info("Nenhuma reuniao registrada no periodo.")
        else:
            exibir = reunioes.copy()
            exibir["data"] = exibir["data"].apply(_fmt_data)
            exibir["ofertas"] = exibir["ofertas"].apply(_moeda)
            exibir["frequencia"] = (
                exibir["presentes"].fillna(0)
                / exibir["matriculadas"].replace(0, 1).fillna(1)
                * 100
            ).round(1).apply(_pct)
            st.dataframe(
                exibir[[
                    "data", "lider", "tema", "matriculadas", "presentes",
                    "ausentes", "visitantes", "frequencia", "ofertas",
                    "observacoes",
                ]],
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "Baixar reunioes CSV",
                data=gerar_csv(reunioes),
                file_name="orhafe_reunioes.csv",
                mime="text/csv",
            )

    with st.expander("Relatorio individual por matriculada", expanded=False):
        if freq.empty:
            st.info("Sem dados individuais no periodo.")
        else:
            exibir = freq.copy()
            total = exibir["presencas"] + exibir["ausencias"]
            freq_numerica = (
                exibir["presencas"] / total.where(total > 0, 1) * 100
            ).round(1)
            exibir["frequencia_pct"] = freq_numerica.apply(_pct)
            exibir["acompanhamento"] = freq_numerica.apply(
                lambda v: "Acompanhar em oracao/visita" if v < 60 else "Regular"
            )
            st.dataframe(exibir, use_container_width=True, hide_index=True)
            st.download_button(
                "Baixar relatorio individual CSV",
                data=gerar_csv(freq),
                file_name="orhafe_frequencia.csv",
                mime="text/csv",
            )


def _render_configuracoes(slug):
    st.markdown("### Coordenadoras e lideres")
    coordenadoras = listar_orhafe_coordenadoras(slug, incluir_inativas=True)
    lideres = listar_orhafe_lideres(slug, incluir_inativos=True)
    op_membros, df_membros = _membros_opcoes(slug)

    with st.expander("Cadastrar coordenadora fixa", expanded=coordenadoras.empty):
        if len(coordenadoras[coordenadoras["ativa"] == 1]) >= 4:
            st.info("Ja existem 4 coordenadoras ativas. Inative ou edite uma antes de cadastrar outra.")
        with st.form("form_orhafe_coordenadora"):
            modo_coord = st.radio(
                "Origem da coordenadora",
                ["Cadastro de membros", "Inserir manualmente"],
                horizontal=True,
                key="modo_coord_orhafe",
            )
            id_cadastro_coord = None
            nome = ""
            telefone = ""
            funcao = "Coordenadora"
            if modo_coord == "Cadastro de membros":
                if not op_membros:
                    st.warning("Nao ha membros ativos disponiveis no cadastro.")
                else:
                    membro_label = st.selectbox(
                        "Coordenadora",
                        list(op_membros.keys()),
                        help="A lista traz somente membros ativos cadastrados.",
                    )
                    id_cadastro_coord = op_membros[membro_label]
                    row_membro = df_membros[
                        df_membros["id_cadastro"].astype(int) == int(id_cadastro_coord)
                    ].iloc[0]
                    c1, c2 = st.columns(2)
                    c1.text_input("Nome", value=row_membro.get("nome", ""), disabled=True)
                    c2.text_input("Telefone / WhatsApp", value=row_membro.get("telefone", ""), disabled=True)
                    funcao = row_membro.get("funcao", "") or "Coordenadora"
                    st.text_input("Funcao no cadastro", value=funcao, disabled=True)
            else:
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome da coordenadora")
                telefone = c2.text_input("Telefone / WhatsApp")
                funcao = st.text_input("Funcao", value="Coordenadora")
            ordem = st.number_input("Ordem", min_value=1, max_value=4, value=1, step=1)
            observacoes = st.text_area("Observacoes", key="obs_coord_orhafe")
            if st.form_submit_button("Salvar coordenadora", type="primary"):
                if len(coordenadoras[coordenadoras["ativa"] == 1]) >= 4:
                    st.error("O ORHAFE deve manter no maximo 4 coordenadoras ativas.")
                elif modo_coord == "Cadastro de membros" and not id_cadastro_coord:
                    st.error("Selecione uma coordenadora no cadastro de membros.")
                else:
                    salvar_orhafe_coordenadora(
                        slug,
                        nome,
                        id_cadastro=id_cadastro_coord,
                        telefone=telefone,
                        funcao=funcao,
                        ordem=ordem,
                        ativa=True,
                        observacoes=observacoes,
                    )
                    st.success("Coordenadora salva.")
                    st.rerun()

    if not coordenadoras.empty:
        st.markdown("#### Coordenadoras cadastradas")
        st.dataframe(
            coordenadoras[["id_cadastro", "nome", "telefone", "funcao", "ordem", "ativa", "observacoes"]],
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Cadastrar lider", expanded=lideres.empty):
        if len(lideres[lideres["ativo"] == 1]) >= 5:
            st.info("Ja existem 5 lideres ativos. Inative ou edite uma antes de cadastrar outro.")
        with st.form("form_orhafe_lider"):
            modo_lider = st.radio(
                "Origem da lider",
                ["Cadastro de membros", "Inserir manualmente"],
                horizontal=True,
                key="modo_lider_orhafe",
            )
            id_cadastro_lider = None
            nome = ""
            telefone = ""
            funcao = "Lider"
            if modo_lider == "Cadastro de membros":
                if not op_membros:
                    st.warning("Nao ha membros ativos disponiveis no cadastro.")
                else:
                    membro_label = st.selectbox(
                        "Lider",
                        list(op_membros.keys()),
                        help="A lista traz somente membros ativos cadastrados.",
                        key="lider_membro_orhafe",
                    )
                    id_cadastro_lider = op_membros[membro_label]
                    row_membro = df_membros[
                        df_membros["id_cadastro"].astype(int) == int(id_cadastro_lider)
                    ].iloc[0]
                    c1, c2 = st.columns(2)
                    c1.text_input("Nome", value=row_membro.get("nome", ""), disabled=True, key="lider_nome_auto")
                    c2.text_input(
                        "Telefone / WhatsApp",
                        value=row_membro.get("telefone", ""),
                        disabled=True,
                        key="lider_tel_auto",
                    )
                    funcao = row_membro.get("funcao", "") or "Lider"
                    st.text_input("Funcao no cadastro", value=funcao, disabled=True, key="lider_funcao_auto")
            else:
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome da lider")
                telefone = c2.text_input("Telefone / WhatsApp")
                funcao = st.text_input("Funcao", value="Lider")
            ordem = st.number_input("Ordem", min_value=1, max_value=5, value=1, step=1)
            observacoes = st.text_area("Observacoes", key="obs_lider_orhafe")
            if st.form_submit_button("Salvar lider", type="primary"):
                if len(lideres[lideres["ativo"] == 1]) >= 5:
                    st.error("O ORHAFE deve manter no maximo 5 lideres ativos.")
                elif modo_lider == "Cadastro de membros" and not id_cadastro_lider:
                    st.error("Selecione uma lider no cadastro de membros.")
                else:
                    salvar_orhafe_lider(
                        slug,
                        nome,
                        id_cadastro=id_cadastro_lider,
                        telefone=telefone,
                        funcao=funcao,
                        ordem=ordem,
                        ativo=True,
                        observacoes=observacoes,
                    )
                    st.success("Lider salva.")
                    st.rerun()

    if not lideres.empty:
        st.markdown("#### Lideres cadastradas")
        st.dataframe(
            lideres[["id_cadastro", "nome", "telefone", "funcao", "ordem", "ativo", "observacoes"]],
            use_container_width=True,
            hide_index=True,
        )


def render():
    st.subheader("ORHAFE - Oracao Heroinas da Fe")
    st.caption("Gestao de matriculas, chamadas, visitantes, lideres e relatorios do ministerio de oracao.")
    slug = slug_da_sessao()
    if not slug:
        st.error("Sessao invalida. Faca login novamente.")
        return

    _render_coordenadoras(slug)

    tab_chamada, tab_matriculas, tab_relatorios, tab_config = st.tabs([
        "Chamada",
        "Matriculas",
        "Relatorios",
        "Coordenadoras e lideres",
    ])
    with tab_chamada:
        _render_chamada(slug)
    with tab_matriculas:
        _render_matriculas(slug)
    with tab_relatorios:
        _render_relatorios(slug)
    with tab_config:
        _render_configuracoes(slug)
