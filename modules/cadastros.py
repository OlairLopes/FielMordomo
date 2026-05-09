"import datetime
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
    "Centro",
    "Nova Esperança",
    "Jardim Arimatéia",
    "Jardim Boa Vista",
    "Jardim Brasil",
    "Jardim Emília",
    "Jardim Floresta",
    "Jardim Floresta II",
    "Conj. Hab. Primavera",
    "Minaçu Norte",
    "Patrimônio do Trevo",
    "Patrimônio do Vicente",
    "Residencial Cana Brava",
    "Residencial Tocantins",
    "Marajoara",
    "Serrinha",
    "Vila Batista",
    "Vila Residencial Sama",
    "Vila de Furnas",
    "Vila de Malta",
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
