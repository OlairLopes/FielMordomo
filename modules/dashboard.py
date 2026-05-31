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
