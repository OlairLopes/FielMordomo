"""
dashboard_geral.py — Painel geral do administrador do FielMordomo.

Este módulo foi criado para resolver o erro:
ModuleNotFoundError: No module named 'admin.dashboard_geral'

Local correto:
admin/dashboard_geral.py

Função principal:
render()

Também foram criados aliases para compatibilidade com diferentes imports:
render_dashboard_geral(), exibir_dashboard_geral(), dashboard_geral(),
renderizar(), renderizar_dashboard_geral(), aba_dashboard_geral().
"""

from __future__ import annotations

import datetime as _dt
import importlib
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import streamlit as st


AZUL = "#061B44"
AZUL_2 = "#0B3A66"
DOURADO = "#D4AF37"
VERDE = "#0F6E56"
VERMELHO = "#B91C1C"
CINZA = "#64748B"


# ─────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────

def _injetar_css() -> None:
    st.markdown(
        f"""
        <style>
            .adm-hero {{
                background: linear-gradient(135deg, {AZUL} 0%, {AZUL_2} 100%);
                color: white;
                padding: 26px 30px;
                border-radius: 18px;
                margin-bottom: 22px;
                box-shadow: 0 12px 30px rgba(6, 27, 68, 0.18);
            }}

            .adm-hero h1 {{
                color: white;
                margin: 0 0 8px 0;
                font-size: 1.8rem;
                font-weight: 800;
            }}

            .adm-hero p {{
                color: rgba(255,255,255,0.82);
                margin: 0;
                font-size: 0.98rem;
            }}

            .adm-card {{
                background: white;
                border: 1px solid rgba(6,27,68,0.08);
                border-radius: 16px;
                padding: 18px 20px;
                box-shadow: 0 8px 22px rgba(6,27,68,0.07);
                min-height: 112px;
            }}

            .adm-card-label {{
                color: {CINZA};
                font-size: 0.82rem;
                font-weight: 700;
                margin-bottom: 8px;
            }}

            .adm-card-value {{
                color: {AZUL};
                font-size: 1.65rem;
                font-weight: 850;
                line-height: 1.1;
            }}

            .adm-card-note {{
                color: {CINZA};
                font-size: 0.78rem;
                margin-top: 8px;
            }}

            .adm-section-title {{
                color: {AZUL};
                font-size: 1.15rem;
                font-weight: 800;
                margin: 22px 0 10px 0;
                padding-left: 10px;
                border-left: 4px solid {DOURADO};
            }}

            .adm-warn {{
                background: #FFF7ED;
                border: 1px solid #FED7AA;
                color: #9A3412;
                padding: 12px 14px;
                border-radius: 12px;
                margin: 12px 0;
                font-size: 0.92rem;
            }}

            .adm-ok {{
                background: #ECFDF5;
                border: 1px solid #BBF7D0;
                color: #166534;
                padding: 12px 14px;
                border-radius: 12px;
                margin: 12px 0;
                font-size: 0.92rem;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────

def _repo():
    try:
        return importlib.import_module("data.repository")
    except Exception:
        return None


def _safe_call(func, *args, default=None, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        return default


def _formatar_moeda(valor: Any) -> str:
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def _formatar_data(valor: Any) -> str:
    if valor is None or str(valor).strip() == "":
        return ""
    try:
        return pd.to_datetime(valor, errors="coerce").strftime("%d/%m/%Y")
    except Exception:
        return str(valor)


def _normalizar_texto(valor: Any) -> str:
    return str(valor or "").strip()


def _normalizar_plano(valor: Any) -> str:
    plano = _normalizar_texto(valor).lower()
    if not plano:
        return "basico"
    if plano in {"básico", "basic"}:
        return "basico"
    if plano in {"profissional", "professional"}:
        return "profissional"
    if plano in {"premium", "premiun"}:
        return "premium"
    return plano


def _normalizar_ativo(valor: Any) -> bool:
    txt = _normalizar_texto(valor).lower()
    if txt in {"0", "false", "falso", "nao", "não", "inativo", "bloqueado", "cancelado"}:
        return False
    if txt in {"1", "true", "verdadeiro", "sim", "ativo", "liberado"}:
        return True
    if isinstance(valor, bool):
        return valor
    return True


# ─────────────────────────────────────────────────────────────
# Coleta de dados
# ─────────────────────────────────────────────────────────────

def _listar_igrejas_raw() -> Any:
    """
    Tenta obter a lista de igrejas usando nomes comuns de funções do repository.py.
    Mantém o módulo resiliente mesmo quando o repository muda.
    """
    repo = _repo()
    if repo is None:
        return []

    candidatos = [
        "listar_igrejas",
        "carregar_igrejas",
        "obter_igrejas",
        "listar_tenants",
        "carregar_master",
        "carregar_cadastros_igrejas",
        "listar_clientes",
    ]

    for nome in candidatos:
        func = getattr(repo, nome, None)
        if callable(func):
            resultado = _safe_call(func, default=None)
            if resultado is not None:
                return resultado

    # Fallback: se existir uma função que retorna conexão/caminho master, não arriscamos
    # manipular schema desconhecido aqui. O objetivo principal é não quebrar o painel.
    return []


def _normalizar_igrejas(dados: Any) -> pd.DataFrame:
    """
    Aceita DataFrame, lista de dicts, dict com lista ou tuplas simples.
    Retorna sempre um DataFrame com colunas esperadas.
    """
    if isinstance(dados, pd.DataFrame):
        df = dados.copy()
    elif isinstance(dados, dict):
        # Ex.: {"igrejas": [...]} ou {"dados": [...]}
        lista = None
        for chave in ["igrejas", "dados", "items", "registros", "tenants"]:
            if chave in dados and isinstance(dados[chave], (list, tuple)):
                lista = dados[chave]
                break
        if lista is None:
            lista = [dados]
        df = pd.DataFrame(lista)
    elif isinstance(dados, (list, tuple)):
        df = pd.DataFrame(list(dados))
    else:
        df = pd.DataFrame()

    if df.empty:
        return pd.DataFrame(
            columns=[
                "slug",
                "nome",
                "plano",
                "ativo",
                "criado_em",
                "usuario",
                "email",
            ]
        )

    # Normaliza possíveis nomes de colunas.
    mapa = {
        "identificador": "slug",
        "id_igreja": "slug",
        "tenant": "slug",
        "tenant_id": "slug",
        "igreja": "nome",
        "nome_igreja": "nome",
        "razao_social": "nome",
        "status": "ativo",
        "situacao": "ativo",
        "data_criacao": "criado_em",
        "created_at": "criado_em",
        "criado": "criado_em",
        "login": "usuario",
        "admin": "usuario",
        "email_admin": "email",
    }

    df = df.rename(columns={c: mapa.get(c, c) for c in df.columns})

    for col in ["slug", "nome", "plano", "ativo", "criado_em", "usuario", "email"]:
        if col not in df.columns:
            df[col] = ""

    df["slug"] = df["slug"].map(_normalizar_texto)
    df["nome"] = df["nome"].map(_normalizar_texto)
    df["plano"] = df["plano"].map(_normalizar_plano)
    df["ativo"] = df["ativo"].map(_normalizar_ativo)
    df["criado_em"] = df["criado_em"].map(_formatar_data)
    df["usuario"] = df["usuario"].map(_normalizar_texto)
    df["email"] = df["email"].map(_normalizar_texto)

    # Se não houver nome, usa slug.
    df.loc[df["nome"] == "", "nome"] = df.loc[df["nome"] == "", "slug"]

    # Remove linhas totalmente vazias.
    df = df[(df["slug"] != "") | (df["nome"] != "")].copy()

    return df


def _carregar_igrejas() -> pd.DataFrame:
    return _normalizar_igrejas(_listar_igrejas_raw())


def _carregar_cadastros(slug: str) -> pd.DataFrame:
    repo = _repo()
    if repo is None:
        return pd.DataFrame()

    func = getattr(repo, "carregar_cadastros", None)
    if not callable(func):
        return pd.DataFrame()

    df = _safe_call(func, slug, default=pd.DataFrame())
    if isinstance(df, pd.DataFrame):
        return df.copy()
    return pd.DataFrame(df) if df is not None else pd.DataFrame()


def _carregar_lancamentos(slug: str) -> pd.DataFrame:
    repo = _repo()
    if repo is None:
        return pd.DataFrame()

    func = getattr(repo, "carregar_lancamentos", None)
    if not callable(func):
        return pd.DataFrame()

    df = _safe_call(func, slug, default=pd.DataFrame())
    if isinstance(df, pd.DataFrame):
        return df.copy()
    return pd.DataFrame(df) if df is not None else pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# Métricas
# ─────────────────────────────────────────────────────────────

def _metricas_por_igreja(df_igrejas: pd.DataFrame) -> pd.DataFrame:
    registros: List[Dict[str, Any]] = []

    for _, row in df_igrejas.iterrows():
        slug = _normalizar_texto(row.get("slug", ""))
        nome = _normalizar_texto(row.get("nome", "")) or slug
        plano = _normalizar_plano(row.get("plano", "basico"))
        ativo = bool(row.get("ativo", True))

        cad = _carregar_cadastros(slug) if slug else pd.DataFrame()
        lan = _carregar_lancamentos(slug) if slug else pd.DataFrame()

        qtd_cadastros = int(len(cad)) if isinstance(cad, pd.DataFrame) else 0

        qtd_membros = 0
        if isinstance(cad, pd.DataFrame) and not cad.empty and "tipo_cadastro" in cad.columns:
            tipo = cad["tipo_cadastro"].fillna("").astype(str).str.upper()
            qtd_membros = int((tipo == "MEMBRO").sum())
        elif qtd_cadastros:
            qtd_membros = qtd_cadastros

        entradas = 0.0
        saidas = 0.0
        entradas_mes = 0.0
        saidas_mes = 0.0
        qtd_lancamentos = 0

        if isinstance(lan, pd.DataFrame) and not lan.empty:
            qtd_lancamentos = int(len(lan))

            if "valor" in lan.columns:
                valores = pd.to_numeric(lan["valor"], errors="coerce").fillna(0.0)
            else:
                valores = pd.Series([0.0] * len(lan))

            if "tipo" in lan.columns:
                tipos = lan["tipo"].fillna("").astype(str).str.upper()
            else:
                tipos = pd.Series([""] * len(lan))

            mask_entrada = tipos.str.contains("ENTRADA|RECEITA|CREDITO|CRÉDITO", regex=True, na=False)
            mask_saida = tipos.str.contains("SAIDA|SAÍDA|DESPESA|DEBITO|DÉBITO", regex=True, na=False)

            entradas = float(valores[mask_entrada].sum())
            saidas = float(valores[mask_saida].sum())

            if "data" in lan.columns:
                datas = pd.to_datetime(lan["data"], errors="coerce")
                hoje = pd.Timestamp.today()
                mask_mes = (datas.dt.year == hoje.year) & (datas.dt.month == hoje.month)
                entradas_mes = float(valores[mask_entrada & mask_mes].sum())
                saidas_mes = float(valores[mask_saida & mask_mes].sum())

        registros.append(
            {
                "Igreja": nome,
                "Slug": slug,
                "Plano": plano.capitalize(),
                "Ativa": "Sim" if ativo else "Não",
                "Membros": qtd_membros,
                "Cadastros": qtd_cadastros,
                "Lançamentos": qtd_lancamentos,
                "Entradas": entradas,
                "Saídas": saidas,
                "Saldo": entradas - saidas,
                "Entradas no mês": entradas_mes,
                "Saídas no mês": saidas_mes,
                "Saldo no mês": entradas_mes - saidas_mes,
            }
        )

    return pd.DataFrame(registros)


def _resumo_geral(df_igrejas: pd.DataFrame, df_metricas: pd.DataFrame) -> Dict[str, Any]:
    total_igrejas = int(len(df_igrejas))
    ativas = int(df_igrejas["ativo"].sum()) if "ativo" in df_igrejas.columns and total_igrejas else 0

    if df_metricas.empty:
        return {
            "total_igrejas": total_igrejas,
            "ativas": ativas,
            "membros": 0,
            "entradas_mes": 0.0,
            "saidas_mes": 0.0,
            "saldo_mes": 0.0,
            "saldo_total": 0.0,
        }

    return {
        "total_igrejas": total_igrejas,
        "ativas": ativas,
        "membros": int(pd.to_numeric(df_metricas["Membros"], errors="coerce").fillna(0).sum()),
        "entradas_mes": float(pd.to_numeric(df_metricas["Entradas no mês"], errors="coerce").fillna(0).sum()),
        "saidas_mes": float(pd.to_numeric(df_metricas["Saídas no mês"], errors="coerce").fillna(0).sum()),
        "saldo_mes": float(pd.to_numeric(df_metricas["Saldo no mês"], errors="coerce").fillna(0).sum()),
        "saldo_total": float(pd.to_numeric(df_metricas["Saldo"], errors="coerce").fillna(0).sum()),
    }


# ─────────────────────────────────────────────────────────────
# Renderização
# ─────────────────────────────────────────────────────────────

def _render_card(label: str, valor: str, nota: str = "") -> None:
    st.markdown(
        f"""
        <div class="adm-card">
            <div class="adm-card-label">{label}</div>
            <div class="adm-card-value">{valor}</div>
            <div class="adm-card-note">{nota}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_graficos(df_igrejas: pd.DataFrame, df_metricas: pd.DataFrame) -> None:
    st.markdown('<div class="adm-section-title">Visão por plano e movimentação</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.caption("Igrejas por plano")
        if not df_igrejas.empty and "plano" in df_igrejas.columns:
            planos = (
                df_igrejas["plano"]
                .fillna("basico")
                .map(_normalizar_plano)
                .str.capitalize()
                .value_counts()
                .rename_axis("Plano")
                .reset_index(name="Quantidade")
            )
            st.bar_chart(planos.set_index("Plano"))
        else:
            st.info("Nenhuma igreja cadastrada para exibir por plano.")

    with col2:
        st.caption("Saldo total por igreja")
        if not df_metricas.empty and "Saldo" in df_metricas.columns:
            graf = df_metricas[["Igreja", "Saldo"]].copy()
            graf["Saldo"] = pd.to_numeric(graf["Saldo"], errors="coerce").fillna(0)
            graf = graf.sort_values("Saldo", ascending=False).head(10)
            st.bar_chart(graf.set_index("Igreja"))
        else:
            st.info("Nenhuma movimentação encontrada para exibir.")


def _render_tabela(df_metricas: pd.DataFrame) -> None:
    st.markdown('<div class="adm-section-title">Resumo por igreja</div>', unsafe_allow_html=True)

    if df_metricas.empty:
        st.info("Nenhuma igreja encontrada no cadastro master.")
        return

    tabela = df_metricas.copy()

    for col in ["Entradas", "Saídas", "Saldo", "Entradas no mês", "Saídas no mês", "Saldo no mês"]:
        if col in tabela.columns:
            tabela[col] = tabela[col].map(_formatar_moeda)

    st.dataframe(
        tabela,
        use_container_width=True,
        hide_index=True,
    )


def render() -> None:
    """
    Renderiza o dashboard geral do administrador.
    """
    _injetar_css()

    st.markdown(
        """
        <div class="adm-hero">
            <h1>Dashboard geral</h1>
            <p>Visão consolidada das igrejas cadastradas, planos, membros e movimentações financeiras.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    df_igrejas = _carregar_igrejas()
    df_metricas = _metricas_por_igreja(df_igrejas) if not df_igrejas.empty else pd.DataFrame()
    resumo = _resumo_geral(df_igrejas, df_metricas)

    if df_igrejas.empty:
        st.markdown(
            """
            <div class="adm-warn">
                Não foi possível localizar igrejas cadastradas pelo dashboard geral.
                O módulo foi carregado corretamente, mas o repository.py não retornou uma lista de igrejas
                por uma das funções esperadas: listar_igrejas, carregar_igrejas, obter_igrejas ou listar_tenants.
            </div>
            """,
            unsafe_allow_html=True,
        )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _render_card("Igrejas cadastradas", str(resumo["total_igrejas"]), f'{resumo["ativas"]} ativas')
    with col2:
        _render_card("Membros cadastrados", str(resumo["membros"]), "Soma consolidada")
    with col3:
        _render_card("Entradas no mês", _formatar_moeda(resumo["entradas_mes"]), "Receitas do mês atual")
    with col4:
        _render_card("Saldo no mês", _formatar_moeda(resumo["saldo_mes"]), "Entradas - saídas")

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        _render_card("Saídas no mês", _formatar_moeda(resumo["saidas_mes"]), "Despesas do mês atual")
    with col6:
        _render_card("Saldo consolidado", _formatar_moeda(resumo["saldo_total"]), "Todas as igrejas")
    with col7:
        planos = df_igrejas["plano"].nunique() if not df_igrejas.empty and "plano" in df_igrejas.columns else 0
        _render_card("Planos em uso", str(planos), "Básico, Profissional ou Premium")
    with col8:
        hoje = _dt.datetime.now().strftime("%d/%m/%Y")
        _render_card("Atualização", hoje, "Dados carregados em tempo real")

    _render_graficos(df_igrejas, df_metricas)
    _render_tabela(df_metricas)

    with st.expander("Diagnóstico técnico do dashboard"):
        st.write("Funções procuradas em `data.repository`: listar_igrejas, carregar_igrejas, obter_igrejas, listar_tenants.")
        st.write("Colunas normalizadas de igrejas:", list(df_igrejas.columns))
        st.write("Quantidade de igrejas lidas:", len(df_igrejas))
        st.caption("Este bloco ajuda a diagnosticar diferenças entre versões do repository.py.")


# ─────────────────────────────────────────────────────────────
# Aliases para compatibilidade com admin/painel.py
# ─────────────────────────────────────────────────────────────

def render_dashboard_geral() -> None:
    render()


def exibir_dashboard_geral() -> None:
    render()


def dashboard_geral() -> None:
    render()


def renderizar() -> None:
    render()


def renderizar_dashboard_geral() -> None:
    render()


def aba_dashboard_geral() -> None:
    render()


def painel_dashboard_geral() -> None:
    render()


def pagina_dashboard_geral() -> None:
    render()


__all__ = [
    "render",
    "render_dashboard_geral",
    "exibir_dashboard_geral",
    "dashboard_geral",
    "renderizar",
    "renderizar_dashboard_geral",
    "aba_dashboard_geral",
    "painel_dashboard_geral",
    "pagina_dashboard_geral",
]
