import datetime
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.repository import (
    DIAS_DIZIMISTA_ATIVO_DEFAULT,
    autenticar_senha_pastoral,
    carregar_cadastros,
    carregar_lancamentos,
    listar_orhafe_coordenadoras,
    listar_orhafe_lideres,
    listar_orhafe_reunioes,
    obter_config_igreja,
    relatorio_orhafe_visitantes,
    senha_pastoral_configurada,
)
from utils.helpers import formatar_moeda, gerar_csv, slug_da_sessao


CORES = {
    "entrada": "#1D9E75",
    "saida": "#D85A30",
    "saldo": "#185FA5",
    "dizimo": "#185FA5",
    "despesa": "#D85A30",
    "funcao": "#534AB7",
    "alerta": "#F59E0B",
    "neutro": "#64748B",
}
PALETA = [
    "#1D9E75", "#185FA5", "#D85A30", "#534AB7", "#F59E0B",
    "#0F6E56", "#378ADD", "#D4537E", "#888780",
]
CONFIG_PLOTLY = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
    "doubleClick": False,
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
        "autosize": True,
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


def _legenda_cores():
    itens = [
        ("Entradas", CORES["entrada"]),
        ("Saidas e despesas", CORES["saida"]),
        ("Saldo e dizimos", CORES["saldo"]),
        ("Funcoes", CORES["funcao"]),
        ("Alertas", CORES["alerta"]),
    ]
    legenda = ['<div class="dash-legenda">']
    for titulo, cor in itens:
        legenda.append(
            f'<span><i style="background:{_escape(cor)}"></i>{_escape(titulo)}</span>'
        )
    legenda.append("</div>")
    st.markdown("".join(legenda), unsafe_allow_html=True)


def _grafico_rosca(
    resumo,
    rotulos,
    valores,
    cores=None,
    total_label="Total",
    valor_central=None,
    label_central=None,
    cor_central="#F1F5F9",
):
    total = float(resumo[valores].sum())
    valor_centro = total if valor_central is None else float(valor_central)
    label_centro = total_label if label_central is None else label_central
    percentuais = [
        (float(valor) / total * 100) if total else 0.0
        for valor in resumo[valores]
    ]
    legendas = [
        f"{rotulo} {percentual:.1f}%"
        for rotulo, percentual in zip(resumo[rotulos], percentuais)
    ]
    fig = go.Figure(go.Pie(
        name=total_label,
        labels=legendas,
        values=resumo[valores],
        hole=.68,
        textinfo="percent",
        textposition="outside",
        textfont=dict(size=12, color="#CBD5E1"),
        hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
        customdata=[formatar_moeda(valor) for valor in resumo[valores]],
        marker=dict(
            colors=cores or PALETA[:len(resumo)],
            line=dict(color="#1E293B", width=2),
        ),
    ))
    fig.add_annotation(
        text=f"<b>{formatar_moeda(valor_centro)}</b><br><span style='font-size:11px'>{label_centro}</span>",
        x=.5,
        y=.5,
        showarrow=False,
        font=dict(size=16, color=cor_central),
    )
    fig.update_layout(**_layout_grafico(
        altura=560,
        margem=dict(t=30, b=175, l=105, r=105),
        showlegend=True,
        legend=dict(
            orientation="h",
            y=-.30,
            yanchor="top",
            x=.5,
            xanchor="center",
            font=dict(size=11, color="#E2E8F0"),
        ),
    ))
    return fig


def _grafico_ranking(resumo, rotulos, valores, cor):
    dados = resumo.sort_values(valores, ascending=True)
    fig = go.Figure(go.Bar(
        name="Valor",
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
        showlegend=False,
        xaxis=dict(fixedrange=True, showgrid=False, showticklabels=False),
        yaxis=dict(fixedrange=True, showgrid=False),
    ))
    return fig


def _orhafe_contar_visitantes(visitantes, lider=None):
    if visitantes is None or visitantes.empty:
        return 0
    dados = visitantes.copy()
    if lider is not None:
        dados = dados[
            _texto(dados["lider"]).replace("", "Sem lider") == str(lider)
        ].copy()
    if dados.empty or "nome" not in dados.columns:
        return 0
    nomes = _texto(dados["nome"]).str.lower()
    return int(nomes[nomes.ne("")].nunique())


def _orhafe_indicadores_resumo(reunioes, visitantes=None, lider=None):
    if reunioes.empty:
        return {
            "Presenca media (%)": 0.0,
            "Ausencia media (%)": 0.0,
            "Visitantes": 0,
            "Ofertas": 0.0,
        }

    matriculadas = pd.to_numeric(reunioes["matriculadas"], errors="coerce").fillna(0)
    presentes = pd.to_numeric(reunioes["presentes"], errors="coerce").fillna(0)
    ausentes = pd.to_numeric(reunioes["ausentes"], errors="coerce").fillna(0)
    media_matriculadas = float(matriculadas.mean()) if not matriculadas.empty else 0.0
    media_presentes = float(presentes.mean()) if not presentes.empty else 0.0
    media_ausentes = float(ausentes.mean()) if not ausentes.empty else 0.0
    if media_matriculadas > 0:
        presenca_pct = media_presentes / media_matriculadas * 100
        ausencia_pct = media_ausentes / media_matriculadas * 100
    else:
        presenca_pct = 0.0
        ausencia_pct = 0.0
    return {
        "Presenca media (%)": round(presenca_pct, 1),
        "Ausencia media (%)": round(ausencia_pct, 1),
        "Visitantes": _orhafe_contar_visitantes(visitantes, lider),
        "Ofertas": float(pd.to_numeric(reunioes["ofertas"], errors="coerce").fillna(0).sum()),
    }


def _orhafe_resumo_lideres(reunioes, visitantes=None):
    if reunioes.empty:
        return pd.DataFrame(columns=[
            "lider", "reunioes", "presenca_media_pct", "ausencia_media_pct",
            "visitantes", "ofertas",
        ])
    dados = reunioes.copy()
    dados["lider"] = _texto(dados["lider"]).replace("", "Sem lider")
    for coluna in ("matriculadas", "presentes", "ausentes", "ofertas"):
        dados[coluna] = pd.to_numeric(dados[coluna], errors="coerce").fillna(0)
    resumo = dados.groupby("lider", as_index=False).agg(
        reunioes=("id_reuniao", "nunique"),
        media_matriculadas=("matriculadas", "mean"),
        media_presentes=("presentes", "mean"),
        media_ausentes=("ausentes", "mean"),
        ofertas=("ofertas", "sum"),
    )
    resumo["presenca_media_pct"] = (
        resumo["media_presentes"] / resumo["media_matriculadas"].where(resumo["media_matriculadas"] > 0, 1) * 100
    ).round(1)
    resumo["ausencia_media_pct"] = (
        resumo["media_ausentes"] / resumo["media_matriculadas"].where(resumo["media_matriculadas"] > 0, 1) * 100
    ).round(1)
    resumo["visitantes"] = resumo["lider"].apply(
        lambda lider: _orhafe_contar_visitantes(visitantes, lider)
    )
    return resumo.sort_values("lider")


def _grafico_orhafe_resumo(titulo, dados):
    df = pd.DataFrame(
        [{"Indicador": chave, "Valor": valor} for chave, valor in dados.items()]
    )
    fig = go.Figure(go.Bar(
        name="Indicador",
        x=df["Indicador"],
        y=df["Valor"],
        marker_color=[CORES["entrada"], CORES["saida"], CORES["alerta"], CORES["funcao"]][:len(df)],
        text=[
            formatar_moeda(valor)
            if indicador == "Ofertas"
            else f"{valor:.1f}%"
            if "(%)" in indicador
            else str(int(valor))
            for indicador, valor in zip(df["Indicador"], df["Valor"])
        ],
        textposition="outside",
        textfont=dict(size=10, color="#CBD5E1"),
    ))
    fig.update_layout(**_layout_grafico(
        altura=360,
        margem=dict(t=55, b=85, l=20, r=20),
        showlegend=False,
        xaxis=dict(fixedrange=True, showgrid=False),
        yaxis=dict(fixedrange=True, gridcolor="#334155"),
    ))
    fig.update_layout(title=titulo)
    return fig


def _grafico_orhafe_por_lider(resumo):
    dados = resumo.sort_values("presenca_media_pct", ascending=True)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Presenca media",
        x=dados["presenca_media_pct"],
        y=dados["lider"],
        orientation="h",
        marker_color=CORES["entrada"],
        text=[f"{valor:.1f}%" for valor in dados["presenca_media_pct"]],
        textposition="outside",
        textfont=dict(size=10, color="#CBD5E1"),
    ))
    fig.add_trace(go.Bar(
        name="Ausencia media",
        x=dados["ausencia_media_pct"],
        y=dados["lider"],
        orientation="h",
        marker_color=CORES["saida"],
        text=[f"{valor:.1f}%" for valor in dados["ausencia_media_pct"]],
        textposition="outside",
        textfont=dict(size=10, color="#CBD5E1"),
    ))
    fig.update_layout(**_layout_grafico(
        altura=max(340, len(dados) * 74 + 120),
        margem=dict(t=60, b=45, l=20, r=40),
        barmode="group",
        showlegend=True,
        xaxis=dict(fixedrange=True, gridcolor="#334155", range=[0, 105]),
        yaxis=dict(fixedrange=True, showgrid=False),
        legend=dict(orientation="h", y=1.12, x=0),
    ))
    fig.update_layout(title="Resumo por lider")
    return fig


def _tabela_monetaria(df, coluna_valor="Valor"):
    tabela = df.copy()
    if coluna_valor in tabela.columns:
        tabela[coluna_valor] = tabela[coluna_valor].apply(formatar_moeda)
    return tabela


def _numero_config(valor, padrao=0.0):
    texto = str(valor or "").strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = float(texto)
    except (TypeError, ValueError):
        return float(padrao)
    return numero if numero >= 0 else float(padrao)


def _indicadores_saude(df, mes_ref, reserva, meta_reserva):
    serie = _serie_mensal(df, mes_ref, quantidade=6)
    recentes = serie.tail(3)
    media_entradas = float(recentes["entradas"].mean()) if not recentes.empty else 0.0
    media_saidas = float(recentes["saidas"].mean()) if not recentes.empty else 0.0
    resultado_medio = media_entradas - media_saidas
    cobertura = (reserva / media_saidas) if media_saidas > 0 else None
    ate_referencia = df[df["mes_periodo"] <= mes_ref]
    saldo_acumulado = _totais(ate_referencia)[2]
    projecoes = pd.DataFrame({
        "Horizonte": ["30 dias", "60 dias", "90 dias"],
        "Meses": [1, 2, 3],
    })
    projecoes["Saldo projetado"] = (
        saldo_acumulado + projecoes["Meses"] * resultado_medio
    )

    alertas = []
    if cobertura is not None and cobertura < meta_reserva:
        alertas.append((
            "critico",
            f"A reserva cobre {cobertura:.1f} mes(es), abaixo da meta de {meta_reserva} mes(es).",
        ))
    if saldo_acumulado < 0:
        alertas.append((
            "critico",
            "O saldo acumulado dos lancamentos registrados esta negativo.",
        ))
    if not serie.empty and float(serie.iloc[-1]["saldo"]) < 0:
        alertas.append((
            "atencao",
            "O mes selecionado fechou com mais saidas do que entradas.",
        ))
    if len(serie) >= 2:
        saida_atual = float(serie.iloc[-1]["saidas"])
        saida_anterior = float(serie.iloc[-2]["saidas"])
        if saida_anterior > 0 and saida_atual > saida_anterior * 1.2:
            variacao = ((saida_atual - saida_anterior) / saida_anterior) * 100
            alertas.append((
                "atencao",
                f"As despesas cresceram {variacao:.1f}% em relacao ao mes anterior.",
            ))
    if len(serie) >= 3:
        entradas = serie["entradas"].tail(3).tolist()
        if entradas[0] > entradas[1] > entradas[2]:
            alertas.append((
                "atencao",
                "As entradas cairam por dois meses consecutivos.",
            ))
    if (projecoes["Saldo projetado"] < 0).any():
        primeiro = projecoes[projecoes["Saldo projetado"] < 0].iloc[0]["Horizonte"]
        alertas.append((
            "critico",
            f"A projecao indica saldo negativo em ate {primeiro}.",
        ))

    return {
        "serie": serie,
        "media_entradas": media_entradas,
        "media_saidas": media_saidas,
        "resultado_medio": resultado_medio,
        "cobertura": cobertura,
        "saldo_acumulado": saldo_acumulado,
        "projecoes": projecoes,
        "alertas": alertas,
    }


def _render_saude_financeira(df, mes_ref, slug):
    reserva = _numero_config(
        obter_config_igreja(slug, "reserva_financeira_disponivel", "0")
    )
    meta_reserva = int(_numero_config(
        obter_config_igreja(slug, "meta_reserva_meses", "3"), 3
    ))
    if meta_reserva < 1:
        meta_reserva = 3
    saude = _indicadores_saude(df, mes_ref, reserva, meta_reserva)

    _secao_dashboard(
        "Saude financeira",
        "Indicadores para apoio a decisao. A projecao utiliza os lancamentos registrados e a media dos ultimos tres meses.",
    )
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        _card("Reserva disponivel", formatar_moeda(reserva), "Configurada em Minha Conta")
    with s2:
        cobertura = saude["cobertura"]
        valor_cobertura = f"{cobertura:.1f} mes(es)" if cobertura is not None else "Sem despesas"
        _card("Cobertura da reserva", valor_cobertura, f"Meta: {meta_reserva} mes(es)")
    with s3:
        _card("Despesa media mensal", formatar_moeda(saude["media_saidas"]), "Media dos ultimos 3 meses")
    with s4:
        _card("Resultado medio mensal", formatar_moeda(saude["resultado_medio"]), "Entradas - saidas")

    _secao_dashboard(
        "Alertas executivos",
        "Pontos que merecem avaliacao antes de assumir novos compromissos financeiros.",
    )
    if saude["alertas"]:
        for nivel, mensagem in saude["alertas"]:
            st.markdown(
                f'<div class="saude-alerta {nivel}">{_escape(mensagem)}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.success("Nenhum alerta financeiro relevante foi identificado.")

    _secao_dashboard(
        "Projecao de caixa",
        "Estimativa baseada no saldo acumulado registrado e no resultado medio mensal recente.",
    )
    projecoes = saude["projecoes"]
    fig_projecao = go.Figure(go.Bar(
        x=projecoes["Horizonte"],
        y=projecoes["Saldo projetado"],
        marker_color=[
            CORES["entrada"] if valor >= 0 else CORES["saida"]
            for valor in projecoes["Saldo projetado"]
        ],
        text=[formatar_moeda(valor) for valor in projecoes["Saldo projetado"]],
        textposition="outside",
        textfont=dict(size=11, color="#CBD5E1"),
    ))
    fig_projecao.update_layout(**_layout_grafico(
        altura=340,
        xaxis=dict(fixedrange=True, showgrid=False),
        yaxis=dict(fixedrange=True, gridcolor="#334155", tickformat=",.0f"),
    ))
    st.plotly_chart(fig_projecao, use_container_width=True, config=CONFIG_PLOTLY)
    st.caption(
        f"Saldo acumulado registrado ate {_mes_label(mes_ref)}: "
        f"{formatar_moeda(saude['saldo_acumulado'])}. "
        "A projecao nao substitui conciliacao bancaria nem planejamento orcamentario."
    )


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


def _meses_periodo(inicio, fim):
    primeiro = pd.Period(inicio, freq="M")
    ultimo = pd.Period(fim, freq="M")
    return [primeiro + i for i in range((ultimo - primeiro).n + 1)]


def _resumo_individual_mensal(dados, meses):
    resumo = {}
    if not dados.empty:
        resumo = (
            dados.groupby("mes_periodo")["valor"]
            .agg(["count", "sum"])
            .to_dict("index")
        )

    linhas = []
    for mes in meses:
        registro = resumo.get(mes, {})
        linhas.append({
            "mes": mes,
            "rotulo": _mes_label(mes),
            "quantidade": int(registro.get("count", 0)),
            "valor": float(registro.get("sum", 0.0)),
        })
    return linhas


def _avaliacao_fidelidade(resumo_mensal):
    total_meses = len(resumo_mensal)
    meses_com_contribuicao = sum(1 for mes in resumo_mensal if mes["quantidade"] > 0)
    taxa = (meses_com_contribuicao / total_meses * 100) if total_meses else 0.0
    if meses_com_contribuicao == 0:
        return taxa, "Sem contribuicoes no periodo", "critico"
    if taxa < 50:
        return taxa, "Frequencia baixa: avaliar necessidade de acompanhamento pastoral", "atencao"
    if taxa < 80:
        return taxa, "Frequencia moderada: observar a regularidade das contribuicoes", "moderado"
    return taxa, "Boa regularidade de contribuicoes no periodo", "positivo"


def _cartoes_fidelidade(resumo_mensal):
    cartoes = ['<div class="fidelidade-grid">']
    for mes in resumo_mensal:
        if mes["quantidade"]:
            classe = "presente"
            detalhe = f'{mes["quantidade"]}x | {formatar_moeda(mes["valor"])}'
        else:
            classe = "ausente"
            detalhe = "Sem dizimo"
        cartoes.append(
            f'<div class="fidelidade-mes {classe}"><strong>{_escape(mes["rotulo"])}</strong>'
            f'<span>{_escape(detalhe)}</span></div>'
        )
    cartoes.append("</div>")
    st.markdown("".join(cartoes), unsafe_allow_html=True)


def _mensagem_fidelidade(nome, resumo_mensal):
    taxa, titulo, classe = _avaliacao_fidelidade(resumo_mensal)
    meses_presentes = sum(1 for mes in resumo_mensal if mes["quantidade"] > 0)
    total_meses = len(resumo_mensal)
    complemento = (
        "Recomenda-se avaliacao humana e, quando apropriado, contato ou visita pastoral."
        if classe in {"critico", "atencao"}
        else "Use esta informacao como apoio ao acompanhamento pastoral."
    )
    st.markdown(
        f'<div class="fidelidade-aviso {classe}"><strong>{_escape(titulo)}</strong>'
        f'<span>{_escape(nome)} contribuiu em {meses_presentes} de {total_meses} meses '
        f'({taxa:.1f}% de fidelidade mensal). {_escape(complemento)}</span></div>',
        unsafe_allow_html=True,
    )


def _injetar_css():
    st.markdown("""
    <style>
    .stApp { background-color:#0F172A; }
    h1,h2,h3,h4 { color:#F1F5F9 !important; }
    .dash-card { background:#1E293B;border:1px solid #334155;border-radius:12px;padding:16px;height:100%; }
    .dash-label { color:#94A3B8;font-size:.78rem;text-transform:uppercase;letter-spacing:.04em; }
    .dash-value { color:#F8FAFC;font-size:1.45rem;font-weight:700;margin-top:5px; }
    .dash-note { color:#CBD5E1;font-size:.76rem;margin-top:5px; }
    .stPlotlyChart, [data-testid="stPlotlyChart"] {
        background:#1E293B;
        border:1px solid #334155;
        border-radius:14px;
        box-shadow:0 10px 24px rgba(0,0,0,.28);
        box-sizing:border-box;
        max-width:100%;
        min-width:0;
        overflow:hidden;
        padding:10px;
        width:100%;
    }
    [data-testid="stPlotlyChart"] > div,
    [data-testid="stPlotlyChart"] .js-plotly-plot,
    [data-testid="stPlotlyChart"] .plot-container,
    [data-testid="stPlotlyChart"] .svg-container {
        box-sizing:border-box;
        max-width:100%!important;
        min-width:0!important;
        width:100%!important;
    }
    @media (max-width:640px) {
        .stPlotlyChart, [data-testid="stPlotlyChart"] {
            border-radius:10px;
            box-shadow:0 6px 16px rgba(0,0,0,.24);
            padding:4px;
        }
    }
    .dash-section { color:#F1F5F9;font-size:1rem;margin:22px 0 10px;padding-bottom:8px;border-bottom:1px solid #334155; }
    .dash-section span { color:#94A3B8;display:block;font-size:.78rem;font-weight:400;margin-top:3px; }
    .dash-legenda { display:flex;flex-wrap:wrap;gap:9px 16px;margin:10px 0 14px; }
    .dash-legenda span { color:#CBD5E1;font-size:.78rem;white-space:nowrap; }
    .dash-legenda i { border-radius:50%;display:inline-block;height:10px;margin-right:6px;width:10px; }
    .pastoral-card { background:#1E293B;border:1px solid #334155;border-radius:12px;padding:14px;text-align:center;height:100%; }
    .pastoral-card div { color:#CBD5E1;font-size:.78rem; }
    .pastoral-card strong { display:block;font-size:1.9rem;margin-top:5px; }
    .pastoral-card span { color:#94A3B8;font-size:.75rem; }
    .pastoral-card.amarelo strong { color:#F59E0B; }
    .pastoral-card.laranja strong { color:#F97316; }
    .pastoral-card.vermelho strong { color:#EF4444; }
    .fidelidade-grid { display:flex;flex-wrap:wrap;gap:8px;margin:14px 0; }
    .fidelidade-mes { border-radius:8px;min-width:96px;padding:9px 11px;text-align:center; }
    .fidelidade-mes strong { display:block;font-size:.8rem; }
    .fidelidade-mes span { display:block;font-size:.7rem;margin-top:4px; }
    .fidelidade-mes.presente { background:#065F46;color:#ECFDF5; }
    .fidelidade-mes.ausente { background:#374151;color:#CBD5E1;opacity:.75; }
    .fidelidade-aviso { background:#1E293B;border-left:4px solid;border-radius:8px;margin:12px 0 18px;padding:13px 16px; }
    .fidelidade-aviso strong { display:block;font-size:.95rem; }
    .fidelidade-aviso span { color:#CBD5E1;display:block;font-size:.82rem;margin-top:5px; }
    .fidelidade-aviso.critico { border-color:#DC2626; }
    .fidelidade-aviso.critico strong { color:#F87171; }
    .fidelidade-aviso.atencao { border-color:#F97316; }
    .fidelidade-aviso.atencao strong { color:#FB923C; }
    .fidelidade-aviso.moderado { border-color:#F59E0B; }
    .fidelidade-aviso.moderado strong { color:#FBBF24; }
    .fidelidade-aviso.positivo { border-color:#10B981; }
    .fidelidade-aviso.positivo strong { color:#34D399; }
    .saude-alerta { background:#1E293B;border-left:4px solid;border-radius:8px;
        color:#CBD5E1;font-size:.86rem;margin:8px 0;padding:12px 15px; }
    .saude-alerta.critico { border-color:#DC2626; }
    .saude-alerta.atencao { border-color:#F59E0B; }
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
    if not senha_pastoral_configurada(slug):
        st.info(
            "Cadastre uma senha exclusiva para o acompanhamento pastoral "
            "na pagina Minha Conta."
        )
        return False
    with st.form(_sk("pastoral_form", slug)):
        senha = st.text_input("Senha do acompanhamento pastoral", type="password")
        if st.form_submit_button("Acessar acompanhamento pastoral", type="primary"):
            if autenticar_senha_pastoral(slug, senha):
                st.session_state[chave] = agora + 5 * 60
                st.rerun()
            else:
                st.error("Senha pastoral incorreta.")
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
    dashboard_restrito = st.session_state.get("modo") == "pastor_auxiliar"
    if dashboard_restrito:
        st.info(
            "Acesso de Pastor Auxiliar: as areas Saude Financeira, Qualidade "
            "e Acompanhamento Pastoral nao estao disponiveis neste perfil."
        )
    _legenda_cores()
    c1, c2, c3, c4 = st.columns(4)
    with c1: _card("Entradas", formatar_moeda(ent), f"{_variacao(ent, ent_ant)} vs mes anterior")
    with c2: _card("Saidas", formatar_moeda(sai), f"{_variacao(sai, sai_ant)} vs mes anterior")
    with c3: _card("Saldo", formatar_moeda(saldo), f"{_variacao(saldo, saldo_ant)} vs mes anterior")
    with c4: _card("Participacao dizimistas ativos", f"{pct_diz:.1f}%", f"{qtd_diz} de {membros_n} membros ativos")

    a1, a2, a3 = st.columns(3)
    with a1: _card("Entradas YTD", formatar_moeda(ent_ytd), f"{_variacao(ent_ytd, ent_ytd_ant)} vs mesmo periodo anterior")
    with a2: _card("Saidas YTD", formatar_moeda(sai_ytd))
    with a3: _card("Saldo YTD", formatar_moeda(saldo_ytd))

    tab_visao, tab_saude, tab_despesas, tab_receitas, tab_qualidade, tab_pastoral = st.tabs([
        "Visao Executiva", "Saude Financeira", "Despesas", "Receitas", "Qualidade",
        "Acompanhamento Pastoral",
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
            margem=dict(t=55, b=40, l=20, r=20),
            barmode="group",
            showlegend=True,
            xaxis=dict(fixedrange=True, gridcolor="#334155"),
            yaxis=dict(fixedrange=True, gridcolor="#334155", tickformat=",.0f"),
            legend=dict(orientation="h", y=1.12, x=0),
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
                    "Composicao",
                    valor_central=saldo,
                    label_central="Saldo do mes",
                    cor_central=CORES["entrada"] if saldo >= 0 else CORES["saida"],
                ),
                use_container_width=True,
                config=CONFIG_PLOTLY,
            )

    with tab_saude:
        if dashboard_restrito:
            st.warning("Area nao disponivel para o perfil Pastor Auxiliar.")
        else:
            _render_saude_financeira(df, mes_ref, slug)

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
                _grafico_ranking(resumo, "Subcategoria", "Valor", CORES["despesa"]),
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
        if dashboard_restrito:
            st.warning("Area nao disponivel para o perfil Pastor Auxiliar.")
            return
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
        pendencias["Status"] = pendencias["Quantidade"].apply(
            lambda qtd: "Pendente" if qtd else "OK"
        )
        pendencias["Acao sugerida"] = [
            "Corrigir ou excluir lancamentos com data ausente/invalida.",
            "Corrigir valores que nao foram reconhecidos como numero.",
            "Revisar lancamentos com valor zerado ou negativo.",
            "Vincular lancamentos a membro ou fornecedor quando aplicavel.",
            "Classificar despesas em uma subcategoria.",
        ]
        if pendencias["Quantidade"].sum():
            fig_qualidade = go.Figure(go.Bar(
                name="Pendencias",
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
                showlegend=False,
                xaxis=dict(fixedrange=True, showgrid=False, showticklabels=False),
                yaxis=dict(fixedrange=True, showgrid=False),
            ))
            st.plotly_chart(fig_qualidade, use_container_width=True, config=CONFIG_PLOTLY)
        else:
            st.success("Nenhuma pendencia identificada nos dados.")
        st.markdown("#### Tabela de pendencias")
        st.dataframe(
            pendencias[["Pendencia", "Quantidade", "Status", "Acao sugerida"]],
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Registros invalidos sao excluidos dos KPIs ate serem corrigidos.")

    with tab_pastoral:
        if dashboard_restrito:
            st.warning("Area nao disponivel para o perfil Pastor Auxiliar.")
            return
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
            inicio_padrao = max(df["data"].min().date(), (mes_ref - 11).start_time.date())
            fim_padrao = min(df["data"].max().date(), mes_ref.end_time.date())
            f1, f2 = st.columns(2)
            with f1:
                inicio_pastoral = st.date_input(
                    "Analisar contribuicoes de",
                    value=inicio_padrao,
                    format="DD/MM/YYYY",
                    key=_sk("pastoral_inicio", slug),
                )
            with f2:
                fim_pastoral = st.date_input(
                    "Ate",
                    value=fim_padrao,
                    format="DD/MM/YYYY",
                    key=_sk("pastoral_fim", slug),
                )
            if inicio_pastoral > fim_pastoral:
                st.error("A data inicial nao pode ser posterior a data final.")
                inicio_pastoral = fim_pastoral

            df_pastoral = _periodo(df, inicio_pastoral, fim_pastoral)
            dizimos_periodo = df_pastoral[
                (df_pastoral["tipo_norm"] == "ENTRADA")
                & (df_pastoral["categoria_norm"] == "DIZIMO")
            ]
            mes_fim_pastoral = pd.Period(fim_pastoral, freq="M")
            mes_inicio_pastoral = pd.Period(inicio_pastoral, freq="M")
            qtd_meses_pastoral = max(1, (mes_fim_pastoral - mes_inicio_pastoral).n + 1)

            _secao_dashboard(
                "CÃ­rculo de OraÃ§Ã£o",
                "Resumo pastoral das chamadas no perÃ­odo selecionado.",
            )
            try:
                reunioes_orhafe = listar_orhafe_reunioes(
                    slug,
                    inicio_pastoral.isoformat(),
                    fim_pastoral.isoformat(),
                )
                visitantes_orhafe = relatorio_orhafe_visitantes(
                    slug,
                    inicio_pastoral.isoformat(),
                    fim_pastoral.isoformat(),
                )
                lideres_cadastradas_orhafe = listar_orhafe_lideres(slug)
                coordenadoras_cadastradas_orhafe = listar_orhafe_coordenadoras(slug)
            except Exception as exc:
                st.warning(f"NÃ£o foi possÃ­vel carregar os indicadores do CÃ­rculo de OraÃ§Ã£o: {exc}")
                reunioes_orhafe = pd.DataFrame()
                visitantes_orhafe = pd.DataFrame()
                lideres_cadastradas_orhafe = pd.DataFrame()
                coordenadoras_cadastradas_orhafe = pd.DataFrame()

            if reunioes_orhafe.empty:
                st.info("Sem chamadas do CÃ­rculo de OraÃ§Ã£o no perÃ­odo selecionado.")
            else:
                tipo_grafico_orhafe = st.selectbox(
                    "Filtrar grÃƒÂ¡ficos por",
                    ["Todas", "LÃƒÂ­deres", "Coordenadoras"],
                    key=_sk("orhafe_tipo_grafico", slug),
                )
                nomes_permitidos = None
                if tipo_grafico_orhafe == "LÃƒÂ­deres":
                    nomes_permitidos = set(
                        _texto(lideres_cadastradas_orhafe.get("nome", pd.Series(dtype=str)))
                        .str.strip()
                        .replace("", pd.NA)
                        .dropna()
                        .tolist()
                    )
                elif tipo_grafico_orhafe == "Coordenadoras":
                    nomes_permitidos = set(
                        _texto(coordenadoras_cadastradas_orhafe.get("nome", pd.Series(dtype=str)))
                        .str.strip()
                        .replace("", pd.NA)
                        .dropna()
                        .tolist()
                    )

                if nomes_permitidos is not None:
                    reunioes_orhafe = reunioes_orhafe[
                        _texto(reunioes_orhafe["lider"]).replace("", "Sem lider").isin(nomes_permitidos)
                    ].copy()
                    if not visitantes_orhafe.empty and "lider" in visitantes_orhafe.columns:
                        visitantes_orhafe = visitantes_orhafe[
                            _texto(visitantes_orhafe["lider"]).replace("", "Sem lider").isin(nomes_permitidos)
                        ].copy()

                if reunioes_orhafe.empty:
                    st.info("Nenhuma chamada encontrada para o filtro selecionado.")

                lideres_orhafe = sorted(
                    _texto(reunioes_orhafe["lider"]).replace("", "Sem lider").unique().tolist()
                ) or ["Sem dados"]
                lider_escolhida = st.selectbox(
                    "LÃ­der para resumo",
                    lideres_orhafe,
                    key=_sk("orhafe_lider", slug),
                )
                reunioes_lider = reunioes_orhafe[
                    _texto(reunioes_orhafe["lider"]).replace("", "Sem lider") == lider_escolhida
                ].copy()
                c_orhafe1, c_orhafe2 = st.columns([1, 1])
                with c_orhafe1:
                    st.plotly_chart(
                        _grafico_orhafe_resumo(
                            f"Resumo da lÃ­der {lider_escolhida}",
                            _orhafe_indicadores_resumo(
                                reunioes_lider,
                                visitantes=visitantes_orhafe,
                                lider=lider_escolhida,
                            ),
                        ),
                        use_container_width=True,
                        config=CONFIG_PLOTLY,
                    )
                with c_orhafe2:
                    resumo_lideres_orhafe = _orhafe_resumo_lideres(
                        reunioes_orhafe,
                        visitantes_orhafe,
                    )
                    st.plotly_chart(
                        _grafico_orhafe_por_lider(resumo_lideres_orhafe),
                        use_container_width=True,
                        config=CONFIG_PLOTLY,
                    )
                if not resumo_lideres_orhafe.empty:
                    with st.expander("Tabela por lÃ­der", expanded=False):
                        tabela_lideres = resumo_lideres_orhafe[[
                            "lider",
                            "reunioes",
                            "presenca_media_pct",
                            "ausencia_media_pct",
                            "visitantes",
                            "ofertas",
                        ]].copy()
                        tabela_lideres["presenca_media_pct"] = tabela_lideres["presenca_media_pct"].apply(
                            lambda valor: f"{valor:.1f}%"
                        )
                        tabela_lideres["ausencia_media_pct"] = tabela_lideres["ausencia_media_pct"].apply(
                            lambda valor: f"{valor:.1f}%"
                        )
                        tabela_lideres["ofertas"] = tabela_lideres["ofertas"].apply(formatar_moeda)
                        tabela_lideres = tabela_lideres.rename(columns={
                            "lider": "LÃ­der",
                            "reunioes": "ReuniÃµes",
                            "presenca_media_pct": "PresenÃ§a mÃ©dia",
                            "ausencia_media_pct": "AusÃªncia mÃ©dia",
                            "visitantes": "Visitantes",
                            "ofertas": "Ofertas",
                        })
                        st.dataframe(tabela_lideres, use_container_width=True, hide_index=True)
                        st.download_button(
                            "Baixar tabela por lÃ­der CSV",
                            data=gerar_csv(tabela_lideres),
                            file_name="dashboard_orhafe_lideres.csv",
                            mime="text/csv",
                            use_container_width=True,
                            key=_sk("baixar_orhafe_lideres", slug),
                        )

            _secao_dashboard(
                "Evolucao dos dizimos",
                "Total arrecadado mes a mes no periodo analisado, com linha de tendencia.",
            )
            serie_dizimos = _serie_mensal(
                dizimos_periodo,
                mes_fim_pastoral,
                quantidade=qtd_meses_pastoral,
            )
            valores_dizimos = serie_dizimos["entradas"].tolist()
            if not any(valor > 0 for valor in valores_dizimos):
                st.info("Ainda nao ha dizimos registrados para exibir a evolucao mensal.")
            else:
                fig_dizimos = go.Figure(go.Bar(
                    name="Dizimos",
                    x=serie_dizimos["rotulo"],
                    y=valores_dizimos,
                    marker_color=CORES["dizimo"],
                    text=[formatar_moeda(v) if v else "" for v in valores_dizimos],
                    textposition="outside",
                    textfont=dict(size=10, color="#CBD5E1"),
                    showlegend=True,
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
                    altura=430,
                    margem=dict(t=25, b=105, l=20, r=20),
                    showlegend=True,
                    xaxis=dict(fixedrange=True, gridcolor="#334155"),
                    yaxis=dict(fixedrange=True, gridcolor="#334155", tickformat=",.0f"),
                    legend=dict(
                        orientation="h",
                        y=-.22,
                        yanchor="top",
                        x=.5,
                        xanchor="center",
                        font=dict(size=11, color="#E2E8F0"),
                    ),
                ))
                st.plotly_chart(fig_dizimos, use_container_width=True, config=CONFIG_PLOTLY)

            _secao_dashboard(
                "Dizimos por membro - top 8",
                "Membros com os maiores valores registrados no periodo analisado.",
            )
            dizimos_membros = dizimos_periodo[dizimos_periodo["id_cadastro"].notna()].merge(
                membros[["id_cadastro", "nome"]],
                on="id_cadastro",
                how="inner",
            )
            ranking_membros = (
                dizimos_membros.groupby("nome", as_index=False)["valor"].sum()
                .sort_values("valor", ascending=False)
                .head(8)
                .sort_values("valor")
            )
            if ranking_membros.empty:
                st.info("Sem dizimos vinculados a membros no periodo.")
            else:
                fig_ranking = go.Figure(go.Bar(
                    x=ranking_membros["valor"],
                    y=ranking_membros["nome"],
                    orientation="h",
                    marker_color=CORES["dizimo"],
                    text=[formatar_moeda(valor) for valor in ranking_membros["valor"]],
                    textposition="outside",
                    textfont=dict(size=10, color="#CBD5E1"),
                ))
                fig_ranking.update_layout(**_layout_grafico(
                    altura=max(280, len(ranking_membros) * 40 + 80),
                    xaxis=dict(fixedrange=True, showgrid=False, showticklabels=False),
                    yaxis=dict(fixedrange=True, showgrid=False),
                ))
                st.plotly_chart(fig_ranking, use_container_width=True, config=CONFIG_PLOTLY)

            _secao_dashboard(
                "Entradas de membros por funcao",
                "Valores recebidos agrupados pela funcao cadastrada dos membros.",
            )
            entradas_membros = df_pastoral[
                (df_pastoral["tipo_norm"] == "ENTRADA")
                & (df_pastoral["tipo_cadastro"].str.upper() == "MEMBRO")
                & df_pastoral["id_cadastro"].notna()
            ].merge(
                membros[["id_cadastro", "funcao"]],
                on="id_cadastro",
                how="inner",
            )
            entradas_membros["funcao"] = _texto(entradas_membros["funcao"]).replace("", "Sem funcao")
            resumo_funcoes = (
                entradas_membros.groupby("funcao", as_index=False)["valor"].sum()
                .sort_values("valor", ascending=False)
            )
            if resumo_funcoes.empty:
                st.info("Sem entradas vinculadas a membros no periodo.")
            else:
                fig_funcoes = go.Figure(go.Bar(
                    x=resumo_funcoes["funcao"],
                    y=resumo_funcoes["valor"],
                    marker_color=CORES["funcao"],
                    text=[formatar_moeda(valor) for valor in resumo_funcoes["valor"]],
                    textposition="outside",
                    textfont=dict(size=10, color="#CBD5E1"),
                ))
                fig_funcoes.update_layout(**_layout_grafico(
                    altura=320,
                    xaxis=dict(fixedrange=True, showgrid=False),
                    yaxis=dict(fixedrange=True, showgrid=False, showticklabels=False),
                ))
                st.plotly_chart(fig_funcoes, use_container_width=True, config=CONFIG_PLOTLY)

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
                "Membros ativos que registraram ao menos uma contribuicao no periodo analisado.",
            )
            qtd_periodo, total_membros, percentual_periodo = _participacao_dizimistas(df_pastoral, membros)
            nao_dizimistas = max(total_membros - qtd_periodo, 0)
            if total_membros:
                fig_participacao = go.Figure(go.Pie(
                    name="Participacao",
                    labels=["Dizimistas", "Sem contribuicao no periodo"],
                    values=[qtd_periodo, nao_dizimistas],
                    hole=.7,
                    textinfo="none",
                    marker=dict(colors=[CORES["entrada"], "#374151"], line=dict(color="#1E293B", width=2)),
                ))
                fig_participacao.add_annotation(
                    text=f"<b>{percentual_periodo:.1f}%</b><br><span style='font-size:12px'>dizimistas</span>",
                    x=.5,
                    y=.5,
                    showarrow=False,
                    font=dict(size=25, color="#F1F5F9"),
                )
                fig_participacao.update_layout(**_layout_grafico(
                    altura=390,
                    margem=dict(t=25, b=110, l=35, r=35),
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        y=-.22,
                        yanchor="top",
                        x=.5,
                        xanchor="center",
                        font=dict(size=11, color="#E2E8F0"),
                    ),
                ))
                st.plotly_chart(fig_participacao, use_container_width=True, config=CONFIG_PLOTLY)
                p1, p2, p3 = st.columns(3)
                p1.metric("Membros ativos", total_membros)
                p2.metric("Dizimistas no periodo", qtd_periodo)
                p3.metric("Sem contribuicao no periodo", nao_dizimistas)
            else:
                st.info("Nao ha membros ativos cadastrados.")

            _secao_dashboard(
                "Frequencia de contribuicoes",
                "Quantidade de registros por membro no periodo analisado. O grafico exibe somente quem contribuiu.",
            )
            frequencia = _frequencia_membros(membros, dizimos_periodo)
            if frequencia.empty:
                st.info("Nao ha membros ativos para exibir.")
            else:
                grafico_freq = frequencia[frequencia["Contribuicoes"] > 0].sort_values(
                    ["Contribuicoes", "Nome"],
                    ascending=[True, False],
                )
                if grafico_freq.empty:
                    st.info("Nenhum membro registrou contribuicao no periodo analisado.")
                else:
                    fig_freq = go.Figure(go.Bar(
                        x=grafico_freq["Contribuicoes"],
                        y=grafico_freq["Nome"],
                        orientation="h",
                        marker_color=CORES["entrada"],
                        text=[str(quantidade) for quantidade in grafico_freq["Contribuicoes"]],
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
                    "frequencia_dizimos_periodo.csv",
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
                    dados = dizimos_periodo[dizimos_periodo["id_cadastro"] == id_membro].copy()
                    ultimos_dados = dados.sort_values("data", ascending=False)
                    ultima_data = (
                        ultimos_dados.iloc[0]["data"].strftime("%d/%m/%Y")
                        if not ultimos_dados.empty else "Sem registro"
                    )
                    meses_individual = _meses_periodo(inicio_pastoral, fim_pastoral)
                    resumo_individual = _resumo_individual_mensal(dados, meses_individual)
                    meses_com_dizimo = sum(
                        1 for mes in resumo_individual if mes["quantidade"] > 0
                    )
                    fidelidade = (
                        meses_com_dizimo / len(meses_individual) * 100
                        if meses_individual else 0.0
                    )
                    i1, i2, i3, i4 = st.columns(4)
                    i1.metric("Contribuicoes registradas", len(dados))
                    i2.metric("Valor total registrado", formatar_moeda(dados["valor"].sum()))
                    i3.metric("Ultima contribuicao", ultima_data)
                    i4.metric("Fidelidade mensal", f"{fidelidade:.1f}%")
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
                    st.caption("Presenca mensal das contribuicoes no periodo analisado")
                    _cartoes_fidelidade(resumo_individual)
                    _mensagem_fidelidade(selecionado.split(" | ", 1)[-1], resumo_individual)

    st.divider()
    st.download_button(
        "Exportar dados do mes",
        gerar_csv(ref),
        f"dashboard_{mes_ref}.csv",
        "text/csv",
        key=_sk("csv_mes", slug),
    )
