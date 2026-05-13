import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.repository import carregar_lancamentos, carregar_cadastros
from utils.helpers import formatar_moeda, gerar_csv, slug_da_sessao

T = "plotly_white"
COR = {
    "Entrada":    "#1D9E75",
    "Saida":      "#D85A30",
    "saldo":      "#0F6E56",
    "dizimo":     "#1D9E75",
    "despesa":    "#D85A30",
    "funcao":     "#0F6E56",
    "qtd_dizimo": "#3DBE99",
    "secundaria": "#F5A623",
    "neutro":     "#6c757d",
}

CONFIG_PLOTLY = {
    "displayModeBar": False,
    "staticPlot": True,
    "responsive": True,
}


def _base_layout(margin=None, **kw):
    return dict(
        template=T,
        margin=margin if margin is not None else dict(t=10, b=0, l=0, r=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode=False,
        dragmode=False,
        **kw,
    )


def _injetar_css_dashboard():
    """CSS dos cards estilo Power BI."""
    st.markdown("""
    <style>
    /* KPI Cards */
    .kpi-card {
        background: white;
        border-radius: 12px;
        padding: 18px 20px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        border-left: 4px solid #0F6E56;
        height: 100%;
    }
    .kpi-card.entrada  { border-left-color: #1D9E75; }
    .kpi-card.saida    { border-left-color: #D85A30; }
    .kpi-card.saldo    { border-left-color: #0F6E56; }
    .kpi-card.lanc     { border-left-color: #F5A623; }

    .kpi-label {
        font-size: 0.72rem;
        font-weight: 600;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #1a1a1a;
        line-height: 1.2;
    }
    .kpi-extra {
        font-size: 0.72rem;
        color: #6c757d;
        margin-top: 4px;
    }
    .kpi-extra.positivo { color: #1D9E75; }
    .kpi-extra.negativo { color: #D85A30; }

    /* Container de grafico */
    .grafico-box {
        background: white;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
        margin-bottom: 12px;
    }
    .grafico-titulo {
        font-size: 0.9rem;
        font-weight: 600;
        color: #1a1a1a;
        margin-bottom: 8px;
        padding-bottom: 6px;
        border-bottom: 1px solid #eee;
    }

    /* Filtros de periodo */
    div[data-testid="stHorizontalBlock"] button {
        font-size: 0.78rem !important;
        padding: 4px 10px !important;
    }
    </style>
    """, unsafe_allow_html=True)


def _aplicar_filtro_periodo(df, periodo):
    """Aplica filtro pre-definido de periodo no DataFrame."""
    hoje = datetime.date.today()
    if periodo == "Hoje":
        ini = fim = hoje
    elif periodo == "Semana":
        ini = hoje - datetime.timedelta(days=hoje.weekday())
        fim = ini + datetime.timedelta(days=6)
    elif periodo == "Mes":
        ini = hoje.replace(day=1)
        prox_mes = (ini.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        fim = prox_mes - datetime.timedelta(days=1)
    elif periodo == "Ano":
        ini = hoje.replace(month=1, day=1)
        fim = hoje.replace(month=12, day=31)
    else:
        return df, None, None
    return df[(df["data"] >= pd.Timestamp(ini)) & (df["data"] <= pd.Timestamp(fim))], ini, fim


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
    df["mes"]   = df["data"].dt.to_period("M").astype(str)
    df["mes_label"] = df["data"].dt.strftime("%b/%Y")
    df["id_cadastro"] = pd.to_numeric(df["id_cadastro"], errors="coerce")

    if "funcao" not in df_cad.columns:
        df_cad["funcao"] = ""
    df_cad["funcao"] = df_cad["funcao"].fillna("").astype(str)
    df_cad["id_cadastro"] = pd.to_numeric(df_cad["id_cadastro"], errors="coerce")

    # ── Filtros de periodo (botoes) ───────────────────────────────────────
    st.markdown("### Dashboard")
    st.caption("Visao geral das financas da igreja")

    if "db_periodo" not in st.session_state:
        st.session_state["db_periodo"] = "Mes"

    c1, c2, c3, c4, c5 = st.columns(5)
    botoes = [("Hoje", c1), ("Semana", c2), ("Mes", c3), ("Ano", c4), ("Personalizado", c5)]
    for nome, col in botoes:
        with col:
            tipo_btn = "primary" if st.session_state["db_periodo"] == nome else "secondary"
            if st.button(nome, key=f"db_btn_{nome}", use_container_width=True, type=tipo_btn):
                st.session_state["db_periodo"] = nome
                st.rerun()

    periodo_sel = st.session_state["db_periodo"]

    # Aplica filtro
    if periodo_sel == "Personalizado":
        dv = df["data"].dropna()
        cp1, cp2 = st.columns(2)
        with cp1:
            d_ini = st.date_input("De", value=dv.min().date() if not dv.empty else datetime.date.today(),
                                  format="DD/MM/YYYY", key="db_ini")
        with cp2:
            d_fim = st.date_input("Ate", value=dv.max().date() if not dv.empty else datetime.date.today(),
                                  format="DD/MM/YYYY", key="db_fim")
        if d_ini > d_fim:
            st.error("Data inicial maior que data final.")
            return
        df_f = df[(df["data"] >= pd.Timestamp(d_ini)) & (df["data"] <= pd.Timestamp(d_fim))].copy()
    else:
        df_f, d_ini, d_fim = _aplicar_filtro_periodo(df, periodo_sel)
        if d_ini and d_fim:
            st.caption(f"Periodo: {d_ini.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')}")

    if df_f.empty:
        st.warning("Sem lancamentos no periodo selecionado.")
        return

    # ── KPIs ──────────────────────────────────────────────────────────────
    ent = df_f[df_f["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    sai = df_f[df_f["tipo"].str.upper() == "SAIDA"]["valor"].sum()
    sal = ent - sai
    n_lanc = len(df_f)

    st.markdown("")
    k1, k2, k3, k4 = st.columns(4)

    with k1:
        st.markdown(f"""
        <div class="kpi-card saldo">
            <div class="kpi-label">Saldo</div>
            <div class="kpi-value" style="color:{'#1D9E75' if sal >= 0 else '#D85A30'}">{formatar_moeda(sal)}</div>
            <div class="kpi-extra">No periodo selecionado</div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        st.markdown(f"""
        <div class="kpi-card entrada">
            <div class="kpi-label">Entradas</div>
            <div class="kpi-value" style="color:#1D9E75">{formatar_moeda(ent)}</div>
            <div class="kpi-extra positivo">↑ Total arrecadado</div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        st.markdown(f"""
        <div class="kpi-card saida">
            <div class="kpi-label">Saidas</div>
            <div class="kpi-value" style="color:#D85A30">{formatar_moeda(sai)}</div>
            <div class="kpi-extra negativo">↓ Total gasto</div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        st.markdown(f"""
        <div class="kpi-card lanc">
            <div class="kpi-label">Lancamentos</div>
            <div class="kpi-value" style="color:#F5A623">{n_lanc}</div>
            <div class="kpi-extra">Total de registros</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("")
    OPC = dict(use_container_width=True, config=CONFIG_PLOTLY)

    # ── Linha 1: Evolucao mensal (full width) ─────────────────────────────
    st.markdown('<div class="grafico-titulo">📊 Evolucao mensal — Entradas x Saidas</div>', unsafe_allow_html=True)

    res   = df_f.groupby(["mes", "mes_label", "tipo"], as_index=False)["valor"].sum().sort_values("mes")
    meses = sorted(res["mes"].unique())
    labels = [res[res["mes"] == m]["mes_label"].iloc[0] for m in meses]

    def s(t):
        r = res[res["tipo"].str.upper() == t.upper()].set_index("mes")
        return [float(r.loc[m, "valor"]) if m in r.index else 0.0 for m in meses]

    e_vals, s_vals = s("Entrada"), s("Saida")
    sal_vals = [e - sv for e, sv in zip(e_vals, s_vals)]

    fig1 = go.Figure([
        go.Bar(name="Entradas", x=labels, y=e_vals, marker_color=COR["Entrada"],
               text=[formatar_moeda(v) for v in e_vals], textposition="outside", textfont_size=10,
               hoverinfo="skip"),
        go.Bar(name="Saidas", x=labels, y=s_vals, marker_color=COR["Saida"],
               text=[formatar_moeda(v) for v in s_vals], textposition="outside", textfont_size=10,
               hoverinfo="skip"),
        go.Scatter(name="Saldo", x=labels, y=sal_vals, mode="lines+markers",
                   line=dict(color=COR["saldo"], width=3), marker=dict(size=8),
                   hoverinfo="skip"),
    ])
    fig1.update_layout(**_base_layout(
        barmode="group", height=320,
        margin=dict(t=30, b=0, l=0, r=0),
        legend=dict(orientation="h", y=1.15, x=0),
        xaxis=dict(fixedrange=True),
        yaxis=dict(fixedrange=True, gridcolor="#f0f0f0"),
    ))
    st.plotly_chart(fig1, **OPC)

    # ── Linha 2: Pizza + Top dizimistas ───────────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="grafico-titulo">🥧 Distribuicao das entradas</div>', unsafe_allow_html=True)
        ent_cat = df_f[df_f["tipo"].str.upper() == "ENTRADA"].groupby("categoria", as_index=False)["valor"].sum()
        if ent_cat.empty:
            st.info("Sem entradas.")
        else:
            fig2 = go.Figure(go.Pie(
                labels=ent_cat["categoria"], values=ent_cat["valor"], hole=0.55,
                textinfo="percent+label", textfont_size=12,
                marker=dict(colors=["#1D9E75", "#0F6E56", "#3DBE99", "#7FDABC"]),
                hoverinfo="skip",
            ))
            fig2.update_layout(**_base_layout(
                showlegend=False, height=300,
                margin=dict(t=10, b=10, l=10, r=10),
            ))
            st.plotly_chart(fig2, **OPC)

    with c2:
        st.markdown('<div class="grafico-titulo">💰 Top 8 dizimistas (valor)</div>', unsafe_allow_html=True)
        diz = df_f[(df_f["categoria"].str.upper() == "DIZIMO") & (df_f["tipo_cadastro"].str.upper() == "MEMBRO")]
        if diz.empty:
            st.info("Sem dizimos.")
        else:
            d = diz.groupby("nome_cadastro", as_index=False)["valor"].sum().sort_values("valor", ascending=False).head(8)
            pares = sorted(zip(d["valor"], d["nome_cadastro"]))
            fig3 = go.Figure(go.Bar(
                x=[p[0] for p in pares], y=[p[1] for p in pares], orientation="h",
                marker_color=COR["dizimo"],
                text=[formatar_moeda(p[0]) for p in pares], textposition="outside",
                hoverinfo="skip",
            ))
            fig3.update_layout(**_base_layout(
                height=max(220, len(d) * 38),
                xaxis=dict(showticklabels=False, showgrid=False, fixedrange=True),
                yaxis=dict(showgrid=False, fixedrange=True),
            ))
            st.plotly_chart(fig3, **OPC)

    # ── Linha 3: Frequencia + Despesas ────────────────────────────────────
    c3, c4 = st.columns(2)

    with c3:
        st.markdown('<div class="grafico-titulo">🔢 Frequencia de dizimos (qtd lancamentos)</div>', unsafe_allow_html=True)
        if diz.empty:
            st.info("Sem dizimos no periodo.")
        else:
            dq = (
                diz.groupby("nome_cadastro", as_index=False)
                .size()
                .rename(columns={"size": "quantidade"})
                .sort_values("quantidade", ascending=False)
                .head(10)
            )
            pares_q = sorted(zip(dq["quantidade"], dq["nome_cadastro"]))
            fig_qtd = go.Figure(go.Bar(
                x=[p[0] for p in pares_q], y=[p[1] for p in pares_q], orientation="h",
                marker_color=COR["qtd_dizimo"],
                text=[str(p[0]) for p in pares_q], textposition="outside",
                hoverinfo="skip",
            ))
            fig_qtd.update_layout(**_base_layout(
                height=max(220, len(dq) * 38),
                xaxis=dict(showticklabels=False, showgrid=False, fixedrange=True),
                yaxis=dict(showgrid=False, fixedrange=True),
            ))
            st.plotly_chart(fig_qtd, **OPC)

    with c4:
        st.markdown('<div class="grafico-titulo">📉 Top 8 despesas</div>', unsafe_allow_html=True)
        desp = df_f[df_f["categoria"].str.upper() == "DESPESA"]
        if desp.empty:
            st.info("Sem despesas.")
        else:
            d2 = desp.groupby("descricao", as_index=False)["valor"].sum().sort_values("valor", ascending=False).head(8)
            pares = sorted(zip(d2["valor"], d2["descricao"]))
            fig4 = go.Figure(go.Bar(
                x=[p[0] for p in pares], y=[p[1] for p in pares], orientation="h",
                marker_color=COR["despesa"],
                text=[formatar_moeda(p[0]) for p in pares], textposition="outside",
                hoverinfo="skip",
            ))
            fig4.update_layout(**_base_layout(
                height=max(220, len(d2) * 38),
                xaxis=dict(showticklabels=False, showgrid=False, fixedrange=True),
                yaxis=dict(showgrid=False, fixedrange=True),
            ))
            st.plotly_chart(fig4, **OPC)

    # ── Linha 4: Entradas por funcao ──────────────────────────────────────
    st.markdown('<div class="grafico-titulo">👥 Entradas por funcao do membro</div>', unsafe_allow_html=True)
    ent_m = df_f[(df_f["tipo"].str.upper() == "ENTRADA") & (df_f["tipo_cadastro"].str.upper() == "MEMBRO")].copy()
    if ent_m.empty:
        st.info("Sem entradas de membros.")
    else:
        mg = ent_m.merge(df_cad[["id_cadastro", "funcao"]], on="id_cadastro", how="left")
        mg["funcao"] = mg["funcao"].replace("", pd.NA).fillna("Sem funcao")
        rf = mg.groupby("funcao", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
        fig5 = go.Figure(go.Bar(
            x=rf["funcao"], y=rf["valor"],
            marker_color=COR["funcao"],
            text=[formatar_moeda(v) for v in rf["valor"]], textposition="outside",
            hoverinfo="skip",
        ))
        fig5.update_layout(**_base_layout(
            height=280,
            yaxis=dict(showticklabels=False, showgrid=False, fixedrange=True),
            xaxis=dict(showgrid=False, fixedrange=True),
        ))
        st.plotly_chart(fig5, **OPC)

    # ── Exportacao ────────────────────────────────────────────────────────
    st.divider()
    df_exp = df_f.copy()
    df_exp["data"] = pd.to_datetime(df_exp["data"]).dt.strftime("%d/%m/%Y")
    colx, _ = st.columns([1, 4])
    with colx:
        st.download_button("📥 Exportar CSV", gerar_csv(df_exp),
                           "dashboard.csv", "text/csv", use_container_width=True)
