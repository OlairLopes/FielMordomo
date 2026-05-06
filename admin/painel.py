"""Painel do super admin — gerencia igrejas, planos e senhas."""

import streamlit as st
import pandas as pd

from data.models import Igreja
from data.repository import (
    listar_igrejas, criar_igreja, atualizar_igreja,
    excluir_igreja, redefinir_senha_igreja,
    slugify, hash_senha, alterar_senha_super_admin,
)
from utils.helpers import confirmar_exclusao

PLANOS = ["basico", "profissional", "premium"]


def render():
    st.title("FielMordomo — Painel Admin")
    st.caption("Gerenciamento de igrejas e planos")

    aba1, aba2, aba3 = st.tabs(["Igrejas", "Nova igreja", "Configuracoes"])

    with aba1:
        _listar_igrejas()

    with aba2:
        _criar_igreja()

    with aba3:
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
    sel    = df[df.apply(lambda r: f'{int(r["id"])} | {r["nome"]} | {r["slug"]} | {r["plano"]}' == rotulo, axis=1)].iloc[0]
    id_ig  = int(sel["id"])

    nome_e  = st.text_input("Nome da igreja",   value=str(sel["nome"]),        key="ae_nome")
    email_e = st.text_input("E-mail do admin",  value=str(sel["email_admin"]), key="ae_email")
    plano_e = st.selectbox("Plano", PLANOS, index=PLANOS.index(sel["plano"]) if sel["plano"] in PLANOS else 0, key="ae_plano")
    ativa_e = st.toggle("Igreja ativa", value=bool(sel["ativa"]), key="ae_ativa")

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("Salvar alteracoes", type="primary", key="btn_upd_ig"):
            atualizar_igreja(id_ig, nome_e, email_e, plano_e, ativa_e)
            st.toast("Igreja atualizada!")
            st.rerun()

    with c2:
        st.write("**Redefinir senha**")
        nova_senha = st.text_input("Nova senha", type="password", key="nova_senha_ig")
        if st.button("Redefinir senha", key="btn_reset_senha"):
            if len(nova_senha) < 6:
                st.error("Senha deve ter ao menos 6 caracteres.")
            else:
                redefinir_senha_igreja(id_ig, nova_senha)
                st.toast("Senha redefinida!")

    with c3:
        if confirmar_exclusao(f"del_ig_{id_ig}", "Excluir igreja"):
            excluir_igreja(id_ig, str(sel["slug"]))
            st.toast("Igreja excluida.")
            st.rerun()


def _criar_igreja():
    st.subheader("Cadastrar nova igreja")

    with st.form("form_nova_ig", clear_on_submit=True):
        nome  = st.text_input("Nome da igreja")
        slug_sugerido = st.text_input("Identificador (slug)", placeholder="ex: ad-serrinha",
                                       help="Letras minusculas, numeros e hifens. Sera o login da igreja.")
        email = st.text_input("E-mail do tesoureiro")
        senha = st.text_input("Senha inicial", type="password")
        plano = st.selectbox("Plano", PLANOS)

        if st.form_submit_button("Criar igreja", type="primary"):
            slug = slugify(slug_sugerido or nome)
            ig = Igreja(
                nome=nome, slug=slug, email_admin=email,
                senha_hash=hash_senha(senha), plano=plano,
            )
            erros = ig.validar()
            if not senha or len(senha) < 6:
                erros.append("Senha deve ter ao menos 6 caracteres.")
            if erros:
                for e in erros: st.error(e)
            else:
                try:
                    id_novo = criar_igreja(ig)
                    st.success(f"Igreja criada! ID: {id_novo} | Slug: {slug}")
                    st.info(f"O tesoureiro acessa com: **{slug}** + senha definida acima.")
                except Exception as ex:
                    if "UNIQUE" in str(ex):
                        st.error(f"Slug '{slug}' ja existe. Escolha outro identificador.")
                    else:
                        st.error(f"Erro ao criar igreja: {ex}")


def _configuracoes():
    st.subheader("Alterar senha do administrador")

    with st.form("form_senha_admin"):
        nova = st.text_input("Nova senha", type="password")
        conf = st.text_input("Confirmar nova senha", type="password")
        if st.form_submit_button("Alterar senha", type="primary"):
            if len(nova) < 6:
                st.error("Senha deve ter ao menos 6 caracteres.")
            elif nova != conf:
                st.error("As senhas nao coincidem.")
            else:
                alterar_senha_super_admin("admin", nova)
                st.toast("Senha alterada!")
