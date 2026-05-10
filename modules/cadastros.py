import datetime
import streamlit as st
import pandas as pd

from data.models import Cadastro
from data.repository import (
    carregar_cadastros, inserir_cadastro, atualizar_cadastro,
    excluir_cadastro, cadastro_em_uso, cpf_existe,
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
    "",
]

BAIRROS_MINACU = [
    "Setor Central",
    "Nova Esperança",
    "Jardim Arimatéia",
    "Jardim Boa Vista",
    "Jardim Brasil",
    "Jardim Emília",
    "Jardim Floresta", 
    "Jardim Floresta  II",
    "Habitacional Primavera",
    "Minaçu Norte",
    "Patrimônio do Trevo", 
    "Patrimônio do Vicente",
    "Residencial Cana Brava",
    "Residencial Tocantins",
    "Marajoara",
    "Setor Serrinha",
    "Vila Batista",
    "Vila Residencial Sama",
    "Vila de Furnas",
    "Vila de Malta"
    "Vila Manchester",
    "Vila Menezes",
    "Vila Moraes",
    "Vila São Geraldo",
    "Vila União",
    "Wilson Vaz",
    "",
]


def _formatar_cpf(cpf: str) -> str:
    digits = "".join(c for c in cpf if c.isdigit())
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return cpf


def _formatar_cnpj(cnpj: str) -> str:
    digits = "".join(c for c in cnpj if c.isdigit())
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return cnpj


def _formatar_doc(doc: str, tipo: str) -> str:
    if tipo == "Fornecedor":
        return _formatar_cnpj(doc)
    return _formatar_cpf(doc)


def _formatar_cep(cep: str) -> str:
    digits = "".join(c for c in cep if c.isdigit())
    if len(digits) == 8:
        return f"{digits[:5]}-{digits[5:]}"
    return cep


def _formatar_tel(tel: str) -> str:
    digits = "".join(c for c in tel if c.isdigit())
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return tel


def _formatar_data(data_str: str) -> str:
    try:
        return datetime.date.fromisoformat(data_str).strftime("%d/%m/%Y")
    except Exception:
        return data_str


def _cache_key():
    return f"df_cad_{slug_da_sessao()}"


def _get(slug):
    k = _cache_key()
    if k not in st.session_state:
        st.session_state[k] = carregar_cadastros(slug)
    return st.session_state[k]


def _invalida(slug):
    st.session_state.pop(_cache_key(), None)


def _val(row, col):
    v = row.get(col, "") if isinstance(row, dict) else getattr(row, col, "")
    return str(v).strip() if v else ""


def render():
    slug = slug_da_sessao()
    st.subheader("Membros e fornecedores")
    df = _get(slug)

    # ── Novo cadastro ────────────────────────────────────────────────────
    with st.expander("Novo cadastro", expanded=False):
        with st.form("form_novo_cad", clear_on_submit=True):
            st.markdown("**Dados principais**")
            tipo   = st.selectbox("Tipo", ["Membro", "Fornecedor"])
            nome   = st.text_input("Nome completo")

            doc_label       = "CPF *" if tipo == "Membro" else "CNPJ *"
            doc_placeholder = "000.000.000-00" if tipo == "Membro" else "00.000.000/0000-00"
            cpf = st.text_input(
                doc_label,
                placeholder=doc_placeholder,
                help="Obrigatorio.",
            )

            dt_nasc = st.date_input(
                "Data de nascimento",
                value=None,
                format="DD/MM/YYYY",
                key="novo_dt_nasc",
                min_value=datetime.date(1900, 1, 1),
                max_value=datetime.date.today(),
            )
            funcao = st.selectbox("Funcao", FUNCOES) if tipo == "Membro" else ""
            cong   = st.selectbox("Congregacao", CONGREGACOES)
            sit    = st.selectbox("Situacao", ["Ativo", "Inativo"])

            st.markdown("**Contato**")
            telefone = st.text_input("Telefone / WhatsApp", placeholder="(00) 00000-0000")

            st.markdown("**Endereco**")
            col1, col2 = st.columns([3, 1])
            with col1:
                logradouro = st.text_input("Rua / Avenida", placeholder="Ex: Rua das Flores")
            with col2:
                numero = st.text_input("Numero", placeholder="123")

            bairro = st.selectbox("Bairro", BAIRROS_MINACU)
            col3, col4 = st.columns([2, 1])
            with col3:
                cidade = st.text_input("Cidade")
            with col4:
                cep = st.text_input("CEP", placeholder="00000-000")

            if st.form_submit_button("Salvar", type="primary"):
                dn_str = dt_nasc.isoformat() if dt_nasc else ""
                c = Cadastro(
                    nome=nome, tipo_cadastro=tipo, funcao=funcao,
                    congregacao=cong, cpf=cpf, situacao=sit,
                    data_nascimento=dn_str,
                    telefone=telefone, logradouro=logradouro,
                    numero=numero, bairro=bairro,
                    cidade=cidade, cep=cep,
                )
                erros = c.validar()
                doc_limpo = "".join(d for d in cpf if d.isdigit())
                if doc_limpo and cpf_existe(slug, doc_limpo):
                    doc_tipo = "CPF" if tipo == "Membro" else "CNPJ"
                    erros.append(doc_tipo + " ja cadastrado. Verifique se este cadastro ja existe.")
                if erros:
                    for e in erros: st.error(e)
                else:
                    inserir_cadastro(slug, c)
                    _invalida(slug)
                    st.toast("Cadastro salvo!")
                    st.rerun()

    # ── Tabela ────────────────────────────────────────────────────────────
    total = len(df)
    with st.expander(f"Ver cadastros ({total} registros)", expanded=False):
        if df.empty:
            st.info("Nenhum cadastro ainda.")
        else:
            df_view = df.copy()
            for col in ["cpf","cep","telefone","logradouro","numero","bairro","cidade","data_nascimento"]:
                if col not in df_view.columns:
                    df_view[col] = ""
            if "tipo_cadastro" in df_view.columns:
                df_view["cpf"] = df_view.apply(
                    lambda r: _formatar_doc(str(r["cpf"]), str(r["tipo_cadastro"])) if str(r["cpf"]).strip() else "",
                    axis=1,
                )
            else:
                df_view["cpf"] = df_view["cpf"].apply(lambda x: _formatar_cpf(str(x)) if str(x).strip() else "")
            df_view["cep"]             = df_view["cep"].apply(lambda x: _formatar_cep(str(x)) if str(x).strip() else "")
            df_view["telefone"]        = df_view["telefone"].apply(lambda x: _formatar_tel(str(x)) if str(x).strip() else "")
            df_view["data_nascimento"] = df_view["data_nascimento"].apply(lambda x: _formatar_data(str(x)) if str(x).strip() else "")
            st.dataframe(df_view, use_container_width=True)

    # ── Editar / Excluir ──────────────────────────────────────────────────
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

        st.markdown("**Dados principais**")
        tipo_opc  = ["Membro", "Fornecedor"]
        tipo_edit = st.selectbox("Tipo", tipo_opc,
                                 index=tipo_opc.index(sel["tipo_cadastro"]) if sel["tipo_cadastro"] in tipo_opc else 0,
                                 key="e_tipo")
        nome_edit = st.text_input("Nome completo", value=_val(sel, "nome"), key="e_nome")

        cpf_atual         = _val(sel, "cpf")
        doc_label_e       = "CPF *" if tipo_edit == "Membro" else "CNPJ *"
        doc_placeholder_e = "000.000.000-00" if tipo_edit == "Membro" else "00.000.000/0000-00"
        cpf_edit = st.text_input(
            doc_label_e,
            value=_formatar_doc(cpf_atual, tipo_edit) if cpf_atual else "",
            placeholder=doc_placeholder_e,
            key="e_cpf",
            help="Obrigatorio.",
        )

        dn_atual = _val(sel, "data_nascimento")
        try:
            dn_value = datetime.date.fromisoformat(dn_atual) if dn_atual else None
        except Exception:
            dn_value = None
        dt_nasc_edit = st.date_input(
            "Data de nascimento",
            value=dn_value,
            format="DD/MM/YYYY",
            key="e_dt_nasc",
            min_value=datetime.date(1900, 1, 1),
            max_value=datetime.date.today(),
        )

        funcao_edit = (
            st.selectbox("Funcao", FUNCOES,
                         index=FUNCOES.index(_val(sel,"funcao")) if _val(sel,"funcao") in FUNCOES else 0,
                         key="e_funcao")
            if tipo_edit == "Membro" else ""
        )

        cong_atual = _val(sel, "congregacao")
        idx_cong   = CONGREGACOES.index(cong_atual) if cong_atual in CONGREGACOES else 0
        cong_edit  = st.selectbox("Congregacao", CONGREGACOES, index=idx_cong, key="e_cong")

        sit_opc  = ["Ativo", "Inativo"]
        sit_edit = st.selectbox("Situacao", sit_opc,
                                index=sit_opc.index(sel["situacao"]) if sel["situacao"] in sit_opc else 0,
                                key="e_sit")

        st.markdown("**Contato**")
        tel_atual = _val(sel, "telefone")
        tel_edit  = st.text_input("Telefone / WhatsApp",
                                   value=_formatar_tel(tel_atual) if tel_atual else "",
                                   placeholder="(00) 00000-0000", key="e_tel")

        st.markdown("**Endereco**")
        col1, col2 = st.columns([3, 1])
        with col1:
            log_edit = st.text_input("Rua / Avenida", value=_val(sel, "logradouro"), key="e_log")
        with col2:
            num_edit = st.text_input("Numero", value=_val(sel, "numero"), key="e_num")

        bairro_atual = _val(sel, "bairro")
        idx_bairro   = BAIRROS_MINACU.index(bairro_atual) if bairro_atual in BAIRROS_MINACU else 0
        bai_edit     = st.selectbox("Bairro", BAIRROS_MINACU, index=idx_bairro, key="e_bai")

        col3, col4 = st.columns([2, 1])
        with col3:
            cid_edit = st.text_input("Cidade", value=_val(sel, "cidade"), key="e_cid")
        with col4:
            cep_atual = _val(sel, "cep")
            cep_edit  = st.text_input("CEP",
                                       value=_formatar_cep(cep_atual) if cep_atual else "",
                                       placeholder="00000-000", key="e_cep")

        st.divider()
        c1, c2 = st.columns(2)

        with c1:
            st.caption("Editar cadastro")
            if solicitar_autorizacao("salvar_cad", "editar"):
                dn_edit_str = dt_nasc_edit.isoformat() if dt_nasc_edit else ""
                c = Cadastro(
                    id_cadastro=id_sel, nome=nome_edit, tipo_cadastro=tipo_edit,
                    funcao=funcao_edit, congregacao=cong_edit,
                    cpf=cpf_edit, situacao=sit_edit,
                    data_nascimento=dn_edit_str,
                    telefone=tel_edit, logradouro=log_edit,
                    numero=num_edit, bairro=bai_edit,
                    cidade=cid_edit, cep=cep_edit,
                )
                erros = c.validar()
                doc_limpo_e = "".join(d for d in cpf_edit if d.isdigit())
                if doc_limpo_e and cpf_existe(slug, doc_limpo_e, id_excluir=id_sel):
                    doc_tipo_e = "CPF" if tipo_edit == "Membro" else "CNPJ"
                    erros.append(doc_tipo_e + " ja cadastrado em outro registro.")
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
