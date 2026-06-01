import datetime
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.repository import (
    DIAS_DIZIMISTA_ATIVO_DEFAULT,
    autenticar_igreja,
    carregar_cadastros,
    carregar_lancamentos,
    obter_config_igreja,
)
from utils.helpers import formatar_moeda, gerar_csv, slug_da_sessao


CORES = {
    "entrada": "#10B981",
    "saida": "#EF4444",
    "saldo": "#3B82F6",
    "dizimo": "#8B5CF6",
    "alerta": "#F59E0B",
    "neutro": "#64748B",
}
PALETA = [
    "#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#EC4899",
    "#14B8A6", "#F97316", "#6366F1", "#94A3B8",
]
CONFIG_PLOTLY = {
    "displayModeBar": False,
    "responsive": True,
    "scrollZoom": False,
}
MESES_PT = [
    "", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]


def _sk(nome, slug):
    return f"dashboard_{nome}_{slug}"


def _escape(valor):
    return html.escape(str(valor if valor is not None else ""), quote=True)


def _texto(serie):
    return serie.fillna("").astype(str).str.strip()


def _mes_label(periodo):
    return f"{MESES_PT[periodo.month]}/{str(periodo.year)[-2:]}"


def _normalizar_dados(df_lanc, df_cad):
    df = df_lanc.copy()
    cad = df_cad.copy()
    lanc_obrigatorias = {"id_lancamento", "data", "valor", "tipo", "categoria"}
    cad_obrigatorias = {"id_cadastro", "tipo_cadastro", "situacao", "nome"}
    faltantes = sorted((lanc_obrigatorias - set(df.columns)) | (cad_obrigatorias - set(cad.columns)))
    if faltantes:
        return df, cad, faltantes, {}

    for coluna in (
        "tipo", "categoria", "subcategoria", "descricao", "forma_pagamento",
        "nome_cadastro", "tipo_cadastro", "lote_id",
    ):
        if coluna not in df.columns:
            df[coluna] = ""
        df[coluna] = _texto(df[coluna])

    for coluna in ("tipo_cadastro", "situacao", "nome", "telefone", "funcao"):
        if coluna not in cad.columns:
            cad[coluna] = ""
        cad[coluna] = _texto(cad[coluna])

    if "id_cadastro" not in df.columns:
        df["id_cadastro"] = pd.NA

    datas_txt = _texto(df["data"])
    valores_txt = _texto(df["valor"])
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["id_cadastro"] = pd.to_numeric(df["id_cadastro"], errors="coerce")
    cad["id_cadastro"] = pd.to_numeric(cad["id_cadastro"], errors="coerce")
    df["tipo_norm"] = _texto(df["tipo"]).str.upper()
    df["categoria_norm"] = _texto(df["categoria"]).str.upper()
    df["mes_periodo"] = df["data"].dt.to_period("M")

    qualidade = {
        "datas_invalidas": int((datas_txt.ne("") & df["data"].isna()).sum()),
        "valores_invalidos": int((valores_txt.ne("") & df["valor"].isna()).sum()),
        "valores_nao_positivos": int((df["valor"].fillna(0) <= 0).sum()),
        "sem_vinculo": int(df["id_cadastro"].isna().sum()),
        "despesas_sem_subcategoria": int(
            ((df["tipo_norm"] == "SAIDA") & (_texto(df["subcategoria"]) == "")).sum()
        ),
    }
    df_validos = df[df["data"].notna() & df["valor"].notna() & (df["valor"] > 0)].copy()
    return df_validos, cad, faltantes, qualidade


def _membros_ativos(cad):
    return cad[
        (cad["tipo_cadastro"].str.upper() == "MEMBRO")
        & (cad["situacao"].str.upper() == "ATIVO")
        & cad["id_cadastro"].notna()
    ].copy()


def _periodo(df, inicio, fim):
    return df[df["data"].between(pd.Timestamp(inicio), pd.Timestamp(fim), inclusive="both")].copy()


def _totais(df):
    entradas = float(df[df["tipo_norm"] == "ENTRADA"]["valor"].sum())
    saidas = float(df[df["tipo_norm"] == "SAIDA"]["valor"].sum())
    return entradas, saidas, entradas - saidas


def _variacao(atual, anterior):
    if anterior == 0:
        return "Novo" if atual else "Sem movimento"
    return f"{((atual - anterior) / abs(anterior)) * 100:+.1f}%"


def _participacao_dizimistas(df_periodo, membros):
    ids_ativos = set(membros["id_cadastro"].dropna().astype(int))
    dizimos = df_periodo[
        (df_periodo["tipo_norm"] == "ENTRADA")
        & (df_periodo["categoria_norm"] == "DIZIMO")
    ]
    ids_dizimistas = set(dizimos["id_cadastro"].dropna().astype(int))
    qtd = len(ids_ativos & ids_dizimistas)
    total = len(ids_ativos)
    return qtd, total, (qtd / total * 100) if total else 0.0


def _comparativo_ytd(df, ano, ate_mes):
    atual = df[(df["data"].dt.year == ano) & (df["data"].dt.month <= ate_mes)]
    anterior = df[(df["data"].dt.year == ano - 1) & (df["data"].dt.month <= ate_mes)]
    return _totais(atual), _totais(anterior)


def _serie_mensal(df, fim_mes, quantidade=12):
    meses_com_dados = df.loc[
        df["mes_periodo"].notna() & (df["mes_periodo"] <= fim_mes),
        "mes_periodo",
    ]
    if meses_com_dados.empty:
        return pd.DataFrame(columns=["mes", "rotulo", "entradas", "saidas", "saldo"])

    inicio_mes = max(meses_com_dados.min(), fim_mes - (quantidade - 1))
    meses = [inicio_mes + i for i in range((fim_mes - inicio_mes).n + 1)]
    linhas = []
    for mes in meses:
        sub = df[df["mes_periodo"] == mes]
        entradas, saidas, saldo = _totais(sub)
        linhas.append({
            "mes": mes,
            "rotulo": _mes_label(mes),
            "entradas": entradas,
            "saidas": saidas,
            "saldo": saldo,
        })
    return pd.DataFrame(linhas)


def _faixas_acompanhamento(membros, dizimos, hoje, dias_ativo):
    ultimos = {}
    if not dizimos.empty:
        ultimos = dizimos.groupby("id_cadastro")["data"].max().to_dict()

    limites = sorted(
        {limite for limite in (dias_ativo, 60, 90) if limite >= dias_ativo},
        reverse=True,
    )
    faixas = {"Nunca contribuiu": []}
    faixas.update({f"Mais de {limite} dias": [] for limite in reversed(limites)})
    for _, membro in membros.iterrows():
        id_cadastro = int(membro["id_cadastro"])
        ultima = ultimos.get(id_cadastro)
        if ultima is None or pd.isna(ultima):
            faixa = "Nunca contribuiu"
            dias = None
            ultima_txt = ""
        else:
            ultima_data = pd.Timestamp(ultima).date()
            dias = (hoje - ultima_data).days
            ultima_txt = ultima_data.strftime("%d/%m/%Y")
            faixa = next(
                (f"Mais de {limite} dias" for limite in limites if dias > limite),
                None,
            )
            if faixa is None:
                continue
        faixas[faixa].append({
            "ID": id_cadastro,
            "Nome": membro["nome"],
            "Telefone": membro.get("telefone", ""),
            "Ultima contribuicao": ultima_txt or "Sem registro",
            "Dias sem contribuicao": dias if dias is not None else "Sem registro",
        })
    return faixas


def _layout_grafico(altura=380, margem=None, **extras):
    layout = {
        "template": "plotly_dark",
        "height": altura,
        "margin": margem or dict(t=25, b=35, l=20, r=20),
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": dict(color="#CBD5E1"),
        "hovermode": False,
        "dragmode": False,
    }
    layout.update(extras)
    return layout


def _secao_dashboard(titulo, subtitulo):
    st.markdown(
        f'<div class="dash-section"><strong>{_escape(titulo)}</strong>'
        f'<span>{_escape(subtitulo)}</span></div>',
        unsafe_allow_html=True,
    )


def _grafico_rosca(resumo, rotulos, valores, cores=None, total_label="Total"):
    total = float(resumo[valores].sum())
    fig = go.Figure(go.Pie(
        labels=resumo[rotulos],
        values=resumo[valores],
        hole=.68,
        textinfo="none",
        marker=dict(
            colors=cores or PALETA[:len(resumo)],
            line=dict(color="#1E293B", width=2),
        ),
    ))
    fig.add_annotation(
        text=f"<b>{formatar_moeda(total)}</b><br><span style='font-size:11px'>{total_label}</span>",
        x=.5,
        y=.5,
        showarrow=False,
        font=dict(size=16, color="#F1F5F9"),
    )
    fig.update_layout(**_layout_grafico(
        altura=370,
        showlegend=True,
        legend=dict(orientation="v", y=.5, x=1.02, font=dict(size=11)),
    ))
    return fig


def _grafico_ranking(resumo, rotulos, valores, cor):
    dados = resumo.sort_values(valores, ascending=True)
    fig = go.Figure(go.Bar(
        x=dados[valores],
        y=dados[rotulos],
        orientation="h",
        marker_color=cor,
        text=[formatar_moeda(valor) for valor in dados[valores]],
        textposition="outside",
        textfont=dict(size=10, color="#CBD5E1"),
    ))
    fig.update_layout(**_layout_grafico(
        altura=max(320, len(dados) * 34 + 100),
        xaxis=dict(fixedrange=True, showgrid=False, showticklabels=False),
        yaxis=dict(fixedrange=True, showgrid=False),
    ))
    return fig


def _tabela_monetaria(df, coluna_valor="Valor"):
    tabela = df.copy()
    if coluna_valor in tabela.columns:
        tabela[coluna_valor] = tabela[coluna_valor].apply(formatar_moeda)
    return tabela


def _cartao_atencao(titulo, quantidade, percentual, classe):
    st.markdown(
        f'<div class="pastoral-card {classe}"><div>{_escape(titulo)}</div>'
        f'<strong>{quantidade}</strong><span>{percentual:.1f}% dos membros</span></div>',
        unsafe_allow_html=True,
    )


def _resumo_acompanhamento(membros, dizimos, hoje, dias_ativo):
    ultimos = {}
    if not dizimos.empty:
        ultimos = dizimos.groupby("id_cadastro")["data"].max().to_dict()

    total = len(membros)
    limites = sorted({limite for limite in (dias_ativo, 60, 90) if limite >= dias_ativo})
    resumo = []
    for limite in limites:
        quantidade = 0
        for id_cadastro in membros["id_cadastro"].dropna().astype(int):
            ultima = ultimos.get(id_cadastro)
            if ultima is None or pd.isna(ultima):
                quantidade += 1
            elif (hoje - pd.Timestamp(ultima).date()).days > limite:
                quantidade += 1
        resumo.append({
            "limite": limite,
            "quantidade": quantidade,
            "percentual": (quantidade / total * 100) if total else 0.0,
        })
    return resumo


def _frequencia_membros(membros, dizimos):
    contagem = dizimos.groupby("id_cadastro").size().to_dict() if not dizimos.empty else {}
    valores = dizimos.groupby("id_cadastro")["valor"].sum().to_dict() if not dizimos.empty else {}
    linhas = []
    for _, membro in membros.sort_values("nome").iterrows():
        id_cadastro = int(membro["id_cadastro"])
        linhas.append({
            "ID": id_cadastro,
            "Nome": membro["nome"],
            "Contribuicoes": int(contagem.get(id_cadastro, 0)),
            "Valor total": float(valores.get(id_cadastro, 0.0)),
        })
    return pd.DataFrame(linhas)


def _injetar_css():
    st.markdown("""
    <style>
    .stApp { background-color:#0F172A; }
    h1,h2,h3,h4 { color:#F1F5F9 !important; }
    .dash-card { background:#1E293B;border:1px solid #334155;border-radius:12px;padding:16px;height:100%; }
    .dash-label { color:#94A3B8;font-size:.78rem;text-transform:uppercase;letter-spacing:.04em; }
    .dash-value { color:#F8FAFC;font-size:1.45rem;font-weight:700;margin-top:5px; }
    .dash-note { color:#CBD5E1;font-size:.76rem;margin-top:5px; }
    .stPlotlyChart { background:#1E293B;border:1px solid #334155;border-radius:14px;padding:10px; }
    .dash-section { color:#F1F5F9;font-size:1rem;margin:22px 0 10px;padding-bottom:8px;border-bottom:1px solid #334155; }
    .dash-section span { color:#94A3B8;display:block;font-size:.78rem;font-weight:400;margin-top:3px; }
    .pastoral-card { background:#1E293B;border:1px solid #334155;border-radius:12px;padding:14px;text-align:center;height:100%; }
    .pastoral-card div { color:#CBD5E1;font-size:.78rem; }
    .pastoral-card strong { display:block;font-size:1.9rem;margin-top:5px; }
    .pastoral-card span { color:#94A3B8;font-size:.75rem; }
    .pastoral-card.amarelo strong { color:#F59E0B; }
    .pastoral-card.laranja strong { color:#F97316; }
    .pastoral-card.vermelho strong { color:#EF4444; }
    </style>
    """, unsafe_allow_html=True)


def _card(titulo, valor, nota=""):
    st.markdown(
        f'<div class="dash-card"><div class="dash-label">{_escape(titulo)}</div>'
        f'<div class="dash-value">{_escape(valor)}</div>'
        f'<div class="dash-note">{_escape(nota)}</div></div>',
        unsafe_allow_html=True,
    )


def _autorizacao_pastoral(slug):
    chave = _sk("pastoral_ate", slug)
    agora = datetime.datetime.now().timestamp()
    if st.session_state.get(chave, 0) > agora:
        return True
    st.session_state.pop(chave, None)
    with st.form(_sk("pastoral_form", slug)):
        senha = st.text_input("Confirme a senha da igreja", type="password")
        if st.form_submit_button("Acessar acompanhamento pastoral", type="primary"):
            if autenticar_igreja(slug, senha):
                st.session_state[chave] = agora + 5 * 60
                st.rerun()
            else:
                st.error("Senha incorreta.")
    return False


def render():
    _injetar_css()
    slug = slug_da_sessao()
    df_lanc, df_cad = carregar_lancamentos(slug), carregar_cadastros(slug)
    if df_lanc.empty:
        st.info("Ainda nao ha lancamentos para o dashboard.")
        return

    df, cad, faltantes, qualidade = _normalizar_dados(df_lanc, df_cad)
    if faltantes:
        st.error("Dashboard indisponivel. Colunas ausentes: " + ", ".join(faltantes))
        return
    if df.empty:
        st.error("Nao existem lancamentos validos para calcular o dashboard.")
        return

    membros = _membros_ativos(cad)
    meses = sorted(df["mes_periodo"].dropna().unique(), reverse=True)
    mes_ref = st.selectbox(
        "Mes de referencia",
        meses,
        format_func=_mes_label,
        key=_sk("mes_ref", slug),
    )
    inicio_mes, fim_mes = mes_ref.start_time.date(), mes_ref.end_time.date()
    anterior = mes_ref - 1
    ref, comp = _periodo(df, inicio_mes, fim_mes), df[df["mes_periodo"] == anterior]
    ent, sai, saldo = _totais(ref)
    ent_ant, sai_ant, saldo_ant = _totais(comp)
    qtd_diz, membros_n, pct_diz = _participacao_dizimistas(ref, membros)
    (ent_ytd, sai_ytd, saldo_ytd), (ent_ytd_ant, _, _) = _comparativo_ytd(df, mes_ref.year, mes_ref.month)

    st.markdown("## Dashboard Financeiro")
    st.caption("Visao executiva para decisao, conferencia e acompanhamento de tendencias.")
    c1, c2, c3, c4 = st.columns(4)
    with c1: _card("Entradas", formatar_moeda(ent), f"{_variacao(ent, ent_ant)} vs mes anterior")
    with c2: _card("Saidas", formatar_moeda(sai), f"{_variacao(sai, sai_ant)} vs mes anterior")
    with c3: _card("Saldo", formatar_moeda(saldo), f"{_variacao(saldo, saldo_ant)} vs mes anterior")
    with c4: _card("Participacao dizimistas ativos", f"{pct_diz:.1f}%", f"{qtd_diz} de {membros_n} membros ativos")

    a1, a2, a3 = st.columns(3)
    with a1: _card("Entradas YTD", formatar_moeda(ent_ytd), f"{_variacao(ent_ytd, ent_ytd_ant)} vs mesmo periodo anterior")
    with a2: _card("Saidas YTD", formatar_moeda(sai_ytd))
    with a3: _card("Saldo YTD", formatar_moeda(saldo_ytd))

    tab_visao, tab_despesas, tab_receitas, tab_qualidade, tab_pastoral = st.tabs([
        "Visao Executiva", "Despesas", "Receitas", "Qualidade", "Acompanhamento Pastoral",
    ])    

    with tab_visao:
        _secao_dashboard(
            "Evolucao financeira",
            "Entradas, saidas e saldo acumulado mes a mes nos ultimos 12 meses.",
        )
        serie = _serie_mensal(df, mes_ref)
        fig = go.Figure([
            go.Bar(
                name="Entradas",
                x=serie["rotulo"],
                y=serie["entradas"],
                marker_color=CORES["entrada"],
                text=[formatar_moeda(v) if v else "" for v in serie["entradas"]],
                textposition="outside",
                textfont=dict(size=9, color="#CBD5E1"),
            ),
            go.Bar(
                name="Saidas",
                x=serie["rotulo"],
                y=serie["saidas"],
                marker_color=CORES["saida"],
                text=[formatar_moeda(v) if v else "" for v in serie["saidas"]],
                textposition="outside",
                textfont=dict(size=9, color="#CBD5E1"),
            ),
            go.Scatter(
                name="Saldo",
                x=serie["rotulo"],
                y=serie["saldo"],
                mode="lines+markers",
                line=dict(color=CORES["saldo"], width=3),
            ),
        ])
        fig.update_layout(**_layout_grafico(
            altura=430,
            barmode="group",
            xaxis=dict(fixedrange=True, gridcolor="#334155"),
            yaxis=dict(fixedrange=True, gridcolor="#334155", tickformat=",.0f"),
            legend=dict(orientation="h", y=-.15),
        ))
        st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)

        _secao_dashboard(
            "Composicao do mes",
            "Leitura rapida da relacao entre recursos recebidos e despesas realizadas.",
        )
        composicao = pd.DataFrame({
            "Tipo": ["Entradas", "Saidas"],
            "Valor": [ent, sai],
        })
        if composicao["Valor"].sum() > 0:
            st.plotly_chart(
                _grafico_rosca(
                    composicao,
                    "Tipo",
                    "Valor",
                    [CORES["entrada"], CORES["saida"]],
                    "Movimentado",
                ),
                use_container_width=True,
                config=CONFIG_PLOTLY,
            )

    with tab_despesas:
        saidas = ref[ref["tipo_norm"] == "SAIDA"].copy()
        saidas["subcategoria"] = _texto(saidas["subcategoria"]).replace("", "Sem subcategoria")
        resumo = saidas.groupby("subcategoria", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
        resumo = resumo.rename(columns={"subcategoria": "Subcategoria", "valor": "Valor"})
        _secao_dashboard(
            "Distribuicao das despesas",
            "Participacao de cada subcategoria no total de saidas do mes selecionado.",
        )
        if resumo.empty:
            st.info("Nao ha despesas no mes selecionado.")
        else:
            st.plotly_chart(
                _grafico_rosca(resumo, "Subcategoria", "Valor", PALETA, "Despesas"),
                use_container_width=True,
                config=CONFIG_PLOTLY,
            )
            _secao_dashboard(
                "Ranking de despesas",
                "Subcategorias ordenadas pelo valor realizado no mes.",
            )
            st.plotly_chart(
                _grafico_ranking(resumo, "Subcategoria", "Valor", CORES["saida"]),
                use_container_width=True,
                config=CONFIG_PLOTLY,
            )
            st.dataframe(_tabela_monetaria(resumo), use_container_width=True, hide_index=True)

    with tab_receitas:
        entradas = ref[ref["tipo_norm"] == "ENTRADA"]
        resumo = entradas.groupby("categoria", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
        resumo = resumo.rename(columns={"categoria": "Categoria", "valor": "Valor"})
        _secao_dashboard(
            "Distribuicao das receitas",
            "Participacao de cada categoria no total de entradas do mes selecionado.",
        )
        if resumo.empty:
            st.info("Nao ha receitas no mes selecionado.")
        else:
            st.plotly_chart(
                _grafico_rosca(resumo, "Categoria", "Valor", PALETA, "Receitas"),
                use_container_width=True,
                config=CONFIG_PLOTLY,
            )
            _secao_dashboard(
                "Ranking de receitas",
                "Categorias ordenadas pelo valor recebido no mes.",
            )
            st.plotly_chart(
                _grafico_ranking(resumo, "Categoria", "Valor", CORES["entrada"]),
                use_container_width=True,
                config=CONFIG_PLOTLY,
            )
            st.dataframe(_tabela_monetaria(resumo), use_container_width=True, hide_index=True)

    with tab_qualidade:
        _secao_dashboard(
            "Qualidade dos dados",
            "Pendencias que precisam ser corrigidas para manter os indicadores confiaveis.",
        )
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Datas invalidas", qualidade["datas_invalidas"])
        q2.metric("Valores invalidos", qualidade["valores_invalidos"])
        q3.metric("Sem vinculo", qualidade["sem_vinculo"])
        q4.metric("Despesas sem subcategoria", qualidade["despesas_sem_subcategoria"])
        pendencias = pd.DataFrame({
            "Pendencia": [
                "Datas invalidas",
                "Valores invalidos",
                "Valores nao positivos",
                "Sem vinculo",
                "Despesas sem subcategoria",
            ],
            "Quantidade": [
                qualidade["datas_invalidas"],
                qualidade["valores_invalidos"],
                qualidade["valores_nao_positivos"],
                qualidade["sem_vinculo"],
                qualidade["despesas_sem_subcategoria"],
            ],
        })
        if pendencias["Quantidade"].sum():
            fig_qualidade = go.Figure(go.Bar(
                x=pendencias["Quantidade"],
                y=pendencias["Pendencia"],
                orientation="h",
                marker_color=CORES["alerta"],
                text=pendencias["Quantidade"],
                textposition="outside",
                textfont=dict(size=11, color="#CBD5E1"),
            ))
            fig_qualidade.update_layout(**_layout_grafico(
                altura=340,
                xaxis=dict(fixedrange=True, showgrid=False, showticklabels=False),
                yaxis=dict(fixedrange=True, showgrid=False),
            ))
            st.plotly_chart(fig_qualidade, use_container_width=True, config=CONFIG_PLOTLY)
        else:
            st.success("Nenhuma pendencia identificada nos dados.")
        st.caption("Registros invalidos sao excluidos dos KPIs ate serem corrigidos.")

    with tab_pastoral:
        st.warning(
            "Area restrita. Exibe dados individuais de contribuicao. "
            "Acesse somente quando necessario e nao compartilhe exportacoes sem autorizacao."
        )
        if _autorizacao_pastoral(slug):
            dias_ativo = DIAS_DIZIMISTA_ATIVO_DEFAULT
            try:
                dias_ativo = int(obter_config_igreja(slug, "dias_dizimista_ativo", str(dias_ativo)))
            except (TypeError, ValueError):
                pass

            dizimos = df[(df["tipo_norm"] == "ENTRADA") & (df["categoria_norm"] == "DIZIMO")]
            inicio_12m = (mes_ref - 11).start_time
            fim_12m = mes_ref.end_time
            dizimos_12m = dizimos[dizimos["data"].between(inicio_12m, fim_12m, inclusive="both")]

            _secao_dashboard(
                "Evolucao dos dizimos",
                "Total arrecadado mes a mes nos ultimos 12 meses, com linha de tendencia.",
            )
            serie_dizimos = _serie_mensal(dizimos, mes_ref)
            valores_dizimos = serie_dizimos["entradas"].tolist()
            if not any(valor > 0 for valor in valores_dizimos):
                st.info("Ainda nao ha dizimos registrados para exibir a evolucao mensal.")
            else:
                fig_dizimos = go.Figure(go.Bar(
                    x=serie_dizimos["rotulo"],
                    y=valores_dizimos,
                    marker_color=CORES["dizimo"],
                    text=[formatar_moeda(v) if v else "" for v in valores_dizimos],
                    textposition="outside",
                    textfont=dict(size=10, color="#CBD5E1"),
                    name="Dizimos",
                ))
                if sum(1 for valor in valores_dizimos if valor > 0) >= 3:
                    tendencia = pd.Series(valores_dizimos).rolling(3, min_periods=1).mean()
                    fig_dizimos.add_trace(go.Scatter(
                        x=serie_dizimos["rotulo"],
                        y=tendencia,
                        mode="lines",
                        line=dict(color="#CBD5E1", width=2, dash="dot"),
                        name="Tendencia",
                    ))
                fig_dizimos.update_layout(**_layout_grafico(
                    altura=390,
                    xaxis=dict(fixedrange=True, gridcolor="#334155"),
                    yaxis=dict(fixedrange=True, gridcolor="#334155", tickformat=",.0f"),
                    legend=dict(orientation="h", y=-0.15),
                ))
                st.plotly_chart(fig_dizimos, use_container_width=True, config=CONFIG_PLOTLY)

            _secao_dashboard(
                "Membros que requerem acompanhamento",
                f"Criterio configurado: dizimista ativo quando contribuiu nos ultimos {dias_ativo} dias.",
            )
            resumo_atencao = _resumo_acompanhamento(
                membros, dizimos, datetime.date.today(), dias_ativo
            )
            classes = ["amarelo", "laranja", "vermelho"]
            colunas_atencao = st.columns(len(resumo_atencao))
            for coluna, dados, classe in zip(colunas_atencao, resumo_atencao, classes):
                with coluna:
                    _cartao_atencao(
                        f"Mais de {dados['limite']} dias",
                        dados["quantidade"],
                        dados["percentual"],
                        classe,
                    )

            faixas = _faixas_acompanhamento(membros, dizimos, datetime.date.today(), dias_ativo)
            st.caption(
                "Os cartoes sao cumulativos. As listas abaixo sao exclusivas para evitar "
                "duplicidade. A interpretacao e a eventual abordagem dependem de avaliacao humana."
            )
            for titulo, registros in faixas.items():
                with st.expander(f"{titulo}: {len(registros)} membro(s)"):
                    tabela = pd.DataFrame(registros)
                    if tabela.empty:
                        st.info("Nenhum registro nesta faixa.")
                    else:
                        st.dataframe(tabela, use_container_width=True, hide_index=True)
                        st.download_button(
                            f"Exportar {titulo.lower()}",
                            gerar_csv(tabela),
                            f"acompanhamento_{titulo.lower().replace(' ', '_')}.csv",
                            "text/csv",
                            key=_sk(f"csv_{titulo}", slug),
                        )

            _secao_dashboard(
                "Participacao dos dizimistas",
                "Membros ativos que registraram ao menos uma contribuicao no mes selecionado.",
            )
            qtd_mes, total_membros, percentual_mes = _participacao_dizimistas(ref, membros)
            nao_dizimistas = max(total_membros - qtd_mes, 0)
            if total_membros:
                fig_participacao = go.Figure(go.Pie(
                    labels=["Dizimistas", "Sem contribuicao no mes"],
                    values=[qtd_mes, nao_dizimistas],
                    hole=.7,
                    textinfo="none",
                    marker=dict(colors=[CORES["entrada"], "#374151"], line=dict(color="#1E293B", width=2)),
                ))
                fig_participacao.add_annotation(
                    text=f"<b>{percentual_mes:.1f}%</b><br><span style='font-size:12px'>dizimistas</span>",
                    x=.5,
                    y=.5,
                    showarrow=False,
                    font=dict(size=25, color="#F1F5F9"),
                )
                fig_participacao.update_layout(**_layout_grafico(
                    altura=340,
                    showlegend=True,
                    legend=dict(orientation="h", y=-.05, x=.5, xanchor="center"),
                ))
                st.plotly_chart(fig_participacao, use_container_width=True, config=CONFIG_PLOTLY)
                p1, p2, p3 = st.columns(3)
                p1.metric("Membros ativos", total_membros)
                p2.metric("Dizimistas no mes", qtd_mes)
                p3.metric("Sem contribuicao no mes", nao_dizimistas)
            else:
                st.info("Nao ha membros ativos cadastrados.")

            _secao_dashboard(
                "Frequencia de contribuicoes",
                "Quantidade de registros por membro nos ultimos 12 meses. A lista inclui quem nao contribuiu.",
            )
            frequencia = _frequencia_membros(membros, dizimos_12m)
            if frequencia.empty:
                st.info("Nao ha membros ativos para exibir.")
            else:
                grafico_freq = frequencia.sort_values(["Contribuicoes", "Nome"], ascending=[True, False])
                cores_freq = [
                    CORES["entrada"] if quantidade else "#475569"
                    for quantidade in grafico_freq["Contribuicoes"]
                ]
                fig_freq = go.Figure(go.Bar(
                    x=grafico_freq["Contribuicoes"],
                    y=grafico_freq["Nome"],
                    orientation="h",
                    marker_color=cores_freq,
                    text=[
                        str(quantidade) if quantidade else "Sem contribuicao"
                        for quantidade in grafico_freq["Contribuicoes"]
                    ],
                    textposition="outside",
                    textfont=dict(size=10, color="#CBD5E1"),
                ))
                fig_freq.update_layout(**_layout_grafico(
                    altura=max(340, len(grafico_freq) * 30 + 100),
                    xaxis=dict(fixedrange=True, showgrid=False, showticklabels=False),
                    yaxis=dict(fixedrange=True, showgrid=False),
                ))
                st.plotly_chart(fig_freq, use_container_width=True, config=CONFIG_PLOTLY)
                freq_exportacao = frequencia.copy()
                freq_exportacao["Valor total"] = freq_exportacao["Valor total"].apply(formatar_moeda)
                st.download_button(
                    "Exportar lista completa de frequencia",
                    gerar_csv(freq_exportacao),
                    "frequencia_dizimos_12_meses.csv",
                    "text/csv",
                    key=_sk("csv_frequencia", slug),
                )

            _secao_dashboard(
                "Consulta individual",
                "Historico do membro selecionado e distribuicao mensal das contribuicoes.",
            )
            opcoes = {
                f"{int(row['id_cadastro'])} | {row['nome']}": int(row["id_cadastro"])
                for _, row in membros.sort_values("nome").iterrows()
            }
            if opcoes:
                selecionado = st.selectbox("Consultar membro", ["Selecione"] + list(opcoes), key=_sk("membro", slug))
                if selecionado != "Selecione":
                    id_membro = opcoes[selecionado]
                    dados = dizimos[dizimos["id_cadastro"] == id_membro].copy()
                    ultimos_dados = dados.sort_values("data", ascending=False)
                    ultima_data = (
                        ultimos_dados.iloc[0]["data"].strftime("%d/%m/%Y")
                        if not ultimos_dados.empty else "Sem registro"
                    )
                    i1, i2, i3 = st.columns(3)
                    i1.metric("Contribuicoes registradas", len(dados))
                    i2.metric("Valor total registrado", formatar_moeda(dados["valor"].sum()))
                    i3.metric("Ultima contribuicao", ultima_data)
                    if dados.empty:
                        st.info("Nao ha contribuicoes registradas no periodo analisado.")
                    else:
                        mensal = (
                            dados.groupby("mes_periodo", as_index=False)["valor"].sum()
                            .sort_values("mes_periodo")
                        )
                        fig_membro = go.Figure(go.Bar(
                            x=[_mes_label(periodo) for periodo in mensal["mes_periodo"]],
                            y=mensal["valor"],
                            marker_color=CORES["dizimo"],
                            text=[formatar_moeda(valor) for valor in mensal["valor"]],
                            textposition="outside",
                            textfont=dict(size=10, color="#CBD5E1"),
                        ))
                        fig_membro.update_layout(**_layout_grafico(
                            altura=320,
                            xaxis=dict(fixedrange=True, gridcolor="#334155"),
                            yaxis=dict(fixedrange=True, gridcolor="#334155", tickformat=",.0f"),
                        ))
                        st.plotly_chart(fig_membro, use_container_width=True, config=CONFIG_PLOTLY)
                        detalhe = dados[["data", "valor", "forma_pagamento", "descricao"]].copy()
                        detalhe = detalhe.sort_values("data", ascending=False)
                        detalhe["data"] = detalhe["data"].dt.strftime("%d/%m/%Y")
                        detalhe["valor"] = detalhe["valor"].apply(formatar_moeda)
                        st.dataframe(detalhe, use_container_width=True, hide_index=True)

    st.divider()
    st.download_button(
        "Exportar dados do mes",
        gerar_csv(ref),
        f"dashboard_{mes_ref}.csv",
        "text/csv",
        key=_sk("csv_mes", slug),
    )
