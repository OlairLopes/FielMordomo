import datetime
import pandas as pd
import streamlit as st

from data.repository import carregar_lancamentos
from utils.helpers import formatar_moeda, slug_da_sessao
from utils.planos import obter_plano, proximo_plano, texto_limite


NAV = [
    ("cadastros",       "Membros e fornecedores", "Gerencie o cadastro de membros e fornecedores."),
    ("lancamentos",     "Lancamentos",            "Registre entradas e saidas financeiras."),
    ("relatorios",      "Relatorios",             "Filtre e exporte dados por periodo."),
    ("dashboard",       "Dashboard",              "Graficos e indicadores visuais."),
    ("aniversariantes", "🎂 Aniversariantes",       "Veja quem faz aniversario hoje, na semana ou no mes."),
]


def _card_plano(igreja):
    plano   = igreja.get("plano", "basico")
    p_info  = obter_plano(plano)
    cor     = p_info["cor"]
    nome_p  = p_info["nome"]
    preco   = p_info["preco"]
    limite  = texto_limite(plano)

    recursos = [
        f"✅ Ate {limite} membros",
        "✅ Dashboard, Relatorios e Aniversariantes",
        "✅ Cupom fiscal",
    ]
    if p_info["lancamento_lote"]:
        recursos.append("✅ Lancamento em lote")
    else:
        recursos.append("❌ Lancamento em lote")
    if p_info["backup_automatico"]:
        recursos.append("✅ Backup automatico (diario/semanal)")
    else:
        recursos.append("❌ Backup automatico (apenas manual)")

    recursos_html = "<br>".join(recursos)

    upgrade_html = ""
    if plano != "premium":
        prox      = proximo_plano(plano)
        prox_info = obter_plano(prox)
        upgrade_html = (
            '<div style="margin-top:14px;padding:10px;background:rgba(255,255,255,0.7);'
            'border-radius:6px;font-size:0.82rem;text-align:center">'
            f'💡 <b>Upgrade para {prox_info["nome"]}</b> por {prox_info["preco"]}<br>'
            '<span style="color:#666">Contate o administrador para fazer upgrade</span>'
            '</div>'
        )

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,{cor}15,{cor}05);
                border:2px solid {cor};border-radius:12px;padding:18px;
                margin-bottom:18px">
        <div style="display:flex;justify-content:space-between;align-items:start">
            <div>
                <div style="font-size:0.75rem;color:#888;text-transform:uppercase;
                            font-weight:600;letter-spacing:0.05em">Seu plano</div>
                <div style="font-size:1.4rem;font-weight:700;color:{cor};
                            margin-top:2px">{nome_p}</div>
                <div style="font-size:0.9rem;color:#666;margin-top:2px">{preco}</div>
            </div>
            <div style="background:{cor};color:white;padding:4px 12px;
                        border-radius:20px;font-size:0.75rem;font-weight:600">
                ATIVO
            </div>
        </div>
        <div style="font-size:0.85rem;color:#444;margin-top:14px;line-height:1.7">
            {recursos_html}
        </div>
        {upgrade_html}
    </div>
    """, unsafe_allow_html=True)


def _kpis(slug):
    df = carregar_lancamentos(slug)
    if df.empty:
        return
    df["data"]  = pd.to_datetime(df["data"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    hoje = datetime.date.today()
    mes_atual = df[df["data"].dt.month == hoje.month]
    ent = mes_atual[mes_atual["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
    sai = mes_atual[mes_atual["tipo"].str.upper() == "SAIDA"]["valor"].sum()
    k1, k2, k3 = st.columns(3)
    k1.metric("Entradas (mes)", formatar_moeda(ent))
    k2.metric("Saidas (mes)",   formatar_moeda(sai))
    k3.metric("Saldo (mes)",    formatar_moeda(ent - sai))


def _cards_nav():
    st.subheader("Ir para")
    c1, c2 = st.columns(2)
    cols = [c1, c2] * ((len(NAV) + 1) // 2)
    for (page, title, desc), col in zip(NAV, cols):
        with col:
            with st.container(border=True):
                st.markdown("### " + title)
                st.caption(desc)
                if st.button("Abrir", key="home_card_" + page,
                             use_container_width=True, type="primary"):
                    st.session_state["pagina"] = page
                    st.rerun()


def render():
    slug   = slug_da_sessao()
    igreja = st.session_state.get("igreja", {})
    st.subheader("Bem-vindo, " + igreja.get("nome", "Igreja"))

    _card_plano(igreja)
    _kpis(slug)
    st.divider()
    _cards_nav()
