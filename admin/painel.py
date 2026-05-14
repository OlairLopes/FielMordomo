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
        nova_senha = st.text_input("Nova senha", type="password", key="nova_senha_ig")
        if st.button("Redefinir senha", key="btn_reset_senha"):
            if len(nova_senha) < 6:
                st.error("Senha deve ter ao menos 6 caracteres.")
            else:
                redefinir_senha_igreja(id_ig, nova_senha)
                st.toast("Senha redefinida!")

    with c3:
        if confirmar_exclusao(f"del_ig_{id_ig}", "Excluir igreja"):
            excluir_igreja(id_ig, slug)
            st.toast("Igreja excluida.")
            st.rerun()


def _criar_igreja():
    st.subheader("Cadastrar nova igreja")

    with st.form("form_nova_ig", clear_on_submit=True):
        nome  = st.text_input("Nome da igreja")
        slug_sugerido = st.text_input(
            "Identificador (slug)",
            placeholder="ex: ad-serrinha",
            help="Letras minusculas, numeros e hifens. Sera o login da igreja.",
        )
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
                    st.toast(f"Igreja criada! ID: {id_novo} | Slug: {slug}")
                    # Limpa caches para forcar releitura do banco
                    for k in list(st.session_state.keys()):
                        if k.startswith("df_") or k.startswith("admin_"):
                            st.session_state.pop(k, None)
                    st.rerun()
                except Exception as ex:
                    if "UNIQUE" in str(ex):
                        st.error(f"Slug '{slug}' ja existe. Escolha outro identificador.")
                    else:
                        st.error(f"Erro: {ex}")


def _gerenciar_logos():
    st.subheader("Logos do sistema")

    st.markdown("#### Logo do FielMordomo")
    st.caption("Aparece na tela de login e na sidebar do administrador.")

    logo_sis = obter_logo_sistema()
    if logo_sis:
        dados, ext = logo_sis
        st.image(dados, width=200)
        st.caption(f"Formato atual: {ext.upper()}")
    else:
        st.info("Nenhum logo do sistema cadastrado ainda.")

    arquivo_sis = st.file_uploader(
        "Enviar logo do FielMordomo",
        type=["png", "jpg", "jpeg", "webp"],
        key="upload_logo_sis",
    )
    if arquivo_sis:
        ext = arquivo_sis.name.rsplit(".", 1)[-1].lower()
        salvar_logo_sistema(arquivo_sis.read(), ext)
        st.toast("Logo do sistema salvo!")
        st.rerun()

    st.divider()
    st.markdown("#### Logo por igreja")
    st.caption("Aparece na sidebar apos o login da igreja.")

    df = listar_igrejas()
    if df.empty:
        st.info("Nenhuma igreja cadastrada ainda.")
        return

    opcoes_ig = df.apply(lambda r: f'{r["nome"]} ({r["slug"]})', axis=1).tolist()
    ig_sel    = st.selectbox("Selecione a igreja", opcoes_ig, key="sel_ig_logo")
    idx       = opcoes_ig.index(ig_sel)
    slug      = str(df.iloc[idx]["slug"])

    logo_ig = obter_logo_igreja(slug)
    if logo_ig:
        dados, ext = logo_ig
        st.image(dados, width=200)
        st.caption(f"Formato atual: {ext.upper()}")
    else:
        st.info(f"Nenhum logo cadastrado para {ig_sel}.")

    arquivo_ig = st.file_uploader(
        f"Enviar logo para: {ig_sel}",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"upload_logo_ig_{slug}",
    )
    if arquivo_ig:
        ext = arquivo_ig.name.rsplit(".", 1)[-1].lower()
        salvar_logo_igreja(slug, arquivo_ig.read(), ext)
        st.toast(f"Logo de {ig_sel} salvo!")
        st.rerun()


def _backup_admin():
    import io, zipfile
    from data.repository import carregar_cadastros, carregar_lancamentos, _tenant_db
    import pandas as _pd

    st.subheader("Backup de todas as igrejas")
    df_igrejas = listar_igrejas()

    if df_igrejas.empty:
        st.info("Nenhuma igreja cadastrada.")
        return

    st.caption(f"{len(df_igrejas)} igreja(s) encontrada(s).")

    if st.button("Gerar backup de todas as igrejas", type="primary", key="btn_backup_admin"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for _, row in df_igrejas.iterrows():
                slug = str(row["slug"])
                try:
                    df_c = carregar_cadastros(slug)
                    zf.writestr(f"{slug}/cadastros.csv",
                                df_c.to_csv(index=False, encoding="utf-8-sig"))
                except Exception:
                    pass
                try:
                    df_l = carregar_lancamentos(slug)
                    if not df_l.empty and "data" in df_l.columns:
                        df_l = df_l.copy()
                        df_l["data"] = _pd.to_datetime(df_l["data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
                    zf.writestr(f"{slug}/lancamentos.csv",
                                df_l.to_csv(index=False, encoding="utf-8-sig"))
                except Exception:
                    pass
                try:
                    db = _tenant_db(slug)
                    if db.exists():
                        zf.writestr(f"{slug}/banco_{slug}.db", db.read_bytes())
                except Exception:
                    pass

        buf.seek(0)
        st.session_state["backup_admin_dados"] = buf.read()
        st.session_state["backup_admin_nome"]  = (
            f"backup_todas_igrejas_{_pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.zip"
        )
        st.toast("Backup gerado!")

    if "backup_admin_dados" in st.session_state:
        st.download_button(
            "Baixar backup completo",
            data=st.session_state["backup_admin_dados"],
            file_name=st.session_state["backup_admin_nome"],
            mime="application/zip",
            key="dl_backup_admin",
            type="primary",
            use_container_width=True,
        )


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
