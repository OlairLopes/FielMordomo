"""
Dashboard Geral - Consolidacao de todas as congregacoes.

Acessivel apenas via Painel Admin, aba "7. Dashboard Geral".
Soma e apresenta dados de todas as igrejas cadastradas com filtros
de periodo e selecao multipla de igrejas.
"""

import datetime
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from data.repository import (
    listar_igrejas,
    carregar_cadastros,
    carregar_lancamentos,
)
from utils.helpers import formatar_moeda


# ─── Paleta de cores (mesmo padrao do modules/graficos.py) ──────────
COR = {
    "bg": "#0F172A",
    "card": "#1E293B",
    "border": "#334155",
    "text": "#F1F5F9",
    "muted": "#94A3B8",
    "muted2": "#64748B",
    "verde": "#10B981",
    "vermelho": "#EF4444",
    "azul": "#3B82F6",
    "amarelo": "#F59E0B",
    "roxo": "#A855F7",
    "rosa": "#EC4899",
    "ciano": "#06B6D4",
}


# ═══════════════════════════════════════════════════════════════════════
# Helpers de renderizacao HTML
# ═══════════════════════════════════════════════════════════════════════

def _kpi_card(titulo, valor, sub="", cor_valor=None, cor_borda=None, icone=""):
    """Renderiza um card KPI no estilo do dashboard."""
    if cor_valor is None:
        cor_valor = COR["text"]

    borda_left = (
        f"border-left:3px solid {cor_borda};" if cor_borda else ""
    )

    icone_html = f"{icone} " if icone else ""

    return (
        f'<div style="background:{COR["card"]};border:1px solid {COR["border"]};'
        f'border-radius:8px;padding:14px 16px;{borda_left}margin-bottom:8px;">'
        f'<div style="font-size:11px;color:{COR["muted"]};letter-spacing:0.05em;'
        f'text-transform:uppercase;margin-bottom:6px;">{icone_html}{titulo}</div>'
        f'<div style="font-size:22px;font-weight:500;color:{cor_valor};">{valor}</div>'
        f'<div style="font-size:11px;color:{COR["muted2"]};margin-top:2px;">{sub}</div>'
        f'</div>'
    )


def _render_ranking(df, coluna, label_singular, cor):
    """Renderiza ranking horizontal com barras coloridas."""
    if df.empty or coluna not in df.columns:
        st.info(f"Sem dados para ranking de {label_singular}.")
        return

    df_sort = df.sort_values(coluna, ascending=False).reset_index(drop=True)

    # Filtra apenas linhas com valor > 0
    df_sort = df_sort[df_sort[coluna] > 0]

    if df_sort.empty:
        st.info(f"Sem dados para ranking de {label_singular}.")
        return

    max_val = df_sort[coluna].max()
    total = df_sort[coluna].sum()

    medalhas = ['🥇', '🥈', '🥉']

    for i, row in df_sort.iterrows():
        valor = row[coluna]
        nome = row['Igreja']
        pct = (valor / total * 100) if total > 0 else 0
        largura = (valor / max_val * 100) if max_val > 0 else 0

        pos = medalhas[i] if i < 3 else f'{i+1}º'

        # Formata valor de acordo com a coluna
        if coluna in ['Entradas', 'Saidas', 'Saldo']:
            valor_fmt = formatar_moeda(valor)
        else:
            valor_fmt = str(int(valor))

        st.markdown(
            f'<div style="margin-bottom:10px;">'
            f'<div style="display:flex;justify-content:space-between;'
            f'font-size:13px;margin-bottom:4px;color:{COR["text"]};">'
            f'<span><span style="color:{cor};font-weight:500;">{pos}</span> {nome}</span>'
            f'<span style="color:{cor};font-weight:500;">'
            f'{valor_fmt} ({pct:.1f}%)</span>'
            f'</div>'
            f'<div style="background:{COR["bg"]};border-radius:4px;height:8px;overflow:hidden;">'
            f'<div style="background:{cor};height:100%;width:{largura:.1f}%;"></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _render_insight(tipo, icone, texto, cor_borda):
    """Renderiza um card de insight/alerta."""
    st.markdown(
        f'<div style="background:{COR["card"]};border-left:3px solid {cor_borda};'
        f'padding:10px 14px;border-radius:4px;margin-bottom:8px;font-size:13px;">'
        f'<span style="color:{cor_borda};font-weight:500;">{icone} {tipo}:</span> '
        f'<span style="color:{COR["text"]};">{texto}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════
# Geracao de insights automaticos
# ═══════════════════════════════════════════════════════════════════════

def _gerar_insights(df_tabela, df_lanc_total, info_igrejas):
    """Gera lista de insights automaticos baseados nos dados consolidados."""
    insights = []

    if df_tabela.empty or len(df_tabela) <= 1:
        return insights

    # Remove linha de TOTAL (ultima)
    df_ig = df_tabela.iloc[:-1].copy() if df_tabela.iloc[-1]["Igreja"] == "— TOTAL —" else df_tabela.copy()

    if df_ig.empty:
        return insights

    # 1. Destaque - igreja com maior arrecadacao
    if 'Entradas' in df_ig.columns and df_ig['Entradas'].max() > 0:
        maior = df_ig.loc[df_ig['Entradas'].idxmax()]
        insights.append({
            'tipo': 'Destaque',
            'icone': '🌟',
            'texto': (
                f"{maior['Igreja']} liderou em arrecadacao com "
                f"{formatar_moeda(maior['Entradas'])} no periodo."
            ),
            'cor': COR["verde"],
        })

    # 2. Atencao - igrejas com baixo % de dizimistas
    if 'Dizimistas' in df_ig.columns and 'Membros' in df_ig.columns:
        df_temp = df_ig.copy()
        df_temp['pct_diz'] = (
            df_temp['Dizimistas'] / df_temp['Membros'].replace(0, 1) * 100
        )
        # Apenas igrejas com pelo menos 1 membro
        df_temp = df_temp[df_temp['Membros'] > 0]

        if not df_temp.empty:
            media_geral = df_temp['pct_diz'].mean()
            baixos = df_temp[df_temp['pct_diz'] < (media_geral - 10)]

            for _, row in baixos.iterrows():
                insights.append({
                    'tipo': 'Atencao',
                    'icone': '⚠️',
                    'texto': (
                        f"{row['Igreja']} tem apenas {row['pct_diz']:.1f}% de "
                        f"dizimistas (media geral: {media_geral:.1f}%)."
                    ),
                    'cor': COR["amarelo"],
                })

    # 3. Info - igrejas inativas
    if not df_lanc_total.empty and '_slug' in df_lanc_total.columns:
        hoje = pd.Timestamp(datetime.date.today())

        for info in info_igrejas:
            slug = info['slug']
            df_ig_lanc = df_lanc_total[df_lanc_total['_slug'] == slug]

            if df_ig_lanc.empty:
                insights.append({
                    'tipo': 'Info',
                    'icone': 'ℹ️',
                    'texto': (
                        f"{info['nome']} nao possui nenhum lancamento "
                        f"registrado."
                    ),
                    'cor': COR["azul"],
                })
            else:
                ultima_data = df_ig_lanc['data'].max()
                if pd.notna(ultima_data):
                    dias_inativo = (hoje - ultima_data).days
                    if dias_inativo > 7:
                        insights.append({
                            'tipo': 'Info',
                            'icone': 'ℹ️',
                            'texto': (
                                f"{info['nome']} nao registra lancamentos "
                                f"ha {dias_inativo} dias."
                            ),
                            'cor': COR["azul"],
                        })

    # 4. Deficit - igrejas com saldo negativo
    if 'Saldo' in df_ig.columns:
        deficits = df_ig[df_ig['Saldo'] < 0]
        for _, row in deficits.iterrows():
            insights.append({
                'tipo': 'Deficit',
                'icone': '🔴',
                'texto': (
                    f"{row['Igreja']} apresenta saldo negativo: "
                    f"{formatar_moeda(row['Saldo'])}."
                ),
                'cor': COR["vermelho"],
            })

    return insights[:8]  # Maximo 8 insights


# ═══════════════════════════════════════════════════════════════════════
# Funcao principal - renderiza o dashboard completo
# ═══════════════════════════════════════════════════════════════════════

def render_dashboard_geral():
    """Renderiza o Dashboard Geral consolidado de todas as igrejas."""

    st.subheader("📊 Dashboard Geral — Todas as Congregacoes")
    st.caption(
        "Visao consolidada de todas as igrejas cadastradas no sistema. "
        "Use os filtros abaixo para personalizar a analise."
    )

    # ─── Carrega lista de igrejas ───────────────────────────────────
    df_igrejas = listar_igrejas()

    if df_igrejas.empty:
        st.info("Nenhuma igreja cadastrada no sistema.")
        return

    # Filtra apenas ativas (se a coluna existir)
    if "ativa" in df_igrejas.columns:
        igrejas_ativas = df_igrejas[df_igrejas["ativa"] == 1].copy()
    else:
        igrejas_ativas = df_igrejas.copy()

    if igrejas_ativas.empty:
        st.warning("Nenhuma igreja ativa.")
        return

    # ─── FILTROS ────────────────────────────────────────────────────
    st.markdown("##### 🔍 Filtros")

    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])

    with col_f1:
        data_de = st.date_input(
            "De",
            value=datetime.date.today().replace(day=1),
            format="DD/MM/YYYY",
            key="dg_data_de",
        )

    with col_f2:
        data_ate = st.date_input(
            "Ate",
            value=datetime.date.today(),
            format="DD/MM/YYYY",
            key="dg_data_ate",
        )

    if data_de > data_ate:
        st.error("Data inicial deve ser anterior a data final.")
        return

    with col_f3:
        # Cria mapa nome -> slug para o multi-select
        opcoes_igrejas = {
            f"{row['nome']}": row['slug']
            for _, row in igrejas_ativas.iterrows()
        }

        nomes_selecionados = st.multiselect(
            f"Igrejas ({len(opcoes_igrejas)} disponiveis)",
            options=list(opcoes_igrejas.keys()),
            default=list(opcoes_igrejas.keys()),
            key="dg_igrejas",
        )

    slugs_selecionados = [opcoes_igrejas[n] for n in nomes_selecionados]

    if not slugs_selecionados:
        st.warning("Selecione ao menos uma igreja para visualizar os dados.")
        return

    # ─── CARREGA E CONSOLIDA DADOS ──────────────────────────────────
    todos_lanc = []
    todos_cad = []
    info_igrejas = []

    with st.spinner("Carregando dados das igrejas..."):
        for _, row in igrejas_ativas.iterrows():
            slug = row['slug']
            if slug not in slugs_selecionados:
                continue

            nome_igreja = row['nome']
            plano = str(row.get('plano', 'basico')).capitalize()

            # Cadastros
            try:
                df_c = carregar_cadastros(slug)
                if not df_c.empty:
                    df_c = df_c.copy()
                    df_c['_slug'] = slug
                    df_c['_igreja'] = nome_igreja
                    todos_cad.append(df_c)
            except Exception:
                pass

            # Lancamentos
            try:
                df_l = carregar_lancamentos(slug)
                if not df_l.empty:
                    df_l = df_l.copy()
                    df_l['_slug'] = slug
                    df_l['_igreja'] = nome_igreja
                    df_l['data'] = pd.to_datetime(
                        df_l['data'], errors='coerce'
                    )
                    todos_lanc.append(df_l)
            except Exception:
                pass

            info_igrejas.append({
                'slug': slug,
                'nome': nome_igreja,
                'plano': plano,
            })

    df_cad_total = (
        pd.concat(todos_cad, ignore_index=True)
        if todos_cad else pd.DataFrame()
    )
    df_lanc_total = (
        pd.concat(todos_lanc, ignore_index=True)
        if todos_lanc else pd.DataFrame()
    )

    # Filtra lancamentos pelo periodo
    df_lanc_periodo = df_lanc_total.copy()
    if not df_lanc_periodo.empty and 'data' in df_lanc_periodo.columns:
        mask = (
            (df_lanc_periodo['data'].dt.date >= data_de) &
            (df_lanc_periodo['data'].dt.date <= data_ate)
        )
        df_lanc_periodo = df_lanc_periodo[mask]

    # Periodo anterior (mesma duracao para comparacao)
    dias_periodo = (data_ate - data_de).days + 1
    data_de_ant = data_de - datetime.timedelta(days=dias_periodo)
    data_ate_ant = data_de - datetime.timedelta(days=1)

    df_lanc_ant = df_lanc_total.copy()
    if not df_lanc_ant.empty and 'data' in df_lanc_ant.columns:
        mask_ant = (
            (df_lanc_ant['data'].dt.date >= data_de_ant) &
            (df_lanc_ant['data'].dt.date <= data_ate_ant)
        )
        df_lanc_ant = df_lanc_ant[mask_ant]

    # ─── CALCULA KPIs ───────────────────────────────────────────────
    total_igrejas_sel = len(slugs_selecionados)
    total_igrejas_disp = len(igrejas_ativas)

    # Membros ativos
    if not df_cad_total.empty and 'tipo_cadastro' in df_cad_total.columns:
        membros_df = df_cad_total[
            df_cad_total['tipo_cadastro'].astype(str).str.upper() == 'MEMBRO'
        ]
        if 'ativo' in membros_df.columns:
            membros_df = membros_df[membros_df['ativo'] == 1]
        total_membros = len(membros_df)
    else:
        total_membros = 0

    # Entradas, saidas, saldo
    if not df_lanc_periodo.empty:
        entradas_df = df_lanc_periodo[df_lanc_periodo['tipo'] == 'Entrada']
        saidas_df = df_lanc_periodo[df_lanc_periodo['tipo'] == 'Saida']

        total_entradas = float(entradas_df['valor'].sum())
        total_saidas = float(saidas_df['valor'].sum())
        saldo = total_entradas - total_saidas

        # Dizimistas unicos (membros que dizimaram no periodo)
        dizimos_df = entradas_df[entradas_df['categoria'] == 'Dizimo']
        if not dizimos_df.empty and 'id_cadastro' in dizimos_df.columns:
            dizimistas_unicos = (
                dizimos_df['id_cadastro'].dropna().unique()
            )
            total_dizimistas = len(dizimistas_unicos)
        else:
            total_dizimistas = 0
    else:
        total_entradas = 0
        total_saidas = 0
        saldo = 0
        total_dizimistas = 0

    # Comparacao com periodo anterior
    if not df_lanc_ant.empty:
        ent_ant = float(df_lanc_ant[df_lanc_ant['tipo'] == 'Entrada']['valor'].sum())
        sai_ant = float(df_lanc_ant[df_lanc_ant['tipo'] == 'Saida']['valor'].sum())
        var_ent = ((total_entradas - ent_ant) / ent_ant * 100) if ent_ant > 0 else 0
        var_sai = ((total_saidas - sai_ant) / sai_ant * 100) if sai_ant > 0 else 0
    else:
        var_ent = 0
        var_sai = 0

    pct_dizimistas = (
        (total_dizimistas / total_membros * 100) if total_membros > 0 else 0
    )

    # ─── RENDERIZA KPIs (6 cards em 2 linhas) ──────────────────────
    st.markdown("---")
    st.markdown("##### 📊 KPIs do periodo")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(_kpi_card(
            titulo="Igrejas ativas",
            valor=str(total_igrejas_sel),
            sub=f"de {total_igrejas_disp} cadastradas",
            icone="🏛️",
        ), unsafe_allow_html=True)

    with c2:
        st.markdown(_kpi_card(
            titulo="Membros ativos",
            valor=str(total_membros),
            sub=f"em {total_igrejas_sel} igreja(s)",
            icone="👥",
        ), unsafe_allow_html=True)

    with c3:
        st.markdown(_kpi_card(
            titulo="Dizimistas unicos",
            valor=str(total_dizimistas),
            sub=f"{pct_dizimistas:.1f}% dos membros",
            icone="🤝",
        ), unsafe_allow_html=True)

    c4, c5, c6 = st.columns(3)

    with c4:
        seta_e = "↑" if var_ent >= 0 else "↓"
        cor_var_e = COR["verde"] if var_ent >= 0 else COR["vermelho"]
        sub_ent = (
            f'<span style="color:{cor_var_e}">{seta_e} {abs(var_ent):.1f}% '
            f'vs periodo anterior</span>'
        )
        st.markdown(_kpi_card(
            titulo="Entradas no periodo",
            valor=formatar_moeda(total_entradas),
            sub=sub_ent,
            cor_valor=COR["verde"],
            cor_borda=COR["verde"],
            icone="⬇️",
        ), unsafe_allow_html=True)

    with c5:
        seta_s = "↑" if var_sai >= 0 else "↓"
        # Para saidas, aumento e ruim
        cor_var_s = COR["vermelho"] if var_sai > 0 else COR["verde"]
        sub_sai = (
            f'<span style="color:{cor_var_s}">{seta_s} {abs(var_sai):.1f}% '
            f'vs periodo anterior</span>'
        )
        st.markdown(_kpi_card(
            titulo="Saidas no periodo",
            valor=formatar_moeda(total_saidas),
            sub=sub_sai,
            cor_valor=COR["vermelho"],
            cor_borda=COR["vermelho"],
            icone="⬆️",
        ), unsafe_allow_html=True)

    with c6:
        if saldo >= 0:
            status = "Superavit"
            cor_saldo = COR["azul"]
            seta_saldo = "↑"
        else:
            status = "Deficit"
            cor_saldo = COR["vermelho"]
            seta_saldo = "↓"

        sub_saldo = (
            f'<span style="color:{cor_saldo}">{seta_saldo} {status}</span>'
        )
        st.markdown(_kpi_card(
            titulo="Saldo consolidado",
            valor=formatar_moeda(saldo),
            sub=sub_saldo,
            cor_valor=cor_saldo,
            cor_borda=cor_saldo,
            icone="💰",
        ), unsafe_allow_html=True)

    # ─── TABELA DETALHADA POR IGREJA ────────────────────────────────
    st.markdown("---")
    st.markdown("##### 📋 Detalhamento por Igreja")

    linhas_tabela = []
    for info in info_igrejas:
        slug = info['slug']

        # Lancamentos da igreja no periodo
        df_l_ig = (
            df_lanc_periodo[df_lanc_periodo['_slug'] == slug]
            if not df_lanc_periodo.empty else pd.DataFrame()
        )

        # Cadastros da igreja
        df_c_ig = (
            df_cad_total[df_cad_total['_slug'] == slug]
            if not df_cad_total.empty else pd.DataFrame()
        )

        # Membros ativos da igreja
        if not df_c_ig.empty and 'tipo_cadastro' in df_c_ig.columns:
            membros_ig_df = df_c_ig[
                df_c_ig['tipo_cadastro'].astype(str).str.upper() == 'MEMBRO'
            ]
            if 'ativo' in membros_ig_df.columns:
                membros_ig_df = membros_ig_df[membros_ig_df['ativo'] == 1]
            membros_ig = len(membros_ig_df)
        else:
            membros_ig = 0

        # Entradas e saidas
        if not df_l_ig.empty:
            ent_ig = float(df_l_ig[df_l_ig['tipo'] == 'Entrada']['valor'].sum())
            sai_ig = float(df_l_ig[df_l_ig['tipo'] == 'Saida']['valor'].sum())
            saldo_ig = ent_ig - sai_ig

            # Dizimistas unicos da igreja
            diz_df_ig = df_l_ig[
                (df_l_ig['tipo'] == 'Entrada') &
                (df_l_ig['categoria'] == 'Dizimo')
            ]
            if not diz_df_ig.empty and 'id_cadastro' in diz_df_ig.columns:
                dizimistas_ig = len(
                    diz_df_ig['id_cadastro'].dropna().unique()
                )
            else:
                dizimistas_ig = 0
        else:
            ent_ig = 0
            sai_ig = 0
            saldo_ig = 0
            dizimistas_ig = 0

        linhas_tabela.append({
            'Igreja': info['nome'],
            'Plano': info['plano'],
            'Membros': membros_ig,
            'Entradas': ent_ig,
            'Saidas': sai_ig,
            'Saldo': saldo_ig,
            'Dizimistas': dizimistas_ig,
        })

    df_tabela = pd.DataFrame(linhas_tabela)

    # Adiciona linha TOTAL
    if not df_tabela.empty:
        total_row = pd.DataFrame([{
            'Igreja': '— TOTAL —',
            'Plano': '—',
            'Membros': df_tabela['Membros'].sum(),
            'Entradas': df_tabela['Entradas'].sum(),
            'Saidas': df_tabela['Saidas'].sum(),
            'Saldo': df_tabela['Saldo'].sum(),
            'Dizimistas': df_tabela['Dizimistas'].sum(),
        }])
        df_tabela_completo = pd.concat([df_tabela, total_row], ignore_index=True)
    else:
        df_tabela_completo = df_tabela

    # Versao formatada para exibicao
    df_tabela_display = df_tabela_completo.copy()
    df_tabela_display['Entradas'] = df_tabela_display['Entradas'].apply(
        formatar_moeda
    )
    df_tabela_display['Saidas'] = df_tabela_display['Saidas'].apply(
        formatar_moeda
    )
    df_tabela_display['Saldo'] = df_tabela_display['Saldo'].apply(
        formatar_moeda
    )

    st.dataframe(
        df_tabela_display,
        use_container_width=True,
        hide_index=True,
    )

    # Botao de exportacao CSV
    csv_data = df_tabela_completo.to_csv(
        index=False, encoding='utf-8-sig', sep=';'
    )
    st.download_button(
        "📥 Exportar CSV consolidado",
        data=csv_data,
        file_name=(
            f"dashboard_geral_"
            f"{data_de.strftime('%Y%m%d')}_"
            f"{data_ate.strftime('%Y%m%d')}.csv"
        ),
        mime="text/csv",
        key="dg_export_csv",
    )

    # ─── RANKINGS (3 abas) ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("##### 🏆 Rankings")

    rank_tab1, rank_tab2, rank_tab3 = st.tabs([
        "💰 Arrecadacao",
        "👥 Membros",
        "🤝 Dizimistas",
    ])

    with rank_tab1:
        st.caption("Igrejas ordenadas por valor total de entradas no periodo.")
        _render_ranking(df_tabela, 'Entradas', 'arrecadacao', COR["verde"])

    with rank_tab2:
        st.caption("Igrejas ordenadas por numero de membros ativos.")
        _render_ranking(df_tabela, 'Membros', 'membros', COR["azul"])

    with rank_tab3:
        st.caption(
            "Igrejas ordenadas por numero de dizimistas unicos no periodo."
        )
        _render_ranking(df_tabela, 'Dizimistas', 'dizimistas', COR["roxo"])

    # ─── DONUTS: Categoria e Subcategoria ──────────────────────────
    st.markdown("---")
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.markdown("##### 🥧 Entradas por Categoria")

        if not df_lanc_periodo.empty:
            df_entradas = df_lanc_periodo[df_lanc_periodo['tipo'] == 'Entrada']
            if not df_entradas.empty:
                grupo_cat = (
                    df_entradas.groupby('categoria')['valor']
                    .sum().reset_index()
                    .sort_values('valor', ascending=False)
                )

                cores_cat = [
                    COR["verde"], COR["azul"], COR["amarelo"],
                    COR["roxo"], COR["rosa"], COR["ciano"],
                ]

                fig_ent = go.Figure(go.Pie(
                    labels=grupo_cat['categoria'],
                    values=grupo_cat['valor'],
                    hole=0.5,
                    marker=dict(colors=cores_cat[:len(grupo_cat)]),
                    textinfo='percent',
                    textfont=dict(color='white', size=12),
                    hovertemplate=(
                        '%{label}<br>%{value:,.2f}<br>%{percent}<extra></extra>'
                    ),
                ))
                fig_ent.update_layout(
                    plot_bgcolor=COR["card"],
                    paper_bgcolor=COR["card"],
                    font=dict(color=COR["text"]),
                    height=320,
                    margin=dict(l=10, r=10, t=20, b=10),
                    legend=dict(
                        orientation="v",
                        x=1.05, y=0.5,
                        font=dict(color=COR["text"], size=11),
                    ),
                )
                st.plotly_chart(fig_ent, use_container_width=True)
            else:
                st.info("Sem entradas no periodo.")
        else:
            st.info("Sem dados.")

    with col_g2:
        st.markdown("##### 🥧 Despesas por Subcategoria")

        if not df_lanc_periodo.empty:
            df_saidas = df_lanc_periodo[df_lanc_periodo['tipo'] == 'Saida']

            if not df_saidas.empty and 'subcategoria' in df_saidas.columns:
                df_saidas_sub = df_saidas[
                    df_saidas['subcategoria'].notna() &
                    (df_saidas['subcategoria'].astype(str).str.strip() != '')
                ]

                if not df_saidas_sub.empty:
                    grupo_sub = (
                        df_saidas_sub.groupby('subcategoria')['valor']
                        .sum().reset_index()
                        .sort_values('valor', ascending=False)
                        .head(8)
                    )

                    cores_sub = [
                        COR["vermelho"], COR["amarelo"], COR["roxo"],
                        COR["azul"], COR["rosa"], COR["ciano"],
                        COR["verde"], "#FB923C",
                    ]

                    fig_sai = go.Figure(go.Pie(
                        labels=grupo_sub['subcategoria'],
                        values=grupo_sub['valor'],
                        hole=0.5,
                        marker=dict(colors=cores_sub[:len(grupo_sub)]),
                        textinfo='percent',
                        textfont=dict(color='white', size=12),
                        hovertemplate=(
                            '%{label}<br>%{value:,.2f}<br>%{percent}'
                            '<extra></extra>'
                        ),
                    ))
                    fig_sai.update_layout(
                        plot_bgcolor=COR["card"],
                        paper_bgcolor=COR["card"],
                        font=dict(color=COR["text"]),
                        height=320,
                        margin=dict(l=10, r=10, t=20, b=10),
                        legend=dict(
                            orientation="v",
                            x=1.05, y=0.5,
                            font=dict(color=COR["text"], size=11),
                        ),
                    )
                    st.plotly_chart(fig_sai, use_container_width=True)
                else:
                    st.info("Sem despesas com subcategoria informada.")
            else:
                st.info("Sem saidas no periodo.")
        else:
            st.info("Sem dados.")

    # ─── EVOLUCAO CONSOLIDADA (ultimos 6 meses) ────────────────────
    st.markdown("---")
    st.markdown("##### 📈 Evolucao Consolidada — Ultimos 6 meses")

    hoje = datetime.date.today()
    inicio_6m = (hoje.replace(day=1) - datetime.timedelta(days=180))
    inicio_6m = inicio_6m.replace(day=1)

    if not df_lanc_total.empty and 'data' in df_lanc_total.columns:
        df_6m = df_lanc_total[
            df_lanc_total['data'].dt.date >= inicio_6m
        ].copy()

        if not df_6m.empty:
            df_6m['ano_mes'] = df_6m['data'].dt.to_period('M').astype(str)

            ent_mes = (
                df_6m[df_6m['tipo'] == 'Entrada']
                .groupby('ano_mes')['valor'].sum().reset_index()
            )
            ent_mes.columns = ['ano_mes', 'entradas']

            sai_mes = (
                df_6m[df_6m['tipo'] == 'Saida']
                .groupby('ano_mes')['valor'].sum().reset_index()
            )
            sai_mes.columns = ['ano_mes', 'saidas']

            df_serie = pd.merge(
                ent_mes, sai_mes, on='ano_mes', how='outer'
            ).fillna(0).sort_values('ano_mes')

            if not df_serie.empty:
                fig_evol = go.Figure()

                # Entradas (area preenchida)
                fig_evol.add_trace(go.Scatter(
                    x=df_serie['ano_mes'],
                    y=df_serie['entradas'],
                    mode='lines+markers',
                    name='Entradas',
                    line=dict(color=COR["verde"], width=3),
                    marker=dict(size=8, color=COR["verde"]),
                    fill='tozeroy',
                    fillcolor='rgba(16, 185, 129, 0.15)',
                    hovertemplate='%{x}<br>Entradas: R$ %{y:,.2f}<extra></extra>',
                ))

                # Saidas (linha simples)
                fig_evol.add_trace(go.Scatter(
                    x=df_serie['ano_mes'],
                    y=df_serie['saidas'],
                    mode='lines+markers',
                    name='Saidas',
                    line=dict(color=COR["vermelho"], width=2),
                    marker=dict(size=6, color=COR["vermelho"]),
                    hovertemplate='%{x}<br>Saidas: R$ %{y:,.2f}<extra></extra>',
                ))

                fig_evol.update_layout(
                    plot_bgcolor=COR["card"],
                    paper_bgcolor=COR["card"],
                    font=dict(color=COR["text"]),
                    height=350,
                    margin=dict(l=60, r=20, t=20, b=60),
                    xaxis=dict(
                        gridcolor=COR["border"],
                        color=COR["muted"],
                        title="",
                    ),
                    yaxis=dict(
                        gridcolor=COR["border"],
                        color=COR["muted"],
                        tickprefix="R$ ",
                        title="",
                    ),
                    legend=dict(
                        orientation="h",
                        y=-0.15, x=0.5,
                        xanchor='center',
                        font=dict(color=COR["text"]),
                    ),
                    hovermode='x unified',
                )
                st.plotly_chart(fig_evol, use_container_width=True)
            else:
                st.info("Sem dados nos ultimos 6 meses.")
        else:
            st.info("Sem dados nos ultimos 6 meses.")
    else:
        st.info("Sem dados de lancamentos.")

    # ─── INSIGHTS E ALERTAS AUTOMATICOS ────────────────────────────
    st.markdown("---")
    st.markdown("##### 💡 Insights e Alertas")

    insights = _gerar_insights(df_tabela_completo, df_lanc_total, info_igrejas)

    if insights:
        for insight in insights:
            _render_insight(
                tipo=insight['tipo'],
                icone=insight['icone'],
                texto=insight['texto'],
                cor_borda=insight['cor'],
            )
    else:
        st.info("Nenhum alerta relevante no momento.")

    # Rodape com info
    st.markdown("---")
    st.caption(
        f"📅 Periodo analisado: {data_de.strftime('%d/%m/%Y')} a "
        f"{data_ate.strftime('%d/%m/%Y')} ({dias_periodo} dias) | "
        f"🏛️ {total_igrejas_sel} de {total_igrejas_disp} igreja(s) selecionada(s)"
    )