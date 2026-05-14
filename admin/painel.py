"""Painel do super admin — gerencia igrejas, planos, senhas, logos e backup."""

import streamlit as st
import pandas as pd

from data.models import Igreja
from data.repository import (
    listar_igrejas, criar_igreja, atualizar_igreja,
    excluir_igreja, redefinir_senha_igreja,
    slugify, hash_senha, alterar_senha_super_admin,
    salvar_logo_sistema, obter_logo_sistema,
    salvar_logo_igreja, obter_logo_igreja,
)
from utils.helpers import confirmar_exclusao

PLANOS = ["basico", "profissional", "premium"]


def render():
    st.title("FielMordomo — Painel Admin")
    st.caption("Gerenciamento de igrejas e planos")

    aba1, aba2, aba3, aba4, aba5 = st.tabs([
        "Igrejas", "Nova igreja", "Logos", "Backup", "Configuracoes"
    ])

    with aba1:
        _listar_igrejas()
    with aba2:
        _criar_igreja()
    with aba3:
        _gerenciar_logos()
    with aba4:
        _backup_admin()
    with aba5:
        _configuracoes()


def _listar_igrejas():
    df = listar_igrejas()
    if df.empty:
        st.info("Nenhuma igreja cadastrada ainda.")
        return

    df_show = df.copy()
    df_show["ativa"] = df_show["ativa"].map({1: "Sim", 0: "Nao"})
    st.dataframe(df_show, use_container_width=True)

    st.divider()
    st.subheader("Editar igreja")

    rotuloslist = df.apply(
        lambda r: f'{int(r["id"])} | {r["nome"]} | {r["slug"]} | {r["plano"]}', axis=1
    ).tolist()
    rotulo = st.selectbox("Selecione a igreja", rotuloslist)
    sel    = df[df.apply(
        lambda r: f'{int(r["id"])} | {r["nome"]} | {r["slug"]} | {r["plano"]}' == rotulo, axis=1
    )].iloc[0]
    id_ig  = int(sel["id"])
    slug   = str(sel["slug"])

    nome_e  = st.text_input("Nome da igreja",  value=str(sel["nome"]),        key="ae_nome")
    email_e = st.text_input("E-mail do admin", value=str(sel["email_admin"]), key="ae_email")
    plano_e = st.selectbox("Plano", PLANOS,
                           index=PLANOS.index(sel["plano"]) if sel["plano"] in PLANOS else 0,
                           key="ae_plano")
    ativa_e = st.toggle("Igreja ativa", value=bool(sel["ativa"]), key="ae_ativa")

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("Salvar alteracoes", type="primary", key="btn_upd_ig"):
            atualizar_igreja(id_ig, nome_e, email_e, plano_e, ativa_e)
            st.toast("Igreja atualizada!")
            st.rerun()

    with c2:
        st.write("**Redefinir senha**")
        nova_senha =
