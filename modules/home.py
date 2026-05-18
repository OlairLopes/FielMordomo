"""
Tela inicial da igreja - logo centralizado + KPIs.
"""

import datetime
import base64
import pandas as pd
import streamlit as st

from data.repository import (
    carregar_lancamentos, carregar_cadastros,
    obter_logo_igreja, obter_logo_sistema,
)
from utils.helpers import formatar_moeda, slug_da_sessao
from utils.planos import obter_plano, texto_limite


def _img_b64(dados, ext):
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/" + ext
    return "data:" + mime + ";base64," + base64.b64encode(dados).decode()


def render():
    slug   = slug_da_sessao()
    igreja = st.session_state.get("igreja", {})

    # ── Logo grande centralizado ──────────────────────────────────────────
    logo_r = obter_logo_igreja(slug) or obter_logo_sistema()

    if logo_r:
        dados, ext = logo_r
        img_src = _img_b64(dados, ext)
        st.markdown(f"""
        <div style="display:flex;flex-direction:column;align-items:center;
                    justify-content:center;padding:40px 20px 30px 20px">
            <img src="{img_src}"
                 style="max-width:260px;max-height:200px;object-fit:contain;
                        filter:drop-shadow(0 4px 12px rgba(15,110,86,0.15))"/>
            <h2 style="color:#0F6E56;margin:20px 0 4px 0;font-weight:700;
                       font-size:1.8rem;text-align:center">
                {igreja.get("nome", "FielMordomo")}
            </h2>
            <p style="color:#888;font-size:0.95rem;margin:0;text-align:center">
                Gestao financeira da igreja
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="display:flex;flex-direction:column;align-items:center;
                    justify-content:center;padding:60px 20px 40px 20px">
            <div style="font-size:3.5rem;font-weight:800;color:#0F6E56;
                        letter-spacing:-1px">FielMordomo</div>
            <h2 style="color:#0F6E56;margin:20px 0 4px 0;font-weight:700;
                       font-size:1.6rem;text-align:center">
                {igreja.get("nome", "")}
            </h2>
            <p style="color:#888;font-size:0.95rem;margin:0;text-align:center">
                Gestao financeira da igreja
            </p>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── KPIs do mes corrente ──────────────────────────────────────────────
    df_lanc = carregar_lancamentos(slug)
    df_cad  = carregar_cadastros(slug)

    hoje = datetime.date.today()
    ini_mes = hoje.replace(day=1)

    if not df_lanc.empty:
        df_lanc["data"]  = pd.to_datetime(df_lanc["data"], errors="coerce")
        df_lanc["valor"] = pd.to_numeric(df_lanc["valor"], errors="coerce").fillna(0.0)
        df_mes = df_lanc[
            (df_lanc["data"] >= pd.Timestamp(ini_mes)) &
            (df_lanc["data"] <= pd.Timestamp(hoje))
        ]
        ent_mes = df_mes[df_mes["tipo"].str.upper() == "ENTRADA"]["valor"].sum()
        sai_mes = df_mes[df_mes["tipo"].str.upper() == "SAIDA"]["valor"].sum()
        sal_mes = ent_mes - sai_mes
        n_lanc_mes = len(df_mes)
    else:
        ent_mes = sai_mes = sal_mes = 0.0
        n_lanc_mes = 0

    if not df_cad.empty and "tipo_cadastro" in df_cad.columns:
        qtd_membros = len(df_cad[df_cad["tipo_cadastro"].str.upper() == "MEMBRO"])
    else:
        qtd_membros = 0

    plano    = igreja.get("plano", "basico")
    p_info   = obter_plano(plano)
    lim_txt  = texto_limite(plano)

    st.markdown(f"""
    <h4 style="color:#0F6E56;margin:18px 0 12px 0">
        📊 Resumo de {hoje.strftime('%B/%Y').capitalize()}
    </h4>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)

    cor_saldo = "#1E73BE" if sal_mes >= 0 else "#C62828"
    with c1:
        st.markdown(f"""
        <div style="background:white;border-radius:12px;padding:16px 18px;
                    box-shadow:0 2px 6px rgba(0,0,0,0.08);
                    border-left:4px solid {cor_saldo};height:100%">
            <div style="font-size:0.72rem;font-weight:600;color:#888;
                        text-transform:uppercase;letter-spacing:0.05em">Saldo do mes</div>
            <div style="font-size:1.35rem;font-weight:700;color:{cor_saldo};
                        line-height:1.2;margin-top:4px">{formatar_moeda(sal_mes)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div style="background:white;border-radius:12px;padding:16px 18px;
                    box-shadow:0 2px 6px rgba(0,0,0,0.08);
                    border-left:4px solid #1E73BE;height:100%">
            <div style="font-size:0.72rem;font-weight:600;color:#888;
                        text-transform:uppercase;letter-spacing:0.05em">Entradas do mes</div>
            <div style="font-size:1.35rem;font-weight:700;color:#1E73BE;
                        line-height:1.2;margin-top:4px">{formatar_moeda(ent_mes)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div style="background:white;border-radius:12px;padding:16px 18px;
                    box-shadow:0 2px 6px rgba(0,0,0,0.08);
                    border-left:4px solid #C62828;height:100%">
            <div style="font-size:0.72rem;font-weight:600;color:#888;
                        text-transform:uppercase;letter-spacing:0.05em">Saidas do mes</div>
            <div style="font-size:1.35rem;font-weight:700;color:#C62828;
                        line-height:1.2;margin-top:4px">{formatar_moeda(sai_mes)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div style="background:white;border-radius:12px;padding:16px 18px;
                    box-shadow:0 2px 6px rgba(0,0,0,0.08);
                    border-left:4px solid #F57C00;height:100%">
            <div style="font-size:0.72rem;font-weight:600;color:#888;
                        text-transform:uppercase;letter-spacing:0.05em">Lancamentos / Membros</div>
            <div style="font-size:1.35rem;font-weight:700;color:#F57C00;
                        line-height:1.2;margin-top:4px">{n_lanc_mes} / {qtd_membros}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Card do plano ─────────────────────────────────────────────────────
    st.markdown("")
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,{p_info['cor']} 0%,#0F6E56 100%);
                border-radius:14px;padding:22px 26px;color:white;margin-top:14px;
                box-shadow:0 4px 14px rgba(15,110,86,0.25)">
        <div style="display:flex;justify-content:space-between;align-items:center;
                    flex-wrap:wrap;gap:10px">
            <div>
                <div style="font-size:0.72rem;text-transform:uppercase;
                            letter-spacing:0.08em;opacity:0.85">Plano atual</div>
                <div style="font-size:1.6rem;font-weight:700;margin-top:2px">
                    {p_info['nome']}
                </div>
                <div style="font-size:0.85rem;opacity:0.9;margin-top:4px">
                    Limite: {lim_txt} membros • {p_info['preco']}
                </div>
            </div>
            <div style="font-size:2.6rem;opacity:0.5">⛪</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
