import datetime
import streamlit as st
import pandas as pd

from data.models import Lancamento
from data.repository import (
    carregar_cadastros, carregar_lancamentos,
    inserir_lancamento, atualizar_lancamento, excluir_lancamento,
)
from utils.helpers import (
    formatar_moeda, preparar_df, obter_ativos, montar_opcoes,
    encontrar_chave, confirmar_exclusao, gerar_csv,
    slug_da_sessao, solicitar_autorizacao,
)

CATEGORIAS_ENTRADA = ["Campanha", "Dizimo", "Missao", "Oferta"]


def _ck(sufixo): return f"df_{sufixo}_{slug_da_sessao()}"
def _invalida():
    for s in ("cad", "lanc"):
        st.session_state.pop(_ck(s), None)
def _get_cad(slug):
    k = _ck("cad")
    if k not in st.session_state:
        st.session_state[k] = carregar_cadastros(slug)
    return st.session_state[k]
def _get_lanc(slug):
    k = _ck("lanc")
    if k not in st.session_state:
        st.session_state[k] = carregar_lancamentos(slug)
    return st.session_state[k]


def render():
    slug    = slug_da_sessao()
    df_cad  = _get_cad(slug)
    df_lanc = _get_lanc(slug)
    membros = obter_ativos(df_cad, "MEMBRO")
    fornec  = obter_ativos(df_cad, "FORNECEDOR")

    # ── Novo lancamento ──────────────────────────────────────────────────
    with st.expander("Novo lancamento", expanded=False):
        with st.form("form_lanc", clear_on_submit=True):
            data_l = st.date_input("Data", value=datetime.date.today(), format="DD/MM/YYYY")
            tipo   = st.selectbox("Tipo", ["Entrada", "Saida"])
            cat    = st.selectbox("Categoria", CATEGORIAS_ENTRADA) if tipo == "Entrada" else "Despesa"
            if tipo == "Saida":
                st.text_input("Categoria", value="Despesa", disabled=True)

            vinc_pad = "Membro" if (tipo == "Entrada" and cat == "Dizimo") else "Fornecedor" if tipo == "Saida" else "Nenhum"
            vincular = st.selectbox("Vincular a", ["Nenhum", "Membro", "Fornecedor"],
                                    index=["Nenhum", "Membro", "Fornecedor"].index(vinc_pad))

            id_cad, nome_cad, tipo_cad = None, "", ""
            if vincular == "Membro" and not membros.empty:
                opc = montar_opcoes(membros)
                esc = st.selectbox("Membro", list(opc.keys()))
                l = opc[esc]; id_cad, nome_cad, tipo_cad = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
            elif vincular == "Fornecedor" and not fornec.empty:
                opc = montar_opcoes(fornec)
                esc = st.selectbox("Fornecedor", list(opc.keys()))
                l = opc[esc]; id_cad, nome_cad, tipo_cad = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]

            desc  = st.text_input("Descricao")
            valor = st.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f")

            if st.form_submit_button("Salvar lancamento", type="primary"):
                lanc = Lancamento(data=data_l, tipo=tipo, categoria=cat,
                                  valor=valor, descricao=desc,
                                  id_cadastro=id_cad, nome_cadastro=nome_cad, tipo_cadastro=tipo_cad)
                erros = lanc.validar()
                if erros:
                    for e in erros: st.error(e)
                else:
                    inserir_lancamento(slug, lanc)
                    _invalida()
                    st.toast("Lancamento salvo!")
                    st.rerun()

    # ── Tabela (oculta por padrao) ────────────────────────────────────────
    total = len(df_lanc)
    with st.expander(f"Ver lancamentos ({total} registros)", expanded=False):
        if df_lanc.empty:
            st.info("Nenhum lancamento ainda.")
        else:
            st.dataframe(preparar_df(df_lanc), use_container_width=True)
            csv = gerar_csv(preparar_df(df_lanc))
            st.download_button("Exportar CSV", csv, "lancamentos.csv", "text/csv")

    # ── Editar / Excluir (requer autorizacao) ────────────────────────────
    with st.expander("Editar ou excluir lancamento", expanded=False):
        if df_lanc.empty:
            st.info("Nenhum lancamento ainda.")
            return

        df_e = df_lanc.copy()
        df_e["data_fmt"] = pd.to_datetime(df_e["data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
        df_e["rotulo"] = df_e.apply(
            lambda r: f'{int(r["id_lancamento"])} | {r["data_fmt"]} | {r["tipo"]} | {r["categoria"]} | {r["nome_cadastro"] or "Sem vinculo"} | {formatar_moeda(r["valor"])}',
            axis=1,
        )

        rotulo  = st.selectbox("Selecione o lancamento", df_e["rotulo"].tolist(), key="sel_lanc_edit")
        sel     = df_e[df_e["rotulo"] == rotulo].iloc[0]
        id_lanc = int(sel["id_lancamento"])

        data_base = pd.to_datetime(sel["data"], errors="coerce")
        data_edit = st.date_input("Data", value=data_base.date() if pd.notna(data_base) else datetime.date.today(),
                                  format="DD/MM/YYYY", key="edit_data")

        tipo_opc = ["Entrada", "Saida"]
        tipo_e   = st.selectbox("Tipo", tipo_opc, index=tipo_opc.index(sel["tipo"]) if sel["tipo"] in tipo_opc else 0, key="edit_tipo")
        cat_e    = st.selectbox("Categoria", CATEGORIAS_ENTRADA,
                                index=CATEGORIAS_ENTRADA.index(sel["categoria"]) if sel["categoria"] in CATEGORIAS_ENTRADA else 0,
                                key="edit_cat") if tipo_e == "Entrada" else "Despesa"
        if tipo_e == "Saida":
            st.text_input("Categoria", value="Despesa", disabled=True, key="edit_cat_d")

        vinc_str   = str(sel["tipo_cadastro"]).strip().upper()
        vinc_pad_e = "Membro" if (tipo_e == "Entrada" and cat_e == "Dizimo") else "Fornecedor" if vinc_str == "FORNECEDOR" else "Membro" if vinc_str == "MEMBRO" else "Nenhum"
        vincular_e = st.selectbox("Vincular a", ["Nenhum", "Membro", "Fornecedor"],
                                  index=["Nenhum", "Membro", "Fornecedor"].index(vinc_pad_e), key="edit_vinc")

        id_e, nome_e, tipo_e2 = None, "", ""
        if vincular_e == "Membro" and not membros.empty:
            opc    = montar_opcoes(membros)
            chave  = encontrar_chave(opc, sel["id_cadastro"])
            chaves = list(opc.keys())
            esc    = st.selectbox("Membro", chaves, index=chaves.index(chave) if chave in chaves else 0, key="edit_mem")
            l = opc[esc]; id_e, nome_e, tipo_e2 = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
        elif vincular_e == "Fornecedor" and not fornec.empty:
            opc    = montar_opcoes(fornec)
            chave  = encontrar_chave(opc, sel["id_cadastro"])
            chaves = list(opc.keys())
            esc    = st.selectbox("Fornecedor", chaves, index=chaves.index(chave) if chave in chaves else 0, key="edit_forn")
            l = opc[esc]; id_e, nome_e, tipo_e2 = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
        else:
            st.text_input("Nome", value="", disabled=True, key="edit_nome_vazio")

        desc_e  = st.text_input("Descricao", value=str(sel["descricao"]), key="edit_desc")
        valor_e = st.number_input("Valor (R$)", min_value=0.0, value=float(sel["valor"]), step=0.01, format="%.2f", key="edit_val")

        st.divider()
        c1, c2 = st.columns(2)

        with c1:
            st.caption("Editar lancamento")
            if solicitar_autorizacao("salvar_lanc", "editar"):
                lanc = Lancamento(data=data_edit, tipo=tipo_e, categoria=cat_e,
                                  valor=valor_e, descricao=desc_e,
                                  id_cadastro=id_e, nome_cadastro=nome_e, tipo_cadastro=tipo_e2,
                                  id_lancamento=id_lanc)
                erros = lanc.validar()
                if erros:
                    for e in erros: st.error(e)
                else:
                    atualizar_lancamento(slug, lanc)
                    _invalida()
                    st.toast("Lancamento alterado!")
                    st.rerun()

        with c2:
            st.caption("Excluir lancamento")
            if solicitar_autorizacao("excluir_lanc", "excluir"):
                if confirmar_exclusao("del_lanc_final", "Confirmar exclusao"):
                    excluir_lancamento(slug, id_lanc)
                    _invalida()
                    st.toast("Excluido.")
                    st.rerun()
