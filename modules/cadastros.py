import streamlit as st
import pandas as pd

from data.models import Cadastro
from data.repository import (
    carregar_cadastros, inserir_cadastro, atualizar_cadastro,
    excluir_cadastro, cadastro_em_uso,
)
from utils.helpers import (
    preparar_df, confirmar_exclusao, slug_da_sessao, solicitar_autorizacao,
)

FUNCOES = [
    "Membro", "Congregado", "Auxiliar", "Pastor", "Diacono", "Diaconisa",
    "Presbitero", "Evangelista", "Cooperador", "Dirigente",
    "Secretario", "Tesoureiro", "Professor", "Lider", "",
]

CONGREGACOES = [
    "AD Serrinha",
    "AD Paraiso",
    "AD Vila Nova",
    "",
]


def _cache_key():
    return f"df_cad_{slug_da_sessao()}"


def _get(slug):
    k = _cache_key()
    if k not in st.session_state:
        st.session_state[k] = carregar_cadastros(slug)
    return st.session_state[k]


def _invalida(slug):
    st.session_state.pop(_cache_key(), None)


def render():
    slug = slug_da_sessao()
    st.subheader("Membros e fornecedores")
    df = _get(slug)

    # ── Novo cadastro ────────────────────────────────────────────────────
    with st.expander("Novo cadastro", expanded=False):
        with st.form("form_novo_cad", clear_on_submit=True):
            tipo   = st.selectbox("Tipo", ["Membro", "Fornecedor"])
            nome   = st.text_input("Nome")
            funcao = st.selectbox("Funcao", FUNCOES) if tipo == "Membro" else ""
            cong   = st.selectbox("Congregacao", CONGREGACOES)
            sit    = st.selectbox("Situacao", ["Ativo", "Inativo"])
            if st.form_submit_button("Salvar", type="primary"):
                c = Cadastro(nome=nome, tipo_cadastro=tipo, funcao=funcao,
                             congregacao=cong, situacao=sit)
                erros = c.validar()
                if erros:
                    for e in erros: st.error(e)
                else:
                    inserir_cadastro(slug, c)
                    _invalida(slug)
                    st.toast("Cadastro salvo!")
                    st.rerun()

    # ── Tabela (oculta por padrao) ────────────────────────────────────────
    total = len(df)
    with st.expander(f"Ver cadastros ({total} registros)", expanded=False):
        if df.empty:
            st.info("Nenhum cadastro ainda.")
        else:
            st.dataframe(preparar_df(df), use_container_width=True)

    # ── Editar / Excluir (requer autorizacao) ────────────────────────────
    with st.expander("Editar ou excluir cadastro", expanded=False):
        if df.empty:
            st.info("Nenhum cadastro ainda.")
            return

        df_r = df.reset_index(drop=True)
        df_r["rotulo"] = df_r.apply(
            lambda r: f'{int(r["id_cadastro"])} | {r["tipo_cadastro"]} | {r["nome"]} | {r["situacao"]}',
            axis=1,
        )
        rotulo = st.selectbox("Selecione", df_r["rotulo"].tolist())
        sel    = df_r[df_r["rotulo"] == rotulo].iloc[0]
        id_sel = int(sel["id_cadastro"])

        tipo_opc  = ["Membro", "Fornecedor"]
        tipo_edit = st.selectbox("Tipo", tipo_opc,
                                 index=tipo_opc.index(sel["tipo_cadastro"]) if sel["tipo_cadastro"] in tipo_opc else 0,
                                 key="e_tipo")
        nome_edit = st.text_input("Nome", value=str(sel["nome"]), key="e_nome")
        funcao_edit = (
            st.selectbox("Funcao", FUNCOES,
                         index=FUNCOES.index(str(sel["funcao"])) if str(sel["funcao"]) in FUNCOES else 0,
                         key="e_funcao")
            if tipo_edit == "Membro" else ""
        )

        cong_atual = str(sel["congregacao"])
        idx_cong   = CONGREGACOES.index(cong_atual) if cong_atual in CONGREGACOES else 0
        cong_edit  = st.selectbox("Congregacao", CONGREGACOES, index=idx_cong, key="e_cong")

        sit_opc  = ["Ativo", "Inativo"]
        sit_edit = st.selectbox("Situacao", sit_opc,
                                index=sit_opc.index(sel["situacao"]) if sel["situacao"] in sit_opc else 0,
                                key="e_sit")

        st.divider()
        c1, c2 = st.columns(2)

        with c1:
            st.caption("Editar cadastro")
            if solicitar_autorizacao("salvar_cad", "editar"):
                c = Cadastro(id_cadastro=id_sel, nome=nome_edit, tipo_cadastro=tipo_edit,
                             funcao=funcao_edit, congregacao=cong_edit, situacao=sit_edit)
                erros = c.validar()
                if erros:
                    for e in erros: st.error(e)
                else:
                    atualizar_cadastro(slug, c)
                    _invalida(slug)
                    st.toast("Cadastro alterado!")
                    st.rerun()

        with c2:
            st.caption("Excluir cadastro")
            if solicitar_autorizacao("excluir_cad", "excluir"):
                if cadastro_em_uso(slug, id_sel):
                    st.error("Cadastro vinculado a lancamento. Nao e possivel excluir.")
                else:
                    if confirmar_exclusao("del_cad_final", "Confirmar exclusao"):
                        excluir_cadastro(slug, id_sel)
                        _invalida(slug)
                        st.toast("Excluido.")
                        st.rerun()
