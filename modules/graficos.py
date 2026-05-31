import datetime
<<<<<<< HEAD
import html

=======
>>>>>>> 260a16ed078d5ed38360fa871afe8ae8dac6cacc
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.repository import (
<<<<<<< HEAD
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
    meses = [fim_mes - i for i in reversed(range(quantidade))]
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

    faixas = {"Nunca contribuiu": [], f"Mais de {dias_ativo} dias": [], "Mais de 60 dias": [], "Mais de 90 dias": []}
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
            if dias > 90:
                faixa = "Mais de 90 dias"
            elif dias > 60:
                faixa = "Mais de 60 dias"
            elif dias > dias_ativo:
                faixa = f"Mais de {dias_ativo} dias"
            else:
                continue
        faixas[faixa].append({
            "ID": id_cadastro,
            "Nome": membro["nome"],
            "Telefone": membro.get("telefone", ""),
            "Ultima contribuicao": ultima_txt or "Sem registro",
            "Dias sem contribuicao": dias if dias is not None else "Sem registro",
        })
    return faixas


def _injetar_css():
    st.markdown("""
    <style>
    .stApp { background-color:#0F172A; }
    h1,h2,h3,h4 { color:#F1F5F9 !important; }
    .dash-card { background:#1E293B;border:1px solid #334155;border-radius:12px;padding:16px;height:100%; }
    .dash-label { color:#94A3B8;font-size:.78rem;text-transform:uppercase;letter-spacing:.04em; }
    .dash-value { color:#F8FAFC;font-size:1.45rem;font-weight:700;margin-top:5px; }
    .dash-note { color:#CBD5E1;font-size:.76rem;margin-top:5px; }
=======
    carregar_lancamentos,
    carregar_cadastros,
    obter_config_igreja,
    DIAS_DIZIMISTA_ATIVO_DEFAULT,
)
from utils.helpers import formatar_moeda, gerar_csv, slug_da_sessao

T = "plotly_dark"

COR = {
    "Entrada": "#10B981",
    "Saida": "#EF4444",
    "saldo": "#3B82F6",
    "dizimo": "#10B981",
    "missao": "#F59E0B",
    "campanha": "#8B5CF6",
    "oferta": "#EC4899",
    "despesa": "#EF4444",
    "qtd_dizimo": "#10B981",
    "funcao": "#3B82F6",
    "Revista EBD": "#11cfc8",
    "sem_contribuicao": "#374151",
}

CORES_CATEGORIA = {
    "DIZIMO": "#10B981",
    "OFERTA": "#3B82F6",
    "MISSAO": "#F59E0B",
    "CAMPANHA": "#8B5CF6",
    "REVISTA EBD": "#11cfc8",
}

CORES_DESPESAS = [
    "#EF4444", "#F59E0B", "#10B981", "#3B82F6",
    "#8B5CF6", "#EC4899", "#6366F1", "#14B8A6", "#94A3B8",
]

ALT_COMPARACAO = 380
ALT_RANK_BASE = 320
ALT_POR_ITEM = 35
ALT_BARRAS_VERT = 400
MES_MINIMO_SISTEMA = pd.Period("2026-01", freq="M")

CONFIG_PLOTLY = {
    "displayModeBar": False,
    "staticPlot": True,
    "responsive": True,
}


def _altura_ranking(qtd_itens):
    return max(ALT_RANK_BASE, qtd_itens * ALT_POR_ITEM + 80)


def _base_layout(margin=None, **kw):
    return dict(
        template=T,
        margin=margin if margin is not None else dict(t=20, b=20, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E5E7EB"),
        hovermode=False,
        dragmode=False,
        **kw,
    )


def _normalizar_texto(df, colunas):
    for col in colunas:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    return df


def _validar_colunas(df, colunas, nome_df):
    faltando = [c for c in colunas if c not in df.columns]
    if faltando:
        st.error(
            f"Dados incompletos em {nome_df}. Colunas ausentes: "
            + ", ".join(faltando)
        )
        return False
    return True


def _injetar_css_dashboard():
    st.markdown("""
    <style>
    .stApp { background-color: #0F172A; }

    .kpi-card-v2 {
        background: #1E293B;
        border-radius: 14px;
        padding: 18px 16px;
        border: 1px solid #334155;
        height: 100%;
        position: relative;
        overflow: hidden;
    }
    .kpi-card-v2 .kpi-icon {
        position: absolute;
        top: 14px;
        right: 14px;
        width: 38px;
        height: 38px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.1rem;
    }
    .kpi-card-v2 .kpi-titulo {
        font-size: 0.78rem;
        color: #94A3B8;
        margin-bottom: 6px;
        font-weight: 500;
    }
    .kpi-card-v2 .kpi-valor {
        font-size: 1.45rem;
        font-weight: 700;
        color: #F1F5F9;
        line-height: 1.1;
        margin-bottom: 6px;
    }
    .kpi-card-v2 .kpi-variacao {
        font-size: 0.75rem;
        font-weight: 600;
    }
    .kpi-card-v2 .kpi-variacao.up { color: #10B981; }
    .kpi-card-v2 .kpi-variacao.down { color: #EF4444; }
    .kpi-card-v2 .kpi-variacao.flat { color: #94A3B8; }

    .grafico-titulo {
        font-size: 1.0rem;
        font-weight: 700;
        color: #F1F5F9;
        margin: 24px 0 10px 0;
        padding-bottom: 8px;
        border-bottom: 1px solid #334155;
    }
    .grafico-titulo .subtitulo {
        font-size: 0.78rem;
        font-weight: 400;
        color: #94A3B8;
        display: block;
        margin-top: 2px;
    }

    .stPlotlyChart {
        background: #1E293B;
        border-radius: 14px;
        padding: 16px 12px;
        border: 1px solid #334155;
        margin-bottom: 12px;
    }

    .filtro-mes-box {
        background: #1E293B;
        border-radius: 10px;
        padding: 8px 14px;
        border: 1px solid #334155;
        margin-bottom: 14px;
    }

    h1, h2, h3, h4 { color: #F1F5F9 !important; }
    .stMarkdown p, .stCaption { color: #CBD5E1; }
    [data-testid="stMetricValue"] { color: #F1F5F9 !important; }
    [data-testid="stMetricLabel"] { color: #94A3B8 !important; }
    .stSelectbox label, .stDateInput label { color: #CBD5E1 !important; }

    .inativo-card {
        background: #1E293B;
        border-radius: 12px;
        padding: 16px 18px;
        border: 1px solid #334155;
        text-align: center;
        height: 100%;
    }
    .inativo-card .titulo {
        font-size: 0.85rem;
        color: #94A3B8;
        margin-bottom: 8px;
    }
    .inativo-card .valor {
        font-size: 2.1rem;
        font-weight: 700;
        line-height: 1.1;
    }
    .inativo-card .pct {
        font-size: 0.85rem;
        margin-top: 4px;
        color: #94A3B8;
    }
    .inativo-card.amarelo .valor { color: #F59E0B; }
    .inativo-card.laranja .valor { color: #EF4444; }
    .inativo-card.vermelho .valor { color: #DC2626; }
>>>>>>> 260a16ed078d5ed38360fa871afe8ae8dac6cacc
    </style>
    """, unsafe_allow_html=True)


<<<<<<< HEAD
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
=======
def _meses_disponiveis(df):
    if df.empty or "data" not in df.columns:
        return []
    return sorted(df["data"].dropna().dt.to_period("M").unique(), reverse=True)


def _mes_anterior(periodo_mes):
    return periodo_mes - 1


def _calc_variacao(atual, anterior):
    if anterior == 0:
        if atual == 0:
            return ("Sem dados anteriores", "flat")
        return ("Novo", "up")

    pct = ((atual - anterior) / abs(anterior)) * 100
    if abs(pct) < 0.1:
        return ("0,0% vs anterior", "flat")

    direcao = "up" if pct > 0 else "down"
    seta = "↑" if pct > 0 else "↓"
    return (f"{seta} {abs(pct):.1f}% vs anterior", direcao)


def _kpi_card(titulo, valor, variacao, direcao, cor_icone, icone):
    st.markdown(f"""
    <div class="kpi-card-v2">
        <div class="kpi-icon" style="background:{cor_icone}33;color:{cor_icone}">
            {icone}
        </div>
        <div class="kpi-titulo">{titulo}</div>
        <div class="kpi-valor">{valor}</div>
        <div class="kpi-variacao {direcao}">{variacao}</div>
    </div>
    """, unsafe_allow_html=True)


def _calc_periodo_serie(df, mes_ref):
    if df.empty or df["mes_periodo"].dropna().empty:
        primeiro_mes_dados = mes_ref
    else:
        primeiro_mes_dados = df["mes_periodo"].dropna().min()

    ini_serie = max(primeiro_mes_dados, MES_MINIMO_SISTEMA)
    ini_12m = max(ini_serie, mes_ref - 11)
    fim_12m = mes_ref

    if fim_12m < ini_12m:
        ini_12m = fim_12m

    qtd_meses = max(1, (fim_12m - ini_12m).n + 1)
    meses_seq = [(ini_12m + i) for i in range(qtd_meses)]
    labels_12m = [m.strftime("%b/%y") for m in meses_seq]

    titulo_periodo = (
        f"{ini_12m.strftime('%b/%y')} a {fim_12m.strftime('%b/%y')}"
        if qtd_meses > 1
        else fim_12m.strftime("%b/%y")
    )

    return ini_12m, fim_12m, meses_seq, labels_12m, titulo_periodo


def _calcular_inativos_financeiros(df_membros_ativos, df_dizimos, hoje, dias_ativo):
    total_membros = len(df_membros_ativos)

    ultimo_diz = {}
    if not df_dizimos.empty:
        ultimo_diz = df_dizimos.groupby("id_cadastro")["data"].max().to_dict()

    resultado = {}
    faixas = sorted(set([int(dias_ativo), 30, 60, 90]))

    for faixa_dias in faixas:
        lista = []

        for _, m in df_membros_ativos.iterrows():
            id_m = int(m["id_cadastro"]) if pd.notna(m["id_cadastro"]) else None
            if id_m is None:
                continue

            if id_m in ultimo_diz and pd.notna(ultimo_diz[id_m]):
                ultimo_data = pd.Timestamp(ultimo_diz[id_m]).date()
                dias_sem = (hoje - ultimo_data).days
                ultimo_str = ultimo_data.strftime("%d/%m/%Y")
            else:
                dias_sem = 9999
                ultimo_str = "Nunca"

            if dias_sem >= faixa_dias:
                tel = str(m.get("telefone", "") or "").strip()
                tel_fmt = ""

                if tel and tel.isdigit():
                    if len(tel) == 11:
                        tel_fmt = f"({tel[:2]}) {tel[2:7]}-{tel[7:]}"
                    elif len(tel) == 10:
                        tel_fmt = f"({tel[:2]}) {tel[2:6]}-{tel[6:]}"
                    else:
                        tel_fmt = tel
                elif tel:
                    tel_fmt = tel

                lista.append({
                    "nome": str(m.get("nome", "")),
                    "telefone": tel_fmt or "—",
                    "ultimo": ultimo_str,
                    "dias": dias_sem if dias_sem < 9999 else None,
                })

        lista.sort(
            key=lambda x: x["dias"] if x["dias"] is not None else 99999,
            reverse=True,
        )

        resultado[str(faixa_dias)] = {
            "qtd": len(lista),
            "pct": (len(lista) / total_membros * 100) if total_membros else 0,
            "lista": lista,
        }

    return resultado


def render():
    _injetar_css_dashboard()

    slug = slug_da_sessao()
    df_lanc = carregar_lancamentos(slug)
    df_cad = carregar_cadastros(slug)

>>>>>>> 260a16ed078d5ed38360fa871afe8ae8dac6cacc
    if df_lanc.empty:
        st.info("Ainda nao ha lancamentos para o dashboard.")
        return

<<<<<<< HEAD
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
        serie = _serie_mensal(df, mes_ref)
        fig = go.Figure([
            go.Bar(name="Entradas", x=serie["rotulo"], y=serie["entradas"], marker_color=CORES["entrada"]),
            go.Bar(name="Saidas", x=serie["rotulo"], y=serie["saidas"], marker_color=CORES["saida"]),
            go.Scatter(name="Saldo", x=serie["rotulo"], y=serie["saldo"], line=dict(color=CORES["saldo"], width=3)),
        ])
        fig.update_layout(barmode="group", template="plotly_dark", height=420, margin=dict(t=20, b=30, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)

    with tab_despesas:
        saidas = ref[ref["tipo_norm"] == "SAIDA"].copy()
        saidas["subcategoria"] = _texto(saidas["subcategoria"]).replace("", "Sem subcategoria")
        resumo = saidas.groupby("subcategoria", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
        st.dataframe(resumo.rename(columns={"subcategoria": "Subcategoria", "valor": "Valor"}), use_container_width=True, hide_index=True)

    with tab_receitas:
        entradas = ref[ref["tipo_norm"] == "ENTRADA"]
        resumo = entradas.groupby("categoria", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
        st.dataframe(resumo.rename(columns={"categoria": "Categoria", "valor": "Valor"}), use_container_width=True, hide_index=True)

    with tab_qualidade:
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Datas invalidas", qualidade["datas_invalidas"])
        q2.metric("Valores invalidos", qualidade["valores_invalidos"])
        q3.metric("Sem vinculo", qualidade["sem_vinculo"])
        q4.metric("Despesas sem subcategoria", qualidade["despesas_sem_subcategoria"])
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
            faixas = _faixas_acompanhamento(membros, dizimos, datetime.date.today(), dias_ativo)
            st.caption("As faixas sao exclusivas. A interpretacao e a eventual abordagem dependem de avaliacao humana.")
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

            opcoes = {
                f"{int(row['id_cadastro'])} | {row['nome']}": int(row["id_cadastro"])
                for _, row in membros.sort_values("nome").iterrows()
            }
            if opcoes:
                selecionado = st.selectbox("Consultar membro", ["Selecione"] + list(opcoes), key=_sk("membro", slug))
                if selecionado != "Selecione":
                    id_membro = opcoes[selecionado]
                    dados = dizimos[dizimos["id_cadastro"] == id_membro].copy()
                    st.metric("Contribuicoes registradas", len(dados))
                    st.metric("Valor total registrado", formatar_moeda(dados["valor"].sum()))
                    if dados.empty:
                        st.info("Nao ha contribuicoes registradas no periodo analisado.")
                    else:
                        detalhe = dados[["data", "valor", "forma_pagamento", "descricao"]].copy()
                        detalhe["data"] = detalhe["data"].dt.strftime("%d/%m/%Y")
                        st.dataframe(detalhe, use_container_width=True, hide_index=True)

    st.divider()
    st.download_button(
        "Exportar dados do mes",
        gerar_csv(ref),
        f"dashboard_{mes_ref}.csv",
        "text/csv",
        key=_sk("csv_mes", slug),
    )
=======
    colunas_lanc = [
        "data", "valor", "id_cadastro", "tipo", "categoria",
        "tipo_cadastro", "nome_cadastro",
    ]
    colunas_cad = ["id_cadastro", "tipo_cadastro", "situacao", "nome"]

    if not _validar_colunas(df_lanc, colunas_lanc, "lancamentos"):
        return
    if not _validar_colunas(df_cad, colunas_cad, "cadastros"):
        return

    df = df_lanc.copy()
    df_cad = df_cad.copy()

    df = _normalizar_texto(df, [
        "tipo", "categoria", "tipo_cadastro", "nome_cadastro",
        "subcategoria", "descricao", "forma_pagamento",
    ])
    df_cad = _normalizar_texto(df_cad, [
        "tipo_cadastro", "situacao", "nome", "telefone", "funcao",
    ])

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df["id_cadastro"] = pd.to_numeric(df["id_cadastro"], errors="coerce")
    df_cad["id_cadastro"] = pd.to_numeric(df_cad["id_cadastro"], errors="coerce")

    df["mes_periodo"] = df["data"].dt.to_period("M")
    df["mes_label"] = df["data"].dt.strftime("%b/%Y")

    try:
        dias_ativo = int(obter_config_igreja(
            slug, "dias_dizimista_ativo", str(DIAS_DIZIMISTA_ATIVO_DEFAULT)
        ))
    except (ValueError, TypeError):
        dias_ativo = DIAS_DIZIMISTA_ATIVO_DEFAULT

    st.markdown("### 📊 Dashboard")
    st.caption("Visao geral da saude financeira da igreja")

    meses = _meses_disponiveis(df)
    if not meses:
        st.warning("Sem dados de data para os lancamentos.")
        return

    if "db_mes_ref" not in st.session_state:
        st.session_state["db_mes_ref"] = str(meses[0])

    meses_str = [str(m) for m in meses]
    meses_lbl = [m.strftime("%b/%Y") for m in meses]
    map_lbl = dict(zip(meses_str, meses_lbl))

    col_ref, col_comp, col_modo = st.columns([2, 2, 1])

    with col_ref:
        mes_ref_str = st.selectbox(
            "📅 Mes de referencia",
            meses_str,
            format_func=lambda x: map_lbl.get(x, x),
            index=meses_str.index(st.session_state["db_mes_ref"])
            if st.session_state["db_mes_ref"] in meses_str else 0,
            key="db_mes_ref_select",
        )
        st.session_state["db_mes_ref"] = mes_ref_str

    mes_ref = pd.Period(mes_ref_str, freq="M")
    mes_anterior_padrao = _mes_anterior(mes_ref)

    meses_comp_str = [str(m) for m in meses if m < mes_ref] or [str(mes_anterior_padrao)]
    map_comp = {str(m): m.strftime("%b/%Y") for m in meses if m < mes_ref}

    if not map_comp:
        map_comp[str(mes_anterior_padrao)] = mes_anterior_padrao.strftime("%b/%Y")

    with col_comp:
        idx_default = 0
        if str(mes_anterior_padrao) in meses_comp_str:
            idx_default = meses_comp_str.index(str(mes_anterior_padrao))

        mes_comp_str = st.selectbox(
            "🔄 Comparar com",
            meses_comp_str,
            format_func=lambda x: map_comp.get(x, x),
            index=idx_default,
            key="db_mes_comp_select",
        )

    mes_comp = pd.Period(mes_comp_str, freq="M")

    with col_modo:
        st.markdown('<div style="margin-top:28px"></div>', unsafe_allow_html=True)
        modo_personalizado = st.toggle(
            "Personalizado",
            value=False,
            key="db_modo_personalizado",
            help="Ativa filtros avancados",
        )

    df_ref = df[df["mes_periodo"] == mes_ref].copy()
    df_comp = df[df["mes_periodo"] == mes_comp].copy()

    membro_sel = "Todos"
    funcao_sel = "Todas"
    categoria_sel = "Todas"
    d_ini = None
    d_fim = None

    if modo_personalizado:
        st.markdown(
            '<div class="filtro-mes-box">'
            '<b style="color:#F1F5F9">🔍 Modo Personalizado</b> '
            '<span style="color:#94A3B8">— cards e graficos respeitam os filtros abaixo. '
            'A comparacao usa o periodo equivalente anterior.</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        dv = df["data"].dropna()
        cp1, cp2 = st.columns(2)

        with cp1:
            d_ini = st.date_input(
                "De",
                value=dv.min().date() if not dv.empty else datetime.date.today(),
                format="DD/MM/YYYY",
                key="db_ini",
            )

        with cp2:
            d_fim = st.date_input(
                "Ate",
                value=dv.max().date() if not dv.empty else datetime.date.today(),
                format="DD/MM/YYYY",
                key="db_fim",
            )

        if d_ini > d_fim:
            st.error("Data inicial maior que data final.")
            return

        df_f = df[
            (df["data"] >= pd.Timestamp(d_ini)) &
            (df["data"] <= pd.Timestamp(d_fim))
        ].copy()

        fc1, fc2, fc3 = st.columns(3)

        membros_disp = sorted([
            n for n in df_f["nome_cadastro"].dropna().unique()
            if str(n).strip() and str(n).strip() != "nan"
        ])
        funcoes_disp = sorted([
            f for f in df_cad["funcao"].dropna().unique()
            if str(f).strip()
        ])
        categorias_disp = sorted([
            c for c in df_f[df_f["tipo"].str.upper() == "ENTRADA"]["categoria"].dropna().unique()
            if str(c).strip()
        ])

        with fc1:
            membro_sel = st.selectbox(
                "Membro / Fornecedor",
                ["Todos"] + membros_disp,
                key="db_membro_filtro",
            )

        with fc2:
            funcao_sel = st.selectbox(
                "Funcao",
                ["Todas"] + funcoes_disp,
                key="db_funcao_filtro",
            )

        with fc3:
            categoria_sel = st.selectbox(
                "Categoria entrada",
                ["Todas"] + categorias_disp,
                key="db_categoria_filtro",
            )

        if membro_sel != "Todos":
            df_f = df_f[df_f["nome_cadastro"].str.strip() == membro_sel]

        if funcao_sel != "Todas":
            ids_funcao = df_cad[
                df_cad["funcao"].str.strip() == funcao_sel
            ]["id_cadastro"].tolist()
            df_f = df_f[df_f["id_cadastro"].isin(ids_funcao)]

        if categoria_sel != "Todas":
            df_f = df_f[df_f["categoria"].str.strip() == categoria_sel]
    else:
        df_f = df_ref

    if modo_personalizado:
        dias_periodo = (d_fim - d_ini).days + 1
        d_fim_comp_pers = d_ini - datetime.timedelta(days=1)
        d_ini_comp_pers = d_fim_comp_pers - datetime.timedelta(days=dias_periodo - 1)

        df_comp_pers = df[
            (df["data"] >= pd.Timestamp(d_ini_comp_pers)) &
            (df["data"] <= pd.Timestamp(d_fim_comp_pers))
        ].copy()

        if membro_sel != "Todos":
            df_comp_pers = df_comp_pers[df_comp_pers["nome_cadastro"].str.strip() == membro_sel]

        if funcao_sel != "Todas":
            ids_funcao = df_cad[
                df_cad["funcao"].str.strip() == funcao_sel
            ]["id_cadastro"].tolist()
            df_comp_pers = df_comp_pers[df_comp_pers["id_cadastro"].isin(ids_funcao)]

        if categoria_sel != "Todas":
            df_comp_pers = df_comp_pers[df_comp_pers["categoria"].str.strip() == categoria_sel]

        df_card_atual = df_f
        df_card_comp = df_comp_pers
        label_atual = f"{d_ini.strftime('%d/%m')} a {d_fim.strftime('%d/%m/%Y')}"

        filtros_resumo = []
        if membro_sel != "Todos":
            filtros_resumo.append(f"Membro: **{membro_sel}**")
        if funcao_sel != "Todas":
            filtros_resumo.append(f"Funcao: **{funcao_sel}**")
        if categoria_sel != "Todas":
            filtros_resumo.append(f"Categoria: **{categoria_sel}**")

        if filtros_resumo:
            st.info("🔍 Filtros ativos: " + " | ".join(filtros_resumo))

        st.caption(
            f"📊 Cards comparando **{label_atual}** com periodo equivalente anterior "
            f"({d_ini_comp_pers.strftime('%d/%m/%Y')} a {d_fim_comp_pers.strftime('%d/%m/%Y')})"
        )
    else:
        df_card_atual = df_ref
        df_card_comp = df_comp
        label_atual = mes_ref.strftime("%b/%Y")

    ent_ref = df_card_atual[df_card_atual["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    sai_ref = df_card_atual[df_card_atual["tipo"].str.upper() == "SAIDA"]["valor"].sum()
    sal_ref = ent_ref - sai_ref

    ent_comp = df_card_comp[df_card_comp["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    sai_comp = df_card_comp[df_card_comp["tipo"].str.upper() == "SAIDA"]["valor"].sum()
    sal_comp = ent_comp - sai_comp

    diz_ref = df_card_atual[
        (df_card_atual["categoria"].str.upper() == "DIZIMO") &
        (df_card_atual["tipo_cadastro"].str.upper() == "MEMBRO")
    ]
    diz_comp = df_card_comp[
        (df_card_comp["categoria"].str.upper() == "DIZIMO") &
        (df_card_comp["tipo_cadastro"].str.upper() == "MEMBRO")
    ]
    qtd_diz_ref = diz_ref["id_cadastro"].dropna().nunique()
    qtd_diz_comp = diz_comp["id_cadastro"].dropna().nunique()

    membros_ativos_n = len(df_cad[
        (df_cad["tipo_cadastro"].str.upper() == "MEMBRO") &
        (df_cad["situacao"].str.upper() == "ATIVO")
    ])
    taxa_ref = (qtd_diz_ref / membros_ativos_n * 100) if membros_ativos_n else 0
    taxa_comp = (qtd_diz_comp / membros_ativos_n * 100) if membros_ativos_n else 0

    miss_ref = df_card_atual[
        (df_card_atual["tipo"].str.upper() == "ENTRADA") &
        (df_card_atual["categoria"].str.upper() == "MISSAO")
    ]["valor"].sum()
    miss_comp = df_card_comp[
        (df_card_comp["tipo"].str.upper() == "ENTRADA") &
        (df_card_comp["categoria"].str.upper() == "MISSAO")
    ]["valor"].sum()

    ano_ref = mes_ref.year
    df_ano = df[df["data"].dt.year == ano_ref]
    df_ano_ant = df[df["data"].dt.year == ano_ref - 1]
    ent_ano = df_ano[df_ano["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    ent_ano_ant = df_ano_ant[df_ano_ant["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    cresc_pct = ((ent_ano - ent_ano_ant) / abs(ent_ano_ant) * 100) if ent_ano_ant else 0

    var_ent, dir_ent = _calc_variacao(ent_ref, ent_comp)
    var_sai, dir_sai = _calc_variacao(sai_ref, sai_comp)
    var_sal, dir_sal = _calc_variacao(sal_ref, sal_comp)
    var_diz, dir_diz = _calc_variacao(qtd_diz_ref, qtd_diz_comp)
    var_taxa, dir_taxa = _calc_variacao(taxa_ref, taxa_comp)
    var_miss, dir_miss = _calc_variacao(miss_ref, miss_comp)

    r1c1, r1c2, r1c3 = st.columns(3)
    r2c1, r2c2, r2c3 = st.columns(3)

    with r1c1:
        _kpi_card(f"Entradas {label_atual}", formatar_moeda(ent_ref), var_ent, dir_ent, "#10B981", "💰")
    with r1c2:
        _kpi_card(f"Despesas {label_atual}", formatar_moeda(sai_ref), var_sai, dir_sai, "#EF4444", "💸")
    with r1c3:
        _kpi_card(f"Saldo {label_atual}", formatar_moeda(sal_ref), var_sal, dir_sal, "#3B82F6", "📊")

    with r2c1:
        _kpi_card("Dizimistas no periodo", str(qtd_diz_ref), var_diz, dir_diz, "#8B5CF6", "🙏")
    with r2c2:
        _kpi_card("Taxa de fidelidade", f"{taxa_ref:.1f}%", var_taxa, dir_taxa, "#F59E0B", "📈")
    with r2c3:
        seta_cresc = "↑" if cresc_pct > 0 else ("↓" if cresc_pct < 0 else "—")
        dir_cresc = "up" if cresc_pct > 0 else ("down" if cresc_pct < 0 else "flat")
        _kpi_card(
            f"Crescimento {ano_ref}",
            f"{cresc_pct:+.1f}%" if ent_ano_ant else "Sem dados",
            f"{seta_cresc} vs {ano_ref - 1}" if ent_ano_ant else "Primeiro ano",
            dir_cresc,
            "#14B8A6",
            "📅",
        )

    st.markdown(
        f"""
        <div class="kpi-card-v2" style="border-left:4px solid #F59E0B">
            <div class="kpi-icon" style="background:#F59E0B33;color:#F59E0B">⛪</div>
            <div class="kpi-titulo">🌍 Investimentos no Reino — {label_atual}</div>
            <div class="kpi-valor" style="color:#F59E0B">{formatar_moeda(miss_ref)}</div>
            <div class="kpi-variacao {dir_miss}">{var_miss}</div>
            <div style="font-size:0.78rem;color:#94A3B8;margin-top:8px">
                Total arrecadado na categoria Missao
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    OPC = dict(use_container_width=True, config=CONFIG_PLOTLY)

    if df_f.empty:
        st.warning("Sem lancamentos no periodo selecionado.")
        return

    if modo_personalizado:
        meses_seq = sorted(df_f["mes_periodo"].dropna().unique())
        if not meses_seq:
            st.warning("Sem dados de meses no periodo filtrado.")
            return

        labels_12m = [m.strftime("%b/%y") for m in meses_seq]
        ini_12m = meses_seq[0]
        fim_12m = meses_seq[-1]
        titulo_periodo = (
            f"{ini_12m.strftime('%b/%y')} a {fim_12m.strftime('%b/%y')}"
            if len(meses_seq) > 1
            else fim_12m.strftime("%b/%y")
        )
        df_12m = df_f.copy()
    else:
        ini_12m, fim_12m, meses_seq, labels_12m, titulo_periodo = _calc_periodo_serie(df, mes_ref)
        df_12m = df[(df["mes_periodo"] >= ini_12m) & (df["mes_periodo"] <= fim_12m)].copy()

    st.markdown(
        f'<div class="grafico-titulo">📈 Fluxo de Caixa — {titulo_periodo}'
        f'<span class="subtitulo">Entradas, Despesas e Saldo mes a mes</span></div>',
        unsafe_allow_html=True,
    )

    def _serie_12m(t):
        out = []
        for m in meses_seq:
            sub = df_12m[
                (df_12m["mes_periodo"] == m) &
                (df_12m["tipo"].str.upper() == t.upper())
            ]
            out.append(float(sub["valor"].sum()))
        return out

    e12 = _serie_12m("Entrada")
    s12 = _serie_12m("Saida")
    sal12 = [e - s for e, s in zip(e12, s12)]

    fig_fc = go.Figure([
        go.Bar(
            name="Entradas",
            x=labels_12m,
            y=e12,
            marker_color=COR["Entrada"],
            text=[formatar_moeda(v) if v > 0 else "" for v in e12],
            textposition="outside",
            textfont=dict(size=10, color="#CBD5E1"),
            hoverinfo="skip",
        ),
        go.Bar(
            name="Despesas",
            x=labels_12m,
            y=s12,
            marker_color=COR["Saida"],
            text=[formatar_moeda(v) if v > 0 else "" for v in s12],
            textposition="outside",
            textfont=dict(size=10, color="#CBD5E1"),
            hoverinfo="skip",
        ),
        go.Bar(
            name="Saldo",
            x=labels_12m,
            y=sal12,
            marker_color=COR["saldo"],
            text=[formatar_moeda(v) if v != 0 else "" for v in sal12],
            textposition="outside",
            textfont=dict(size=10, color="#CBD5E1"),
            hoverinfo="skip",
        ),
    ])
    fig_fc.update_layout(**_base_layout(
        barmode="group",
        height=ALT_COMPARACAO,
        margin=dict(t=50, b=30, l=10, r=10),
        legend=dict(orientation="h", y=1.12, x=0, font=dict(color="#E5E7EB")),
        xaxis=dict(fixedrange=True, color="#94A3B8", gridcolor="#334155"),
        yaxis=dict(fixedrange=True, gridcolor="#334155", color="#94A3B8", tickformat=",.0f"),
        bargap=0.20,
        bargroupgap=0.05,
    ))
    st.plotly_chart(fig_fc, **OPC)

    g1, g2 = st.columns(2)

    with g1:
        st.markdown(
            f'<div class="grafico-titulo">🥧 Entradas por Categoria'
            f'<span class="subtitulo">{label_atual}</span></div>',
            unsafe_allow_html=True,
        )
        ent_cat = df_f[df_f["tipo"].str.upper() == "ENTRADA"].groupby(
            "categoria", as_index=False
        )["valor"].sum().sort_values("valor", ascending=False)

        if ent_cat.empty:
            st.info("Sem entradas no periodo.")
        else:
            cores_pizza = [
                CORES_CATEGORIA.get(str(c).upper(), "#94A3B8")
                for c in ent_cat["categoria"]
            ]
            fig_ec = go.Figure(go.Pie(
                labels=ent_cat["categoria"],
                values=ent_cat["valor"],
                hole=0.6,
                textinfo="percent",
                textfont=dict(color="white", size=12),
                marker=dict(colors=cores_pizza, line=dict(color="#1E293B", width=2)),
                hoverinfo="skip",
            ))
            total_ent = ent_cat["valor"].sum()
            fig_ec.add_annotation(
                text=f"<b>Total</b><br>{formatar_moeda(total_ent)}",
                x=0.5,
                y=0.5,
                font=dict(size=13, color="#F1F5F9"),
                showarrow=False,
            )
            fig_ec.update_layout(**_base_layout(
                height=ALT_COMPARACAO,
                showlegend=True,
                legend=dict(orientation="v", y=0.5, x=1.05, font=dict(color="#E5E7EB", size=11)),
                margin=dict(t=20, b=20, l=20, r=20),
            ))
            st.plotly_chart(fig_ec, **OPC)

    with g2:
        st.markdown(
            f'<div class="grafico-titulo">📉 Despesas por Subcategoria'
            f'<span class="subtitulo">{label_atual}</span></div>',
            unsafe_allow_html=True,
        )
        desp = df_f[df_f["tipo"].str.upper() == "SAIDA"].copy()
        if desp.empty:
            st.info("Sem despesas no periodo.")
        else:
            desp["subcategoria"] = desp["subcategoria"].fillna("").str.strip()
            desp["subcategoria"] = desp["subcategoria"].replace("", "Sem subcategoria")
            agrup = desp.groupby("subcategoria", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
            cores_d = CORES_DESPESAS[:len(agrup)] + ["#94A3B8"] * max(0, len(agrup) - len(CORES_DESPESAS))

            fig_dc = go.Figure(go.Pie(
                labels=agrup["subcategoria"],
                values=agrup["valor"],
                hole=0.6,
                textinfo="percent",
                textfont=dict(color="white", size=12),
                marker=dict(colors=cores_d, line=dict(color="#1E293B", width=2)),
                hoverinfo="skip",
            ))
            total_desp = agrup["valor"].sum()
            fig_dc.add_annotation(
                text=f"<b>Total</b><br>{formatar_moeda(total_desp)}",
                x=0.5,
                y=0.5,
                font=dict(size=13, color="#F1F5F9"),
                showarrow=False,
            )
            fig_dc.update_layout(**_base_layout(
                height=ALT_COMPARACAO,
                showlegend=True,
                legend=dict(orientation="v", y=0.5, x=1.05, font=dict(color="#E5E7EB", size=11)),
                margin=dict(t=20, b=20, l=20, r=20),
            ))
            st.plotly_chart(fig_dc, **OPC)

    st.markdown(
        f'<div class="grafico-titulo">💰 Evolucao dos Dizimos — {titulo_periodo}'
        f'<span class="subtitulo">Total arrecadado em dizimos mes a mes</span></div>',
        unsafe_allow_html=True,
    )

    d12 = []
    for m in meses_seq:
        sub = df_12m[
            (df_12m["mes_periodo"] == m) &
            (df_12m["categoria"].str.upper() == "DIZIMO")
        ]
        d12.append(float(sub["valor"].sum()))

    fig_d = go.Figure(go.Bar(
        x=labels_12m,
        y=d12,
        marker_color=COR["dizimo"],
        text=[formatar_moeda(v) if v > 0 else "" for v in d12],
        textposition="outside",
        textfont=dict(size=10, color="#CBD5E1"),
        hoverinfo="skip",
    ))

    if len([v for v in d12 if v > 0]) >= 3:
        ma = []
        for i in range(len(d12)):
            ini = max(0, i - 2)
            window = d12[ini:i + 1]
            ma.append(sum(window) / len(window) if window else 0)
        fig_d.add_trace(go.Scatter(
            x=labels_12m,
            y=ma,
            mode="lines",
            line=dict(color="#94A3B8", width=2, dash="dot"),
            name="Tendencia",
            hoverinfo="skip",
        ))

    fig_d.update_layout(**_base_layout(
        height=ALT_COMPARACAO,
        showlegend=False,
        margin=dict(t=30, b=30, l=10, r=10),
        xaxis=dict(fixedrange=True, color="#94A3B8", gridcolor="#334155"),
        yaxis=dict(fixedrange=True, gridcolor="#334155", color="#94A3B8", tickformat=",.0f"),
    ))
    st.plotly_chart(fig_d, **OPC)

    st.markdown(
        f'<div class="grafico-titulo">⚠️ Membros Inativos Financeiramente'
        f'<span class="subtitulo">Configuracao da igreja: dizimista ativo = ate {dias_ativo} dias. '
        f'As faixas abaixo mostram quem esta abaixo desse criterio.</span></div>',
        unsafe_allow_html=True,
    )

    df_mem_ativos_full = df_cad[
        (df_cad["tipo_cadastro"].str.upper() == "MEMBRO") &
        (df_cad["situacao"].str.upper() == "ATIVO")
    ].copy()

    if modo_personalizado and funcao_sel != "Todas":
        df_mem_ativos_full = df_mem_ativos_full[
            df_mem_ativos_full["funcao"].str.strip() == funcao_sel
        ]

    if modo_personalizado and membro_sel != "Todos":
        df_mem_ativos_full = df_mem_ativos_full[
            df_mem_ativos_full["nome"].str.strip() == membro_sel
        ]

    df_dizimos_todos = df[
        (df["categoria"].str.upper() == "DIZIMO") &
        (df["tipo_cadastro"].str.upper() == "MEMBRO")
    ].copy()

    hoje_dt = datetime.date.today()
    inativos = _calcular_inativos_financeiros(
        df_mem_ativos_full, df_dizimos_todos, hoje_dt, dias_ativo
    )

    cores_inativos = {
        str(dias_ativo): ("amarelo", f"{dias_ativo} dias ou mais", "🟡"),
        "30": ("amarelo", "30 dias ou mais", "🟡"),
        "60": ("laranja", "60 dias ou mais", "🟠"),
        "90": ("vermelho", "90 dias ou mais", "🔴"),
    }
    cores_inativos = {
        faixa: dados
        for faixa, dados in cores_inativos.items()
        if faixa in inativos
    }

    colunas_inativos = st.columns(len(cores_inativos))

    for (faixa, (cor, titulo, icone)), col in zip(
        cores_inativos.items(), colunas_inativos
    ):
        dados = inativos[faixa]
        with col:
            st.markdown(
                f"""
                <div class="inativo-card {cor}">
                    <div class="titulo">{icone} {titulo}</div>
                    <div class="valor">{dados['qtd']}</div>
                    <div class="pct">{dados['pct']:.1f}% dos membros</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("")
    st.caption(
        f"📋 Total de membros ativos: **{len(df_mem_ativos_full)}**. "
        "Clique nas faixas abaixo para ver os nomes."
    )

    for faixa, (cor, titulo, icone) in cores_inativos.items():
        dados = inativos[faixa]
        if dados["qtd"] == 0:
            continue

        with st.expander(
            f"{icone} {titulo} — {dados['qtd']} membro(s)",
            expanded=False,
        ):
            df_lista = pd.DataFrame(dados["lista"])
            df_lista["dias"] = df_lista["dias"].apply(
                lambda x: f"{x} dias" if x is not None else "Nunca dizimou"
            )
            df_lista = df_lista.rename(columns={
                "nome": "Nome",
                "telefone": "Telefone",
                "ultimo": "Ultimo dizimo",
                "dias": "Dias sem dizimar",
            })
            st.dataframe(df_lista, use_container_width=True, hide_index=True)

            csv_inativos = df_lista.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                f"📥 Exportar lista de {titulo.lower()}",
                csv_inativos,
                f"inativos_{faixa}dias.csv",
                "text/csv",
                key=f"dl_inativos_{faixa}",
            )

    st.markdown(
        '<div class="grafico-titulo">🙏 Percentual de Dizimistas'
        '<span class="subtitulo">Membros ativos que contribuiram no periodo</span></div>',
        unsafe_allow_html=True,
    )

    df_membros_ativos = df_cad[
        (df_cad["tipo_cadastro"].str.upper() == "MEMBRO") &
        (df_cad["situacao"].str.upper() == "ATIVO")
    ].copy()

    if modo_personalizado and funcao_sel != "Todas":
        df_membros_ativos = df_membros_ativos[
            df_membros_ativos["funcao"].str.strip() == funcao_sel
        ]

    if modo_personalizado and membro_sel != "Todos":
        df_membros_ativos = df_membros_ativos[
            df_membros_ativos["nome"].str.strip() == membro_sel
        ]

    total_membros = len(df_membros_ativos)
    diz_periodo = df_f[
        (df_f["categoria"].str.upper() == "DIZIMO") &
        (df_f["tipo_cadastro"].str.upper() == "MEMBRO")
    ]

    ids_membros_ativos = set(df_membros_ativos["id_cadastro"].dropna().astype(int).tolist())
    ids_dizimistas = set(diz_periodo["id_cadastro"].dropna().astype(int).tolist())
    qtd_d = len(ids_dizimistas & ids_membros_ativos)
    qtd_nd = total_membros - qtd_d

    if total_membros == 0:
        st.info("Nenhum membro ativo encontrado para o filtro aplicado.")
    else:
        pct = (qtd_d / total_membros) * 100

        fig_pct = go.Figure(go.Pie(
            labels=["Dizimistas", "Nao dizimistas"],
            values=[qtd_d, qtd_nd],
            hole=0.7,
            textinfo="none",
            marker=dict(colors=[COR["Entrada"], "#374151"], line=dict(color="#1E293B", width=2)),
            hoverinfo="skip",
        ))
        fig_pct.add_annotation(
            text=f"<b>{pct:.1f}%</b>",
            x=0.5,
            y=0.55,
            font=dict(size=32, color=COR["Entrada"]),
            showarrow=False,
        )
        fig_pct.add_annotation(
            text="dizimistas",
            x=0.5,
            y=0.40,
            font=dict(size=12, color="#94A3B8"),
            showarrow=False,
        )
        fig_pct.update_layout(**_base_layout(
            height=ALT_COMPARACAO,
            showlegend=True,
            legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center", font=dict(color="#E5E7EB")),
            margin=dict(t=10, b=40, l=10, r=10),
        ))
        st.plotly_chart(fig_pct, **OPC)

        km1, km2, km3 = st.columns(3)
        km1.metric("Membros ativos", str(total_membros))
        km2.metric("Dizimistas", str(qtd_d), delta=f"{pct:.1f}%")
        km3.metric("Nao dizimistas", str(qtd_nd), delta=f"-{100 - pct:.1f}%", delta_color="inverse")

    # ── FREQUENCIA DE DIZIMOS — TODOS OS MEMBROS ATIVOS ───────────────────
    diz_f = df_f[
        (df_f["categoria"].str.upper() == "DIZIMO") &
        (df_f["tipo_cadastro"].str.upper() == "MEMBRO")
    ]

    # Lista TODOS os membros ativos da igreja (com filtros se modo personalizado)
    df_todos_membros = df_cad[
        (df_cad["tipo_cadastro"].str.upper() == "MEMBRO") &
        (df_cad["situacao"].str.upper() == "ATIVO")
    ].copy()

    if modo_personalizado and funcao_sel != "Todas":
        df_todos_membros = df_todos_membros[
            df_todos_membros["funcao"].str.strip() == funcao_sel
        ]
    if modo_personalizado and membro_sel != "Todos":
        df_todos_membros = df_todos_membros[
            df_todos_membros["nome"].str.strip() == membro_sel
        ]

    if not df_todos_membros.empty:
        st.markdown(
            f'<div class="grafico-titulo">🔢 Frequencia de Dizimos'
            f'<span class="subtitulo">Todos os membros ativos — qtd de lancamentos no periodo '
            f'({len(df_todos_membros)} membros)</span></div>',
            unsafe_allow_html=True,
        )

        # Conta dizimos por id_cadastro
        if not diz_f.empty:
            cont_dizimos = diz_f.groupby("id_cadastro").size().to_dict()
        else:
            cont_dizimos = {}

        # Monta lista com TODOS os membros ativos (mesmo os que tem 0)
        lista_freq = []
        for _, m in df_todos_membros.iterrows():
            id_m = int(m["id_cadastro"]) if pd.notna(m["id_cadastro"]) else None
            if id_m is None:
                continue
            qtd_membro = cont_dizimos.get(id_m, 0)
            lista_freq.append({
                "nome": str(m["nome"]),
                "quantidade": qtd_membro,
            })

        # Ordena: maior quantidade primeiro, depois alfabetico
        lista_freq.sort(key=lambda x: (-x["quantidade"], x["nome"]))

        # Inverte para o grafico horizontal (maior aparece no topo)
        lista_freq_grafico = list(reversed(lista_freq))

        nomes_g = [item["nome"] for item in lista_freq_grafico]
        qtds_g  = [item["quantidade"] for item in lista_freq_grafico]

        # Cores: verde se contribuiu, cinza se 0
        cores_g = [
            COR["qtd_dizimo"] if q > 0 else COR["sem_contribuicao"]
            for q in qtds_g
        ]

        # Texto da barra: numero, ou "Sem contribuicao" se 0
        textos_g = [
            str(q) if q > 0 else "Sem contribuicao"
            for q in qtds_g
        ]

        fig_qtd = go.Figure(go.Bar(
            x=qtds_g,
            y=nomes_g,
            orientation="h",
            marker_color=cores_g,
            text=textos_g,
            textposition="outside",
            textfont=dict(color="#CBD5E1", size=11),
            hoverinfo="skip",
        ))
        fig_qtd.update_layout(**_base_layout(
            height=_altura_ranking(len(lista_freq)),
            xaxis=dict(showticklabels=False, showgrid=False, fixedrange=True),
            yaxis=dict(showgrid=False, fixedrange=True, color="#CBD5E1"),
        ))
        st.plotly_chart(fig_qtd, **OPC)

        # 3 metricas resumo
        qtd_com_diz   = sum(1 for q in qtds_g if q > 0)
        qtd_sem_diz   = len(qtds_g) - qtd_com_diz
        total_lancs   = sum(qtds_g)

        km_f1, km_f2, km_f3 = st.columns(3)
        km_f1.metric("Membros que contribuiram", str(qtd_com_diz))
        km_f2.metric("Membros sem contribuicao", str(qtd_sem_diz))
        km_f3.metric("Total de lancamentos", str(total_lancs))

        # Exportacao da lista completa
        df_freq_exp = pd.DataFrame(lista_freq).rename(columns={
            "nome": "Nome",
            "quantidade": "Qtd dizimos no periodo",
        })
        csv_freq = df_freq_exp.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "📥 Exportar lista completa de frequencia",
            csv_freq,
            "frequencia_dizimos.csv",
            "text/csv",
            key="dl_freq_completa",
        )

        # ── FREQUENCIA INDIVIDUAL DO MEMBRO ───────────────────────────────
        st.markdown(
            '<div class="grafico-titulo">🔍 Frequencia Individual do Membro'
            '<span class="subtitulo">Selecione um membro (inclui quem nao contribuiu)</span></div>',
            unsafe_allow_html=True,
        )

        # Lista TODOS os membros ativos (em ordem alfabetica)
        membros_lista_select = sorted(df_todos_membros["nome"].dropna().unique().tolist())

        membro_sel_freq = st.selectbox(
            "Membro",
            ["— Selecione um membro —"] + membros_lista_select,
            key="freq_membro_sel",
            help="Lista todos os membros ativos da igreja, mesmo os que nao contribuiram.",
        )

        if membro_sel_freq != "— Selecione um membro —":
            diz_membro = diz_f[
                diz_f["nome_cadastro"].str.strip() == membro_sel_freq
            ].copy()

            qtd_total = len(diz_membro)
            valor_total = diz_membro["valor"].sum() if qtd_total else 0
            media_valor = valor_total / qtd_total if qtd_total else 0
            meses_unicos = diz_membro["mes_periodo"].nunique() if qtd_total else 0

            mf1, mf2, mf3, mf4 = st.columns(4)
            mf1.metric("Total de dizimos", str(qtd_total), help="Quantidade de lancamentos no periodo")
            mf2.metric("Valor total", formatar_moeda(valor_total))
            mf3.metric("Media por contribuicao", formatar_moeda(media_valor))
            mf4.metric("Meses com dizimo", f"{meses_unicos} mes(es)")

            # Mapa de presenca (sempre mostra, mesmo se 0 dizimos)
            meses_com_diz = set(diz_membro["mes_periodo"].dropna().tolist()) if qtd_total else set()
            badges_html = '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;margin-bottom:18px">'

            for m in meses_seq:
                presente = m in meses_com_diz
                if presente:
                    valor_mes = diz_membro[diz_membro["mes_periodo"] == m]["valor"].sum()
                    qtd_mes = len(diz_membro[diz_membro["mes_periodo"] == m])

                    badges_html += (
                        f'<div style="background:#10B981;color:white;'
                        f'padding:8px 14px;border-radius:8px;font-size:0.82rem;'
                        f'font-weight:600;text-align:center;min-width:90px">'
                        f'✅ {m.strftime("%b/%y")}<br>'
                        f'<span style="font-size:0.72rem;font-weight:400;opacity:0.9">'
                        f'{qtd_mes}x · {formatar_moeda(valor_mes)}</span>'
                        f'</div>'
                    )
                else:
                    badges_html += (
                        f'<div style="background:#374151;color:#94A3B8;'
                        f'padding:8px 14px;border-radius:8px;font-size:0.82rem;'
                        f'text-align:center;min-width:90px;opacity:0.6">'
                        f'❌ {m.strftime("%b/%y")}<br>'
                        f'<span style="font-size:0.72rem">sem dizimo</span>'
                        f'</div>'
                    )

            badges_html += "</div>"
            st.markdown(badges_html, unsafe_allow_html=True)

            # Avaliacao pastoral
            if qtd_total == 0:
                # Membro nao contribuiu nada
                st.markdown(
                    f'<div style="background:#1E293B;border-left:4px solid #DC2626;'
                    f'padding:14px 18px;border-radius:8px;margin-bottom:18px">'
                    f'<div style="color:#DC2626;font-weight:700;font-size:1.05rem">'
                    f'🚨 Sem contribuicoes no periodo'
                    f'</div>'
                    f'<div style="color:#CBD5E1;font-size:0.88rem;margin-top:6px">'
                    f'<b>{membro_sel_freq}</b> nao possui dizimos registrados no periodo selecionado. '
                    f'Recomenda-se visita pastoral ou contato para aconselhamento.'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            elif len(meses_seq) > 0:
                taxa_freq = (meses_unicos / len(meses_seq)) * 100
                if taxa_freq >= 80:
                    cor_freq = "#10B981"
                    msg_freq = "🌟 Excelente frequencia"
                elif taxa_freq >= 50:
                    cor_freq = "#F59E0B"
                    msg_freq = "👍 Boa frequencia"
                else:
                    cor_freq = "#EF4444"
                    msg_freq = "⚠️ Frequencia baixa — necessita atencao pastoral"

                st.markdown(
                    f'<div style="background:#1E293B;border-left:4px solid {cor_freq};'
                    f'padding:12px 16px;border-radius:8px;margin-bottom:18px">'
                    f'<div style="color:{cor_freq};font-weight:700;font-size:1rem">{msg_freq}</div>'
                    f'<div style="color:#CBD5E1;font-size:0.85rem;margin-top:4px">'
                    f'Taxa de frequencia: <b>{taxa_freq:.1f}%</b> — contribuiu em '
                    f'{meses_unicos} de {len(meses_seq)} meses do periodo.'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

            # Tabela detalhada (so se tiver dizimos)
            if qtd_total > 0:
                with st.expander(
                    f"📋 Ver detalhamento dos {qtd_total} dizimo(s) de {membro_sel_freq}",
                    expanded=False,
                ):
                    cols_detalhe = ["data", "valor"]
                    if "forma_pagamento" in diz_membro.columns:
                        cols_detalhe.append("forma_pagamento")
                    cols_detalhe.append("descricao")

                    df_detalhe = diz_membro[cols_detalhe].copy()
                    df_detalhe["data"] = pd.to_datetime(df_detalhe["data"], errors="coerce")
                    df_detalhe = df_detalhe.sort_values("data", ascending=False)
                    df_detalhe["data"] = df_detalhe["data"].dt.strftime("%d/%m/%Y")
                    df_detalhe["valor"] = df_detalhe["valor"].apply(formatar_moeda)

                    df_detalhe = df_detalhe.rename(columns={
                        "data": "Data",
                        "valor": "Valor",
                        "forma_pagamento": "Forma de pagamento",
                        "descricao": "Descricao",
                    })

                    st.dataframe(df_detalhe, use_container_width=True, hide_index=True)

                    csv_membro = df_detalhe.to_csv(index=False, encoding="utf-8-sig")
                    st.download_button(
                        f"📥 Exportar dizimos de {membro_sel_freq}",
                        csv_membro,
                        f"dizimos_{membro_sel_freq.replace(' ', '_').lower()}.csv",
                        "text/csv",
                        key=f"dl_dizimos_{membro_sel_freq}",
                    )

    # ── TOP 10 DIZIMISTAS (VALOR) ─────────────────────────────────────────
    if not diz_f.empty:
        st.markdown(
            '<div class="grafico-titulo">💰 Top 10 Dizimistas (Valor)</div>',
            unsafe_allow_html=True,
        )

        d = (
            diz_f.groupby("nome_cadastro", as_index=False)["valor"]
            .sum()
            .sort_values("valor", ascending=False)
            .head(10)
        )
        pares = sorted(zip(d["valor"], d["nome_cadastro"]))

        fig3 = go.Figure(go.Bar(
            x=[p[0] for p in pares],
            y=[p[1] for p in pares],
            orientation="h",
            marker_color=COR["dizimo"],
            text=[formatar_moeda(p[0]) for p in pares],
            textposition="outside",
            textfont=dict(color="#CBD5E1", size=11),
            hoverinfo="skip",
        ))
        fig3.update_layout(**_base_layout(
            height=_altura_ranking(len(d)),
            xaxis=dict(showticklabels=False, showgrid=False, fixedrange=True),
            yaxis=dict(showgrid=False, fixedrange=True, color="#CBD5E1"),
        ))
        st.plotly_chart(fig3, **OPC)

    st.markdown(
        '<div class="grafico-titulo">👥 Entradas por Funcao do Membro</div>',
        unsafe_allow_html=True,
    )

    ent_m = df_f[
        (df_f["tipo"].str.upper() == "ENTRADA") &
        (df_f["tipo_cadastro"].str.upper() == "MEMBRO")
    ].copy()

    if ent_m.empty:
        st.info("Sem entradas de membros no periodo.")
    else:
        mg = ent_m.merge(df_cad[["id_cadastro", "funcao"]], on="id_cadastro", how="left")
        mg["funcao"] = mg["funcao"].replace("", pd.NA).fillna("Sem funcao")
        rf = mg.groupby("funcao", as_index=False)["valor"].sum().sort_values("valor", ascending=False)

        fig5 = go.Figure(go.Bar(
            x=rf["funcao"],
            y=rf["valor"],
            marker_color=COR["funcao"],
            text=[formatar_moeda(v) for v in rf["valor"]],
            textposition="outside",
            textfont=dict(color="#CBD5E1", size=11),
            hoverinfo="skip",
        ))
        fig5.update_layout(**_base_layout(
            height=ALT_BARRAS_VERT,
            yaxis=dict(showticklabels=False, showgrid=False, fixedrange=True),
            xaxis=dict(showgrid=False, fixedrange=True, color="#CBD5E1"),
        ))
        st.plotly_chart(fig5, **OPC)

    st.divider()
    df_exp = df_f.copy()
    df_exp["data"] = pd.to_datetime(df_exp["data"]).dt.strftime("%d/%m/%Y")

    colx, _ = st.columns([1, 4])
    with colx:
        st.download_button(
            "📥 Exportar CSV",
            gerar_csv(df_exp),
            "dashboard.csv",
            "text/csv",
            use_container_width=True,
        )
>>>>>>> 260a16ed078d5ed38360fa871afe8ae8dac6cacc
