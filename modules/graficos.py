import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.repository import carregar_lancamentos, carregar_cadastros
from utils.helpers import formatar_moeda, gerar_csv, slug_da_sessao

T = "plotly_white"
COR = {"Entrada": "#1D9E75", "Saida": "#D85A30", "saldo": "#185FA5",
       "dizimo": "#185FA5", "despesa": "#D85A30", "funcao": "#534AB7"}


def _base_layout(**kw):
    return dict(template=T, margin=dict(t=10, b=0, l=0, r=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", **kw)


def render():
    slug = slug_da_sessao()
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

    if "funcao" not in df_cad.columns: df_cad["funcao"] = ""
    df_cad["funcao"] = df_cad["funcao"].fillna("").astype(str)
    df_cad["id_cadastro"] = pd.to_numeric(df_cad["id_cadastro"], errors="coerce")

    dv = df["data"].dropna()
    d_ini = st.date_input("De", value=dv.min().date() if not dv.empty else datetime.date.today(), format="DD/MM/YYYY", key="db_ini")
    d_fim = st.date_input("Ate", value=dv.max().date() if not dv.empty else datetime.date.today(), format="DD/MM/YYYY", key="db_fim")

    if d_ini > d_fim:
        st.error("Data inicial maior que data final.")
        return

    df_f = df[(df["data"] >= pd.Timestamp(d_ini)) & (df["data"] <= pd.Timestamp(d_fim))].copy()
    if df_f.empty:
        st.info("Sem lancamentos no periodo.")
        return

    ent = df_f[df_f["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    sai = df_f[df_f["tipo"].str.upper() == "SAIDA"]["valor"].sum()
    sal = ent - sai

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Entradas",    formatar_moeda(ent))
    k2.metric("Saidas",      formatar_moeda(sai))
    k3.metric("Saldo",       formatar_moeda(sal), delta=formatar_moeda(sal))
    k4.metric("Lancamentos", str(len(df_f)))

    st.divider()
    OPC = dict(use_container_width=True, config={"displayModeBar": False})

    st.caption("Evolucao mensal")
    res = df_f.groupby(["mes", "mes_label", "tipo"], as_index=False)["valor"].sum().sort_values("mes")
    meses = sorted(res["mes"].unique())
    labels = [res[res["mes"] == m]["mes_label"].iloc[0] for m in meses]
    def s(t): r = res[res["tipo"].str.upper() == t.upper()].set_index("mes"); return [float(r.loc[m,"valor"]) if m in r.index else 0.0 for m in meses]
    e_vals, s_vals = s("Entrada"), s("Saida")
    sal_vals = [e-s for e,s in zip(e_vals, s_vals)]
    fig1 = go.Figure([
        go.Bar(name="Entradas", x=labels, y=e_vals, marker_color=COR["Entrada"], text=[formatar_moeda(v) for v in e_vals], textposition="outside", textfont_size=10),
        go.Bar(name="Saidas",   x=labels, y=s_vals, marker_color=COR["Saida"],   text=[formatar_moeda(v) for v in s_vals], textposition="outside", textfont_size=10),
        go.Scatter(name="Saldo", x=labels, y=sal_vals, mode="lines+markers", line=dict(color=COR["saldo"], width=2, dash="dot"), marker=dict(size=5)),
    ])
    fig1.update_layout(**_base_layout(barmode="group", height=280, legend=dict(orientation="h", y=1.1, x=0)))
    st.plotly_chart(fig1, **OPC)

    c1, c2 = st.columns(2)

    with c1:
        st.caption("Distribuicao das entradas")
        ent_cat = df_f[df_f["tipo"].str.upper() == "ENTRADA"].groupby("categoria", as_index=False)["valor"].sum()
        if ent_cat.empty:
            st.info("Sem entradas.")
        else:
            fig2 = go.Figure(go.Pie(labels=ent_cat["categoria"], values=ent_cat["valor"], hole=0.5,
                                    textinfo="percent+label", textfont_size=12,
                                    hovertemplate="%{label}: %{customdata}<extra></extra>",
                                    customdata=[formatar_moeda(v) for v in ent_cat["valor"]]))
            fig2.update_layout(**_base_layout(showlegend=False, height=260, margin=dict(t=10,b=10,l=10,r=10)))
            st.plotly_chart(fig2, **OPC)

    with c2:
        st.caption("Dizimos por membro — top 8")
        diz = df_f[(df_f["categoria"].str.upper() == "DIZIMO") & (df_f["tipo_cadastro"].str.upper() == "MEMBRO")]
        if diz.empty:
            st.info("Sem dizimos.")
        else:
            d = diz.groupby("nome_cadastro", as_index=False)["valor"].sum().sort_values("valor", ascending=False).head(8)
            pares = sorted(zip(d["valor"], d["nome_cadastro"]))
            fig3 = go.Figure(go.Bar(x=[p[0] for p in pares], y=[p[1] for p in pares], orientation="h",
                                    marker_color=COR["dizimo"], text=[formatar_moeda(p[0]) for p in pares], textposition="outside"))
            fig3.update_layout(**_base_layout(height=max(200, len(d)*44),
                                              xaxis=dict(showticklabels=False, showgrid=False),
                                              yaxis=dict(showgrid=False)))
            st.plotly_chart(fig3, **OPC)

    c3, c4 = st.columns(2)

    with c3:
        st.caption("Top 8 despesas")
        desp = df_f[df_f["categoria"].str.upper() == "DESPESA"]
        if desp.empty:
            st.info("Sem despesas.")
        else:
            d2 = desp.groupby("descricao", as_index=False)["valor"].sum().sort_values("valor", ascending=False).head(8)
            pares = sorted(zip(d2["valor"], d2["descricao"]))
            fig4 = go.Figure(go.Bar(x=[p[0] for p in pares], y=[p[1] for p in pares], orientation="h",
                                    marker_color=COR["despesa"], text=[formatar_moeda(p[0]) for p in pares], textposition="outside"))
            fig4.update_layout(**_base_layout(height=max(200, len(d2)*44),
                                              xaxis=dict(showticklabels=False, showgrid=False),
                                              yaxis=dict(showgrid=False)))
            st.plotly_chart(fig4, **OPC)

    with c4:
        st.caption("Entradas por funcao")
        ent_m = df_f[(df_f["tipo"].str.upper() == "ENTRADA") & (df_f["tipo_cadastro"].str.upper() == "MEMBRO")].copy()
        if ent_m.empty:
            st.info("Sem entradas de membros.")
        else:
            mg = ent_m.merge(df_cad[["id_cadastro", "funcao"]], on="id_cadastro", how="left")
            mg["funcao"] = mg["funcao"].replace("", pd.NA).fillna("Sem funcao")
            rf = mg.groupby("funcao", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
            fig5 = go.Figure(go.Bar(x=rf["funcao"], y=rf["valor"], marker_color=COR["funcao"],
                                    text=[formatar_moeda(v) for v in rf["valor"]], textposition="outside"))
            fig5.update_layout(**_base_layout(height=260, yaxis=dict(showticklabels=False, showgrid=False), xaxis=dict(showgrid=False)))
            st.plotly_chart(fig5, **OPC)

    st.divider()
    df_exp = df_f.copy()
    df_exp["data"] = pd.to_datetime(df_exp["data"]).dt.strftime("%d/%m/%Y")
    col1, col2, _ = st.columns([1,1,4])
    with col1:
        st.download_button("CSV completo", gerar_csv(df_exp), "dashboard.csv", "text/csv")
