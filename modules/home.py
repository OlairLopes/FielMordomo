import streamlit as st
import pandas as pd

from data.repository import carregar_cadastros, carregar_lancamentos
from utils.helpers import formatar_moeda, slug_da_sessao
from utils.planos import plano_da_igreja, limite_cadastros, PLANOS


NAV = [
    ("cadastros",       "Membros e fornecedores", "Gerencie o cadastro de membros e fornecedores."),
    ("lancamentos",     "Lancamentos",            "Registre entradas e saidas financeiras."),
    ("relatorios",      "Relatorios",             "Filtre e exporte dados por periodo."),
    ("dashboard",       "Dashboard",              "Graficos e indicadores visuais."),
    ("aniversariantes", "🎂 Aniversariantes",     "Veja quem faz aniversario hoje, na semana ou no mes."),
]


def _kpis():
    slug = slug_da_sessao()
    df_l = carregar_lancamentos(slug)
    df_c = carregar_cadastros(slug)

    if df_l.empty:
        ent = sai = sal = 0.0
        n_lanc = 0
    else:
        df_l["valor"] = pd.to_numeric(df_l["valor"], errors="coerce").fillna(0.0)
        ent = df_l[df_l["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
        sai = df_l[df_l["tipo"].str.upper() == "SAIDA"]["valor"].sum()
        sal = ent - sai
        n_lanc = len(df_l)

    n_membros = len(df_c[df_c["tipo_cadastro"].str.upper() == "MEMBRO"]) if not df_c.empty else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Saldo",       formatar_moeda(sal))
    k2.metric("Entradas",    formatar_moeda(ent))
    k3.metric("Saidas",      formatar_moeda(sai))
    k4.metric("Membros",     str(n_membros))

    st.caption(f"📋 {n_lanc} lancamentos registrados")


def _card_plano():
    """Card mostrando plano atual e botao de upgrade."""
    igreja = st.session_state.get("igreja", {})
    plano  = plano_da_igreja(igreja)
    slug   = slug_da_sessao()
    df_c   = carregar_cadastros(slug)
    qtd_membros = len(df_c[df_c["tipo_cadastro"].str.upper() == "MEMBRO"]) if not df_c.empty else 0
    lim = limite_cadastros(igreja)

    cor = plano["cor"]

    if lim is None:
        uso_str = f"{qtd_membros} membros (ilimitado)"
        pct = 0
    else:
        uso_str = f"{qtd_membros} de {lim} membros"
        pct = min(100, (qtd_membros / lim) * 100) if lim > 0 else 0

    # Recursos liberados
    recursos_html = ""
    icones = {
        "lancamento_lote":   "🛒 Lancamento em lote",
        "backup_automatico": "🔄 Backup automatico",
        "aniversariantes":   "🎂 Aniversariantes",
        "cupom_fiscal":      "🧾 Cupom fiscal",
        "dashboard":         "📊 Dashboard",
        "relatorios":        "📋 Relatorios",
    }
    for chave, label in icones.items():
        ok = plano["recursos"].get(chave, False)
        cor_item = "#1D9E75" if ok else "#ccc"
        marca    = "✓" if ok else "✗"
        recursos_html += (
            f'<div style="font-size:0.78rem;color:{cor_item};margin:2px 0">'
            f'{marca} {label}</div>'
        )

    st.markdown(f"""
    <div style="background:white;border-radius:12px;padding:18px;
                box-shadow:0 2px 8px rgba(0,0,0,0.08);
                border-top:4px solid {cor};margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <div>
                <div style="font-size:0.72rem;color:#888;text-transform:uppercase;letter-spacing:0.06em">Plano atual</div>
                <div style="font-size:1.4rem;font-weight:700;color:{cor}">{plano['nome']}</div>
                <div style="font-size:0.85rem;color:#666">{plano['preco']}</div>
            </div>
            <div style="text-align:right">
                <div style="font-size:0.72rem;color:#888">USO</div>
                <div style="font-size:0.95rem;font-weight:600;color:#333">{uso_str}</div>
            </div>
        </div>
        <div style="background:#f0f0f0;border-radius:6px;height:8px;overflow:hidden;margin:8px 0 12px">
            <div style="background:{cor};height:100%;width:{pct}%;transition:width 0.3s"></div>
        </div>
        <div style="margin-top:8px">
            {recursos_html}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Botao de upgrade (so se nao for premium)
    if str(igreja.get("plano", "")).lower() != "premium":
        if st.button("⬆️ Ver opcoes de upgrade", key="home_upgrade", use_container_width=True, type="primary"):
            st.session_state["show_upgrade"] = True
            st.rerun()


def _modal_upgrade():
    """Tela de comparacao de planos."""
    if not st.session_state.get("show_upgrade"):
        return

    igreja = st.session_state.get("igreja", {})
    plano_atual = str(igreja.get("plano", "basico")).lower()

    st.markdown("---")
    st.markdown("## 💎 Escolha seu plano")
    st.caption("Faca upgrade para liberar mais recursos e cadastros.")

    cols = st.columns(3)
    for i, (chave, p) in enumerate(PLANOS.items()):
        with cols[i]:
            destaque = "border:2px solid " + p["cor"] if chave == plano_atual else "border:1px solid #eee"
            atual_badge = ""
            if chave == plano_atual:
                atual_badge = '<div style="background:#1D9E75;color:white;padding:2px 8px;border-radius:4px;font-size:0.7rem;font-weight:700;display:inline-block;margin-bottom:4px">PLANO ATUAL</div>'

            recursos_html = ""
            icones = {
                "lancamento_lote":   "Lancamento em lote",
                "backup_automatico": "Backup automatico",
                "aniversariantes":   "Aniversariantes",
                "cupom_fiscal":      "Cupom fiscal",
                "dashboard":         "Dashboard",
                "relatorios":        "Relatorios",
            }
            for k, lbl in icones.items():
                ok = p["recursos"].get(k, False)
                cor_i = "#1D9E75" if ok else "#ccc"
                marca = "✓" if ok else "✗"
                recursos_html += f'<div style="color:{cor_i};font-size:0.82rem;margin:3px 0">{marca} {lbl}</div>'

            st.markdown(f"""
            <div style="background:white;border-radius:12px;padding:18px;{destaque};
                        box-shadow:0 2px 8px rgba(0,0,0,0.06);min-height:380px">
                {atual_badge}
                <div style="font-size:1.3rem;font-weight:700;color:{p['cor']}">{p['nome']}</div>
                <div style="font-size:1.5rem;font-weight:700;color:#1a1a1a;margin:8px 0">{p['preco']}</div>
                <div style="font-size:0.85rem;color:#666;margin-bottom:12px">{p['limite_label']}</div>
                <hr style="border:none;border-top:1px solid #eee;margin:8px 0">
                {recursos_html}
            </div>
            """, unsafe_allow_html=True)

            if chave != plano_atual:
                if st.button(f"Solicitar {p['nome']}",
                             key=f"upgrade_btn_{chave}",
                             use_container_width=True,
                             type="primary"):
                    st.success(
                        f"✉️ Solicitacao de upgrade para o plano **{p['nome']}** registrada!\n\n"
                        f"Entre em contato com o administrador do sistema para concluir a alteracao."
                    )

    if st.button("Fechar", key="home_fechar_upgrade"):
        st.session_state["show_upgrade"] = False
        st.rerun()


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
    igreja = st.session_state.get("igreja", {})
    nome   = igreja.get("nome", "Igreja")

    st.subheader(f"Bem-vindo, {nome}!")
    st.caption("Visao geral do sistema FielMordomo")

    _kpis()
    st.divider()
    _card_plano()
    _modal_upgrade()

    if not st.session_state.get("show_upgrade"):
        st.divider()
        _cards_nav()
