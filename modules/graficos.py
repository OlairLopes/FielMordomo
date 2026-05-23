import datetime
import calendar
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.repository import (
    carregar_lancamentos, carregar_cadastros,
    obter_config_igreja, DIAS_DIZIMISTA_ATIVO_DEFAULT,
)
from utils.helpers import formatar_moeda, gerar_csv, slug_da_sessao

T = "plotly_dark"

# ── PALETA DE CORES (tema escuro) ─────────────────────────────────────────
COR = {
    "Entrada":    "#10B981",
    "Saida":      "#EF4444",
    "saldo":      "#3B82F6",
    "dizimo":     "#10B981",
    "missao":     "#F59E0B",
    "campanha":   "#8B5CF6",
    "oferta":     "#EC4899",
    "despesa":    "#EF4444",
    "qtd_dizimo": "#10B981",
    "funcao":     "#3B82F6",
}

CORES_CATEGORIA = {
    "DIZIMO":   "#10B981",
    "OFERTA":   "#3B82F6",
    "MISSAO":   "#F59E0B",
    "CAMPANHA": "#8B5CF6",
}

CORES_DESPESAS = [
    "#EF4444", "#F59E0B", "#10B981", "#3B82F6",
    "#8B5CF6", "#EC4899", "#6366F1", "#14B8A6", "#94A3B8",
]

ALT_COMPARACAO  = 380
ALT_RANK_BASE   = 320
ALT_POR_ITEM    = 55
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
    .kpi-card-v2 .kpi-variacao.up    { color: #10B981; }
    .kpi-card-v2 .kpi-variacao.down  { color: #EF4444; }
    .kpi-card-v2 .kpi-variacao.flat  { color: #94A3B8; }

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
    .stSelectbox label, .stDateInput label {
        color: #CBD5E1 !important;
    }

    /* Card de inativos financeiros */
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
    </style>
    """, unsafe_allow_html=True)


def _meses_disponiveis(df):
    if df.empty or "data" not in df.columns:
        return []
    return sorted(
        df["data"].dropna().dt.to_period("M").unique(),
        reverse=True,
    )


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
    html = f"""
    <div class="kpi-card-v2">
        <div class="kpi-icon" style="background:{cor_icone}33;color:{cor_icone}">
            {icone}
        </div>
        <div class="kpi-titulo">{titulo}</div>
        <div class="kpi-valor">{valor}</div>
        <div class="kpi-variacao {direcao}">{variacao}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def _calc_periodo_serie(df, mes_ref):
    if df.empty or df["mes_periodo"].dropna().empty:
        primeiro_mes_dados = mes_ref
    else:
        primeiro_mes_dados = df["mes_periodo"].dropna().min()

    ini_serie = max(primeiro_mes_dados, MES_MINIMO_SISTEMA)
    ini_12m_limite = mes_ref - 11
    ini_12m = max(ini_serie, ini_12m_limite)
    fim_12m = mes_ref

    if fim_12m < ini_12m:
        ini_12m = fim_12m

    qtd_meses  = max(1, (fim_12m - ini_12m).n + 1)
    meses_seq  = [(ini_12m + i) for i in range(qtd_meses)]
    labels_12m = [m.strftime("%b/%y") for m in meses_seq]

    titulo_periodo = (
        f"{ini_12m.strftime('%b/%y')} a {fim_12m.strftime('%b/%y')}"
        if qtd_meses > 1
        else fim_12m.strftime('%b/%y')
    )

    return ini_12m, fim_12m, meses_seq, labels_12m, titulo_periodo


def _calcular_inativos_financeiros(df_membros_ativos, df_dizimos, hoje):
    """
    Calcula membros inativos por faixa de dias sem dizimo.

    Retorna dict:
    {
        '30': {'qtd': N, 'pct': P, 'lista': [{'nome', 'telefone', 'ultimo', 'dias'}]},
        '60': {...}, '90': {...}
    }
    """
    total_membros = len(df_membros_ativos)

    ultimo_diz = {}
    if not df_dizimos.empty:
        agrup = df_dizimos.groupby("id_cadastro")["data"].max()
        ultimo_diz = agrup.to_dict()

    resultado = {}
    for faixa_dias in [30, 60, 90]:
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
                dias_sem = 9999  # Nunca dizimou
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
                    "nome": str(m["nome"]),
                    "telefone": tel_fmt or "—",
                    "ultimo": ultimo_str,
                    "dias": dias_sem if dias_sem < 9999 else None,
                })

        lista.sort(key=lambda x: x["dias"] if x["dias"] is not None else 99999, reverse=True)

        pct = (len(lista) / total_membros * 100) if total_membros else 0
        resultado[str(faixa_dias)] = {
            "qtd": len(lista),
            "pct": pct,
            "lista": lista,
        }

    return resultado


def render():
    _injetar_css_dashboard()

    slug    = slug_da_sessao()
    df_lanc = carregar_lancamentos(slug)
    df_cad  = carregar_cadastros(slug)

    if df_lanc.empty:
        st.info("Ainda nao ha lancamentos para o dashboard.")
        return

    df = df_lanc.copy()
    df["data"]  = pd.to_datetime(df["data"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df["mes_periodo"] = df["data"].dt.to_period("M")
    df["mes_label"]   = df["data"].dt.strftime("%b/%Y")
    df["id_cadastro"] = pd.to_numeric(df["id_cadastro"], errors="coerce")

    if "subcategoria" not in df.columns:
        df["subcategoria"] = ""
    df["subcategoria"] = df["subcategoria"].fillna("").astype(str)

    if "funcao" not in df_cad.columns:
        df_cad["funcao"] = ""
    df_cad["funcao"] = df_cad["funcao"].fillna("").astype(str)
    df_cad["id_cadastro"] = pd.to_numeric(df_cad["id_cadastro"], errors="coerce")

    try:
        dias_ativo = int(obter_config_igreja(
            slug, "dias_dizimista_ativo", str(DIAS_DIZIMISTA_ATIVO_DEFAULT)
        ))
    except (ValueError, TypeError):
        dias_ativo = DIAS_DIZIMISTA_ATIVO_DEFAULT

    st.markdown("### 📊 Dashboard")
    st.caption("Visao geral da saude financeira da igreja")

    # ── Seletor de mes de referencia e comparacao ─────────────────────────
    meses = _meses_disponiveis(df)
    if not meses:
        st.warning("Sem dados de data para os lancamentos.")
        return

    if "db_mes_ref" not in st.session_state:
        st.session_state["db_mes_ref"] = str(meses[0])

    meses_str = [str(m) for m in meses]
    meses_lbl = [m.strftime("%b/%Y") for m in meses]
    map_lbl   = dict(zip(meses_str, meses_lbl))

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
        st.markdown(
            '<div style="margin-top:28px"></div>',
            unsafe_allow_html=True,
        )
        modo_personalizado = st.toggle(
            "Personalizado",
            value=False,
            key="db_modo_personalizado",
            help="Ativa filtros avancados",
        )

    df_ref  = df[df["mes_periodo"] == mes_ref].copy()
    df_comp = df[df["mes_periodo"] == mes_comp].copy()

    membro_sel    = "Todos"
    funcao_sel    = "Todas"
    categoria_sel = "Todas"
    d_ini = None
    d_fim = None

    if modo_personalizado:
        st.markdown(
            '<div class="filtro-mes-box">'
            '<b style="color:#F1F5F9">🔍 Modo Personalizado</b> '
            '<span style="color:#94A3B8">— todos os cards e graficos respeitam os filtros abaixo. '
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
            f for f in df_cad["funcao"].dropna().unique() if str(f).strip()
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
            df_f = df_f[df_f["nome_cadastro"].fillna("").str.strip() == membro_sel]
        if funcao_sel != "Todas":
            ids_funcao = df_cad[
                df_cad["funcao"].fillna("").str.strip() == funcao_sel
            ]["id_cadastro"].tolist()
            df_f = df_f[df_f["id_cadastro"].isin(ids_funcao)]
        if categoria_sel != "Todas":
            df_f = df_f[df_f["categoria"].fillna("").str.strip() == categoria_sel]
    else:
        df_f = df_ref

    # ── CALCULA PERIODO DE COMPARACAO E DATAFRAMES PARA CARDS ─────────────
    if modo_personalizado:
        dias_periodo = (d_fim - d_ini).days + 1
        d_fim_comp_pers = d_ini - datetime.timedelta(days=1)
        d_ini_comp_pers = d_fim_comp_pers - datetime.timedelta(days=dias_periodo - 1)

        df_comp_pers = df[
            (df["data"] >= pd.Timestamp(d_ini_comp_pers)) &
            (df["data"] <= pd.Timestamp(d_fim_comp_pers))
        ].copy()

        if membro_sel != "Todos":
            df_comp_pers = df_comp_pers[
                df_comp_pers["nome_cadastro"].fillna("").str.strip() == membro_sel
            ]
        if funcao_sel != "Todas":
            ids_funcao = df_cad[
                df_cad["funcao"].fillna("").str.strip() == funcao_sel
            ]["id_cadastro"].tolist()
            df_comp_pers = df_comp_pers[df_comp_pers["id_cadastro"].isin(ids_funcao)]
        if categoria_sel != "Todas":
            df_comp_pers = df_comp_pers[
                df_comp_pers["categoria"].fillna("").str.strip() == categoria_sel
            ]

        df_card_atual = df_f
        df_card_comp  = df_comp_pers

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
        df_card_comp  = df_comp
        label_atual   = mes_ref.strftime("%b/%Y")

    # ── CARDS KPI ─────────────────────────────────────────────────────────
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
    qtd_diz_ref  = diz_ref["id_cadastro"].dropna().nunique()
    qtd_diz_comp = diz_comp["id_cadastro"].dropna().nunique()

    membros_ativos_n = len(df_cad[
        (df_cad["tipo_cadastro"].str.upper() == "MEMBRO") &
        (df_cad["situacao"].fillna("").str.upper() == "ATIVO")
    ])
    taxa_ref  = (qtd_diz_ref / membros_ativos_n * 100) if membros_ativos_n else 0
    taxa_comp = (qtd_diz_comp / membros_ativos_n * 100) if membros_ativos_n else 0

    miss_ref  = df_card_atual[
        (df_card_atual["tipo"].str.upper() == "ENTRADA") &
        (df_card_atual["categoria"].str.upper() == "MISSAO")
    ]["valor"].sum()
    miss_comp = df_card_comp[
        (df_card_comp["tipo"].str.upper() == "ENTRADA") &
        (df_card_comp["categoria"].str.upper() == "MISSAO")
    ]["valor"].sum()

    ano_ref = mes_ref.year
    df_ano  = df[df["data"].dt.year == ano_ref]
    df_ano_ant = df[df["data"].dt.year == ano_ref - 1]
    ent_ano    = df_ano[df_ano["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    ent_ano_ant = df_ano_ant[df_ano_ant["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    cresc_pct  = ((ent_ano - ent_ano_ant) / abs(ent_ano_ant) * 100) if ent_ano_ant else 0

    var_ent, dir_ent = _calc_variacao(ent_ref, ent_comp)
    var_sai, dir_sai = _calc_variacao(sai_ref, sai_comp)
    var_sal, dir_sal = _calc_variacao(sal_ref, sal_comp)
    var_diz, dir_diz = _calc_variacao(qtd_diz_ref, qtd_diz_comp)
    var_taxa, dir_taxa = _calc_variacao(taxa_ref, taxa_comp)
    var_miss, dir_miss = _calc_variacao(miss_ref, miss_comp)

    r1c1, r1c2, r1c3 = st.columns(3)
    r2c1, r2c2, r2c3 = st.columns(3)

    with r1c1:
        _kpi_card(
            f"Entradas {label_atual}",
            formatar_moeda(ent_ref),
            var_ent, dir_ent,
            "#10B981", "💰",
        )
    with r1c2:
        _kpi_card(
            f"Despesas {label_atual}",
            formatar_moeda(sai_ref),
            var_sai, dir_sai,
            "#EF4444", "💸",
        )
    with r1c3:
        _kpi_card(
            f"Saldo {label_atual}",
            formatar_moeda(sal_ref),
            var_sal, dir_sal,
            "#3B82F6", "📊",
        )

    with r2c1:
        _kpi_card(
            "Dizimistas no periodo",
            str(qtd_diz_ref),
            var_diz, dir_diz,
            "#8B5CF6", "🙏",
        )
    with r2c2:
        _kpi_card(
            "Taxa de fidelidade",
            f"{taxa_ref:.1f}%",
            var_taxa, dir_taxa,
            "#F59E0B", "📈",
        )
    with r2c3:
        seta_cresc = "↑" if cresc_pct > 0 else ("↓" if cresc_pct < 0 else "—")
        dir_cresc  = "up" if cresc_pct > 0 else ("down" if cresc_pct < 0 else "flat")
        _kpi_card(
            f"Crescimento {ano_ref}",
            f"{cresc_pct:+.1f}%" if ent_ano_ant else "Sem dados",
            f"{seta_cresc} vs {ano_ref - 1}" if ent_ano_ant else "Primeiro ano",
            dir_cresc,
            "#14B8A6", "📅",
        )

    # Card destacado de Investimentos no Reino
    st.markdown("")
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

    st.markdown("")
    OPC = dict(use_container_width=True, config=CONFIG_PLOTLY)

    if df_f.empty:
        st.warning("Sem lancamentos no periodo selecionado.")
        return

    # ── Fluxo de caixa (respeita modo personalizado) ──────────────────────
    if modo_personalizado:
        meses_disp_personalizado = sorted(df_f["mes_periodo"].dropna().unique())

        if len(meses_disp_personalizado) == 0:
            st.warning("Sem dados de meses no periodo filtrado.")
            return

        meses_seq  = meses_disp_personalizado
        labels_12m = [m.strftime("%b/%y") for m in meses_seq]
        ini_12m    = meses_seq[0]
        fim_12m    = meses_seq[-1]

        titulo_periodo = (
            f"{ini_12m.strftime('%b/%y')} a {fim_12m.strftime('%b/%y')}"
            if len(meses_seq) > 1
            else fim_12m.strftime('%b/%y')
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
            sub = df_12m[(df_12m["mes_periodo"] == m) & (df_12m["tipo"].str.upper() == t.upper())]
            out.append(float(sub["valor"].sum()))
        return out

    e12 = _serie_12m("Entrada")
    s12 = _serie_12m("Saida")
    sal12 = [e - s for e, s in zip(e12, s12)]

    fig_fc = go.Figure([
        go.Bar(
            name="Entradas",
            x=labels_12m, y=e12,
            marker_color=COR["Entrada"],
            text=[formatar_moeda(v) if v > 0 else "" for v in e12],
            textposition="outside",
            textfont=dict(size=10, color="#CBD5E1"),
            hoverinfo="skip",
        ),
        go.Bar(
            name="Despesas",
            x=labels_12m, y=s12,
            marker_color=COR["Saida"],
            text=[formatar_moeda(v) if v > 0 else "" for v in s12],
            textposition="outside",
            textfont=dict(size=10, color="#CBD5E1"),
            hoverinfo="skip",
        ),
        go.Bar(
            name="Saldo",
            x=labels_12m, y=sal12,
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
        yaxis=dict(fixedrange=True, gridcolor="#334155", color="#94A3B8",
                   tickformat=",.0f"),
        bargap=0.20,
        bargroupgap=0.05,
    ))
    st.plotly_chart(fig_fc, **OPC)

    # ── Donuts de Entradas e Despesas ─────────────────────────────────────
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
                x=0.5, y=0.5,
                font=dict(size=13, color="#F1F5F9"),
                showarrow=False,
            )
            fig_ec.update_layout(**_base_layout(
                height=ALT_COMPARACAO,
                showlegend=True,
                legend=dict(orientation="v", y=0.5, x=1.05,
                            font=dict(color="#E5E7EB", size=11)),
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
                x=0.5, y=0.5,
                font=dict(size=13, color="#F1F5F9"),
                showarrow=False,
            )
            fig_dc.update_layout(**_base_layout(
                height=ALT_COMPARACAO,
                showlegend=True,
                legend=dict(orientation="v", y=0.5, x=1.05,
                            font=dict(color="#E5E7EB", size=11)),
                margin=dict(t=20, b=20, l=20, r=20),
            ))
            st.plotly_chart(fig_dc, **OPC)

    # ── Evolucao dos dizimos ──────────────────────────────────────────────
    st.markdown(
        f'<div class="grafico-titulo">💰 Evolucao dos Dizimos — {titulo_periodo}'
        f'<span class="subtitulo">Total arrecadado em dizimos mes a mes</span></div>',
        unsafe_allow_html=True,
    )

    def _dizimo_mensal(m):
        sub = df_12m[
            (df_12m["mes_periodo"] == m) &
            (df_12m["categoria"].str.upper() == "DIZIMO")
        ]
        return float(sub["valor"].sum())

    d12 = [_dizimo_mensal(m) for m in meses_seq]

    fig_d = go.Figure([
        go.Bar(
            x=labels_12m, y=d12,
            marker_color=COR["dizimo"],
            text=[formatar_moeda(v) if v > 0 else "" for v in d12],
            textposition="outside",
            textfont=dict(size=10, color="#CBD5E1"),
            hoverinfo="skip",
        ),
    ])
    if len([v for v in d12 if v > 0]) >= 3:
        ma = []
        for i in range(len(d12)):
            ini = max(0, i - 2)
            window = d12[ini:i+1]
            ma.append(sum(window) / len(window) if window else 0)
        fig_d.add_trace(go.Scatter(
            x=labels_12m, y=ma, mode="lines",
            line=dict(color="#94A3B8", width=2, dash="dot"),
            name="Tendencia",
            hoverinfo="skip",
        ))

    fig_d.update_layout(**_base_layout(
        height=ALT_COMPARACAO,
        showlegend=False,
        margin=dict(t=30, b=30, l=10, r=10),
        xaxis=dict(fixedrange=True, color="#94A3B8", gridcolor="#334155"),
        yaxis=dict(fixedrange=True, gridcolor="#334155", color="#94A3B8",
                   tickformat=",.0f"),
    ))
    st.plotly_chart(fig_d, **OPC)

    # ── INATIVOS FINANCEIROS (FASE 2) ─────────────────────────────────────
    st.markdown(
        f'<div class="grafico-titulo">⚠️ Membros Inativos Financeiramente'
        f'<span class="subtitulo">Configuracao da igreja: dizimista ativo = ate {dias_ativo} dias. '
        f'As 3 faixas abaixo mostram quem esta abaixo desse criterio.</span></div>',
        unsafe_allow_html=True,
    )

    df_mem_ativos_full = df_cad[
        (df_cad["tipo_cadastro"].str.upper() == "MEMBRO") &
        (df_cad["situacao"].fillna("").str.upper() == "ATIVO")
    ].copy()

    df_dizimos_todos = df[
        (df["categoria"].str.upper() == "DIZIMO") &
        (df["tipo_cadastro"].str.upper() == "MEMBRO")
    ].copy()

    hoje_dt = datetime.date.today()
    inativos = _calcular_inativos_financeiros(
        df_mem_ativos_full, df_dizimos_todos, hoje_dt
    )

    ina_c1, ina_c2, ina_c3 = st.columns(3)

    cores_inativos = {
        "30": ("amarelo", "30 dias ou mais", "🟡"),
        "60": ("laranja", "60 dias ou mais", "🟠"),
        "90": ("vermelho", "90 dias ou mais", "🔴"),
    }

    for (faixa, (cor, titulo, icone)), col in zip(
        cores_inativos.items(), [ina_c1, ina_c2, ina_c3]
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
                "nome":     "Nome",
                "telefone": "Telefone",
                "ultimo":   "Ultimo dizimo",
                "dias":     "Dias sem dizimar",
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

    # ── Percentual de dizimistas ──────────────────────────────────────────
    st.markdown(
        '<div class="grafico-titulo">🙏 Percentual de Dizimistas'
        '<span class="subtitulo">Membros ativos que contribuiram no periodo</span></div>',
        unsafe_allow_html=True,
    )

    df_membros_ativos = df_cad[
        (df_cad["tipo_cadastro"].str.upper() == "MEMBRO") &
        (df_cad["situacao"].fillna("").str.upper() == "ATIVO")
    ].copy()

    if modo_personalizado and funcao_sel != "Todas":
        df_membros_ativos = df_membros_ativos[
            df_membros_ativos["funcao"].fillna("").str.strip() == funcao_sel
        ]
    if modo_personalizado and membro_sel != "Todos":
        df_membros_ativos = df_membros_ativos[
            df_membros_ativos["nome"].fillna("").str.strip() == membro_sel
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
            marker=dict(colors=[COR["Entrada"], "#374151"],
                        line=dict(color="#1E293B", width=2)),
            hoverinfo="skip",
        ))
        fig_pct.add_annotation(
            text=f"<b>{pct:.1f}%</b>",
            x=0.5, y=0.55,
            font=dict(size=32, color=COR["Entrada"]),
            showarrow=False,
        )
        fig_pct.add_annotation(
            text="dizimistas",
            x=0.5, y=0.40,
            font=dict(size=12, color="#94A3B8"),
            showarrow=False,
        )
        fig_pct.update_layout(**_base_layout(
            height=ALT_COMPARACAO,
            showlegend=True,
            legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center",
                        font=dict(color="#E5E7EB")),
            margin=dict(t=10, b=40, l=10, r=10),
        ))
        st.plotly_chart(fig_pct, **OPC)

        km1, km2, km3 = st.columns(3)
        km1.metric("Membros ativos", str(total_membros))
        km2.metric("Dizimistas", str(qtd_d), delta=f"{pct:.1f}%")
        km3.metric("Nao dizimistas", str(qtd_nd),
                   delta=f"-{100-pct:.1f}%", delta_color="inverse")

    # ── Top dizimistas + Frequencia individual ────────────────────────────
    diz_f = df_f[
        (df_f["categoria"].str.upper() == "DIZIMO") &
        (df_f["tipo_cadastro"].str.upper() == "MEMBRO")
    ]

    if not diz_f.empty:
        st.markdown(
            '<div class="grafico-titulo">🔢 Frequencia de Dizimos'
            '<span class="subtitulo">Top 10 — qtd de lancamentos por membro</span></div>',
            unsafe_allow_html=True,
        )
        dq = (
            diz_f.groupby("nome_cadastro", as_index=False)
            .size()
            .rename(columns={"size": "quantidade"})
            .sort_values("quantidade", ascending=False)
            .head(10)
        )
        pares_q = sorted(zip(dq["quantidade"], dq["nome_cadastro"]))
        fig_qtd = go.Figure(go.Bar(
            x=[p[0] for p in pares_q], y=[p[1] for p in pares_q],
            orientation="h", marker_color=COR["qtd_dizimo"],
            text=[str(p[0]) for p in pares_q],
            textposition="outside",
            textfont=dict(color="#CBD5E1", size=11),
            hoverinfo="skip",
        ))
        fig_qtd.update_layout(**_base_layout(
            height=_altura_ranking(len(dq)),
            xaxis=dict(showticklabels=False, showgrid=False, fixedrange=True),
            yaxis=dict(showgrid=False, fixedrange=True, color="#CBD5E1"),
        ))
        st.plotly_chart(fig_qtd, **OPC)

        # ── Frequencia individual de um membro especifico ─────────────────
        st.markdown(
            '<div class="grafico-titulo">🔍 Frequencia Individual do Membro'
            '<span class="subtitulo">Selecione um membro para ver detalhes da contribuicao</span></div>',
            unsafe_allow_html=True,
        )

        membros_dizimistas = sorted(
            diz_f["nome_cadastro"].dropna().unique().tolist()
        )

        membro_sel_freq = st.selectbox(
            "Membro",
            ["— Selecione um membro —"] + membros_dizimistas,
            key="freq_membro_sel",
            help="Mostra todos os dizimos deste membro no periodo selecionado.",
        )

        if membro_sel_freq != "— Selecione um membro —":
            diz_membro = diz_f[
                diz_f["nome_cadastro"].fillna("").str.strip() == membro_sel_freq
            ].copy()

            if diz_membro.empty:
                st.info(f"Nenhum dizimo de {membro_sel_freq} no periodo.")
            else:
                qtd_total = len(diz_membro)
                valor_total = diz_membro["valor"].sum()
                media_valor = valor_total / qtd_total if qtd_total else 0
                meses_unicos = diz_membro["mes_periodo"].nunique()

                mf1, mf2, mf3, mf4 = st.columns(4)
                with mf1:
                    st.metric(
                        "Total de dizimos",
                        str(qtd_total),
                        help="Quantidade de lancamentos no periodo",
                    )
                with mf2:
                    st.metric(
                        "Valor total",
                        formatar_moeda(valor_total),
                    )
                with mf3:
                    st.metric(
                        "Media por contribuicao",
                        formatar_moeda(media_valor),
                    )
                with mf4:
                    st.metric(
                        "Meses com dizimo",
                        f"{meses_unicos} mes(es)",
                    )

                # Mapa de presenca mensal
                st.markdown(
                    f'<div style="margin-top:18px;color:#94A3B8;font-size:0.85rem">'
                    f'📅 <b>Mapa de presenca</b> — em quais meses {membro_sel_freq} contribuiu '
                    f'(periodo do dashboard)'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                meses_com_diz = set(diz_membro["mes_periodo"].dropna().tolist())

                badges_html = '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;margin-bottom:18px">'
                for m in meses_seq:
                    presente = m in meses_com_diz
                    if presente:
                        valor_mes = diz_membro[
                            diz_membro["mes_periodo"] == m
                        ]["valor"].sum()
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
                badges_html += '</div>'
                st.markdown(badges_html, unsafe_allow_html=True)

                # Avaliacao de frequencia
                if len(meses_seq) > 0:
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
                        f'<div style="color:{cor_freq};font-weight:700;font-size:1rem">'
                        f'{msg_freq}'
                        f'</div>'
                        f'<div style="color:#CBD5E1;font-size:0.85rem;margin-top:4px">'
                        f'Taxa de frequencia: <b>{taxa_freq:.1f}%</b> — contribuiu em '
                        f'{meses_unicos} de {len(meses_seq)} meses do periodo.'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                # Tabela detalhada
                with st.expander(
                    f"📋 Ver detalhamento dos {qtd_total} dizimo(s) de {membro_sel_freq}",
                    expanded=False,
                ):
                    cols_detalhe = ["data", "valor"]
                    if "forma_pagamento" in diz_membro.columns:
                        cols_detalhe.append("forma_pagamento")
                    cols_detalhe.append("descricao")

                    df_detalhe = diz_membro[cols_detalhe].copy()

                    df_detalhe["data"] = pd.to_datetime(
                        df_detalhe["data"], errors="coerce"
                    ).dt.strftime("%d/%m/%Y")
                    df_detalhe["valor"] = df_detalhe["valor"].apply(formatar_moeda)
                    df_detalhe = df_detalhe.sort_values("data", ascending=False)

                    rename_map = {
                        "data":            "Data",
                        "valor":           "Valor",
                        "forma_pagamento": "Forma de pagamento",
                        "descricao":       "Descricao",
                    }
                    df_detalhe = df_detalhe.rename(columns=rename_map)

                    st.dataframe(df_detalhe, use_container_width=True, hide_index=True)

                    csv_membro = df_detalhe.to_csv(index=False, encoding="utf-8-sig")
                    st.download_button(
                        f"📥 Exportar dizimos de {membro_sel_freq}",
                        csv_membro,
                        f"dizimos_{membro_sel_freq.replace(' ', '_').lower()}.csv",
                        "text/csv",
                        key=f"dl_dizimos_{membro_sel_freq}",
                    )

        # ── Top 10 dizimistas (valor) ─────────────────────────────────────
        st.markdown(
            '<div class="grafico-titulo">💰 Top 10 Dizimistas (Valor)</div>',
            unsafe_allow_html=True,
        )
        d = diz_f.groupby("nome_cadastro", as_index=False)["valor"].sum().sort_values("valor", ascending=False).head(10)
        pares = sorted(zip(d["valor"], d["nome_cadastro"]))
        fig3 = go.Figure(go.Bar(
            x=[p[0] for p in pares], y=[p[1] for p in pares],
            orientation="h", marker_color=COR["dizimo"],
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

    # ── Entradas por funcao ───────────────────────────────────────────────
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
            x=rf["funcao"], y=rf["valor"],
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

    # ── Exportacao ────────────────────────────────────────────────────────
    st.divider()
    df_exp = df_f.copy()
    df_exp["data"] = pd.to_datetime(df_exp["data"]).dt.strftime("%d/%m/%Y")
    colx, _ = st.columns([1, 4])
    with colx:
        st.download_button(
            "📥 Exportar CSV",
            gerar_csv(df_exp),
            "dashboard.csv", "text/csv",
            use_container_width=True,
        )
