import datetime
import streamlit as st
import pandas as pd

from data.models import Cadastro, limpar_documento
from data.repository import (
    carregar_cadastros, inserir_cadastro, atualizar_cadastro,
    excluir_cadastro, cadastro_em_uso, cpf_existe, LimiteMembrosExcedido,
)
from utils.helpers import confirmar_exclusao, slug_da_sessao, solicitar_autorizacao
from utils.planos import obter_plano, pode_cadastrar_membro, proximo_plano


FUNCOES = [
    "Membro", "Congregado", "Auxiliar", "Pastor", "Diacono", "Diaconisa",
    "Presbitero", "Evangelista", "Cooperador", "Dirigente",
    "Secretario", "Tesoureiro", "Professor", "Lider", "Missionário (a)", "",
]

SEXO_OPC = ["Masculino", "Feminino", ""]
TIPOS_CADASTRO = ["Membro", "Fornecedor"]


def _formatar_cpf(cpf):
    digits = "".join(c for c in cpf if c.isdigit())
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return cpf


def _formatar_cnpj(cnpj):
    digits = "".join(c for c in cnpj if c.isdigit())
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return cnpj


def _formatar_doc(doc, tipo):
    if tipo == "Fornecedor":
        return _formatar_cnpj(doc)
    return _formatar_cpf(doc)


def _formatar_cep(cep):
    digits = "".join(c for c in cep if c.isdigit())
    if len(digits) == 8:
        return f"{digits[:5]}-{digits[5:]}"
    return cep


def _formatar_tel(tel):
    digits = "".join(c for c in tel if c.isdigit())
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return tel


def _formatar_data(data_str):
    try:
        return datetime.date.fromisoformat(data_str).strftime("%d/%m/%Y")
    except Exception:
        return data_str


def _cache_key(slug):
    return f"df_cad_{slug}"


def _get(slug):
    k = _cache_key(slug)
    if k not in st.session_state:
        st.session_state[k] = carregar_cadastros(slug)
    return st.session_state[k]


def _invalida(slug):
    st.session_state.pop(_cache_key(slug), None)


def _val(row, col):
    v = row.get(col, "") if isinstance(row, dict) else getattr(row, col, "")
    return "" if pd.isna(v) else str(v).strip()


def _congregacao_da_sessao(slug, igreja):
    """
    Retorna o identificador/slug da igreja logada.
    """
    if not isinstance(igreja, dict):
        igreja = {}

    return str(
        igreja.get("identificador")
        or igreja.get("slug")
        or slug
        or ""
    ).strip()


def render():
    slug = slug_da_sessao()
    st.subheader("Membros e fornecedores")
    df = _get(slug)

    igreja = st.session_state.get("igreja", {})
    plano  = igreja.get("plano", "basico")
    p_info = obter_plano(plano)

    # Congregacao FIXA = identificador/slug da igreja logada
    congregacao_fixa = _congregacao_da_sessao(slug, igreja)

    if not df.empty and "tipo_cadastro" in df.columns:
        tipos = df["tipo_cadastro"].fillna("").astype(str).str.strip().str.upper()
        qtd_membros = len(df[tipos == "MEMBRO"])
    else:
        qtd_membros = 0

    limite    = p_info["limite_membros"]
    bloqueado = not pode_cadastrar_membro(plano, qtd_membros)

    if limite:
        pct = min(100, int((qtd_membros / limite) * 100))
        cor_barra = "#D85A30" if pct >= 90 else ("#F5A623" if pct >= 70 else "#1D9E75")
        st.markdown(f"""
        <div style="background:#f8f9fa;padding:10px 14px;border-radius:8px;margin-bottom:14px">
            <div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:4px">
                <span><b>Plano {p_info['nome']}:</b> {qtd_membros} de {limite} membros</span>
                <span style="color:{cor_barra};font-weight:600">{pct}%</span>
            </div>
            <div style="background:#e9ecef;height:6px;border-radius:3px;overflow:hidden">
                <div style="background:{cor_barra};height:100%;width:{pct}%"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Novo cadastro ────────────────────────────────────────────────────
    with st.expander("Novo cadastro", expanded=False):

        # >>> TIPO FORA DO FORM <<< — atualiza dinamicamente os outros campos
        st.markdown("**Dados principais**")
        if st.session_state.get("novo_tipo") not in TIPOS_CADASTRO:
            st.session_state.pop("novo_tipo", None)
        tipo = st.selectbox(
            "Tipo",
            TIPOS_CADASTRO,
            key="novo_tipo",
        )

        if tipo == "Membro" and bloqueado:
            st.error(
                f"⚠️ Voce atingiu o limite de **{limite} membros** do plano "
                f"**{p_info['nome']}**. Faca upgrade para "
                f"**{proximo_plano(plano).capitalize()}** para cadastrar mais membros."
            )
            st.info("Entre em contato com o administrador para upgrade do plano.")
        else:
            # Form com os demais campos
            with st.form("form_novo_cad", clear_on_submit=True):
                nome = st.text_input("Nome completo")

                doc_label       = "CPF *" if tipo == "Membro" else "CNPJ *"
                doc_placeholder = "000.000.000-00" if tipo == "Membro" else "00.000.000/0000-00"

                cpf = st.text_input(
                    doc_label,
                    placeholder=doc_placeholder,
                    help="Obrigatorio."
                )

                dt_nasc = st.date_input(
                    "Data de nascimento" if tipo == "Membro" else "Data de fundacao",
                    value=None,
                    format="DD/MM/YYYY",
                    key="novo_dt_nasc",
                    min_value=datetime.date(1900, 1, 1),
                    max_value=datetime.date.today(),
                )

                if tipo == "Membro":
                    sexo   = st.selectbox("Sexo", SEXO_OPC, key="novo_sexo")
                    funcao = st.selectbox("Funcao", FUNCOES, key="novo_funcao")
                else:
                    sexo, funcao = "", ""

                cong = congregacao_fixa

                st.text_input(
                    "Congregacao",
                    value=congregacao_fixa,
                    disabled=True,
                    key="novo_cong_fixo",
                    help="Definida automaticamente pelo identificador da igreja logada."
                )

                sit = st.selectbox("Situacao", ["Ativo", "Inativo"])

                st.markdown("**Contato**")
                telefone = st.text_input(
                    "Telefone / WhatsApp",
                    placeholder="(00) 00000-0000"
                )

                st.markdown("**Endereco**")
                col1, col2 = st.columns([3, 1])

                with col1:
                    logradouro = st.text_input(
                        "Rua / Avenida",
                        placeholder="Ex: Rua das Flores"
                    )

                with col2:
                    numero = st.text_input(
                        "Numero",
                        placeholder="123"
                    )

                bairro = st.text_input("Bairro", placeholder="Ex: Setor Central")

                col3, col4 = st.columns([2, 1])

                with col3:
                    cidade = st.text_input("Cidade", value="Minacu")

                with col4:
                    cep = st.text_input("CEP", value="76450-000")

                if st.form_submit_button("Salvar", type="primary"):
                    dn_str = dt_nasc.isoformat() if dt_nasc else ""

                    c = Cadastro(
                        nome=nome,
                        tipo_cadastro=tipo,
                        funcao=funcao,
                        congregacao=cong,
                        cpf=cpf,
                        situacao=sit,
                        data_nascimento=dn_str,
                        sexo=sexo,
                        telefone=telefone,
                        logradouro=logradouro,
                        numero=numero,
                        bairro=bairro,
                        cidade=cidade,
                        cep=cep,
                    )

                    erros = c.validar()

                    doc_limpo = limpar_documento(cpf)

                    if doc_limpo and cpf_existe(slug, doc_limpo):
                        doc_tipo = "CPF" if tipo == "Membro" else "CNPJ"
                        erros.append(doc_tipo + " ja cadastrado.")

                    if erros:
                        for e in erros:
                            st.error(e)
                    else:
                        try:
                            inserir_cadastro(slug, c)
                        except LimiteMembrosExcedido as ex:
                            st.error(str(ex))
                        else:
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

            for col in [
                "cpf", "cep", "telefone", "logradouro", "numero", "bairro",
                "cidade", "data_nascimento", "sexo"
            ]:
                if col not in df_view.columns:
                    df_view[col] = ""

            if "tipo_cadastro" in df_view.columns:
                df_view["cpf"] = df_view.apply(
                    lambda r: _formatar_doc(
                        str(r["cpf"]),
                        str(r["tipo_cadastro"])
                    ) if str(r["cpf"]).strip() else "",
                    axis=1,
                )
            else:
                df_view["cpf"] = df_view["cpf"].apply(
                    lambda x: _formatar_cpf(str(x)) if str(x).strip() else ""
                )

            df_view["cep"] = df_view["cep"].apply(
                lambda x: _formatar_cep(str(x)) if str(x).strip() else ""
            )

            df_view["telefone"] = df_view["telefone"].apply(
                lambda x: _formatar_tel(str(x)) if str(x).strip() else ""
            )

            df_view["data_nascimento"] = df_view["data_nascimento"].apply(
                lambda x: _formatar_data(str(x)) if str(x).strip() else ""
            )

            # Renomeia coluna para "Documento" (mais generico)
            df_view = df_view.rename(columns={"cpf": "documento"})

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

        rotulo = st.selectbox(
            "Selecione",
            df_r["rotulo"].tolist(),
            key="sel_cad_edit"
        )

        sel    = df_r[df_r["rotulo"] == rotulo].iloc[0]
        id_sel = int(sel["id_cadastro"])

        # CHAVE DINAMICA — quando muda a selecao, todos os widgets sao recriados
        kp = f"_edit_cad_{id_sel}_"

        st.markdown("**Dados principais**")

        tipo_opc = TIPOS_CADASTRO

        tipo_edit = st.selectbox(
            "Tipo",
            tipo_opc,
            index=tipo_opc.index(sel["tipo_cadastro"])
            if sel["tipo_cadastro"] in tipo_opc else 0,
            key=kp + "tipo"
        )

        nome_edit = st.text_input(
            "Nome completo",
            value=_val(sel, "nome"),
            key=kp + "nome"
        )

        cpf_atual         = _val(sel, "cpf")
        doc_label_e       = "CPF *" if tipo_edit == "Membro" else "CNPJ *"
        doc_placeholder_e = "000.000.000-00" if tipo_edit == "Membro" else "00.000.000/0000-00"

        cpf_edit = st.text_input(
            doc_label_e,
            value=_formatar_doc(cpf_atual, tipo_edit) if cpf_atual else "",
            placeholder=doc_placeholder_e,
            key=kp + "cpf",
            help="Obrigatorio.",
        )

        dn_atual = _val(sel, "data_nascimento")

        try:
            dn_value = datetime.date.fromisoformat(dn_atual) if dn_atual else None
        except Exception:
            dn_value = None

        dt_nasc_edit = st.date_input(
            "Data de nascimento" if tipo_edit == "Membro" else "Data de fundacao",
            value=dn_value,
            format="DD/MM/YYYY",
            key=kp + "dt_nasc",
            min_value=datetime.date(1900, 1, 1),
            max_value=datetime.date.today(),
        )

        if tipo_edit == "Membro":
            sexo_atual = _val(sel, "sexo")
            idx_sexo   = SEXO_OPC.index(sexo_atual) if sexo_atual in SEXO_OPC else 2

            sexo_edit = st.selectbox(
                "Sexo",
                SEXO_OPC,
                index=idx_sexo,
                key=kp + "sexo"
            )

            funcao_atual = _val(sel, "funcao")

            funcao_edit = st.selectbox(
                "Funcao",
                FUNCOES,
                index=FUNCOES.index(funcao_atual)
                if funcao_atual in FUNCOES else 0,
                key=kp + "funcao"
            )
        else:
            sexo_edit, funcao_edit = "", ""

        cong_edit = _val(sel, "congregacao") or congregacao_fixa

        st.text_input(
            "Congregacao",
            value=cong_edit,
            disabled=True,
            key=kp + "cong_fixo",
            help="Definida automaticamente pelo identificador da igreja logada."
        )

        sit_opc = ["Ativo", "Inativo"]

        sit_edit = st.selectbox(
            "Situacao",
            sit_opc,
            index=sit_opc.index(sel["situacao"])
            if sel["situacao"] in sit_opc else 0,
            key=kp + "sit"
        )

        st.markdown("**Contato**")

        tel_atual = _val(sel, "telefone")

        tel_edit = st.text_input(
            "Telefone / WhatsApp",
            value=_formatar_tel(tel_atual) if tel_atual else "",
            placeholder="(00) 00000-0000",
            key=kp + "tel"
        )

        st.markdown("**Endereco**")

        col1, col2 = st.columns([3, 1])

        with col1:
            log_edit = st.text_input(
                "Rua / Avenida",
                value=_val(sel, "logradouro"),
                key=kp + "log"
            )

        with col2:
            num_edit = st.text_input(
                "Numero",
                value=_val(sel, "numero"),
                key=kp + "num"
            )

        bai_edit = st.text_input(
            "Bairro",
            value=_val(sel, "bairro"),
            key=kp + "bai"
        )

        col3, col4 = st.columns([2, 1])

        with col3:
            cid_edit = st.text_input(
                "Cidade",
                value=_val(sel, "cidade"),
                key=kp + "cid"
            )

        with col4:
            cep_atual = _val(sel, "cep")
            cep_edit = st.text_input(
                "CEP",
                value=_formatar_cep(cep_atual) if cep_atual else "",
                key=kp + "cep"
            )

        st.divider()

        c1, c2 = st.columns(2)

        with c1:
            st.caption("Editar cadastro")

            if solicitar_autorizacao("salvar_cad", "editar"):
                dn_edit_str = dt_nasc_edit.isoformat() if dt_nasc_edit else ""

                c = Cadastro(
                    id_cadastro=id_sel,
                    nome=nome_edit,
                    tipo_cadastro=tipo_edit,
                    funcao=funcao_edit,
                    congregacao=cong_edit,
                    cpf=cpf_edit,
                    situacao=sit_edit,
                    data_nascimento=dn_edit_str,
                    sexo=sexo_edit,
                    telefone=tel_edit,
                    logradouro=log_edit,
                    numero=num_edit,
                    bairro=bai_edit,
                    cidade=cid_edit,
                    cep=cep_edit,
                )

                erros = c.validar()

                doc_limpo_e = limpar_documento(cpf_edit)

                if (
                    tipo_edit == "Membro"
                    and sel["tipo_cadastro"] != "Membro"
                    and bloqueado
                ):
                    erros.append(
                        f"O plano {p_info['nome']} atingiu o limite de membros."
                    )

                if doc_limpo_e and cpf_existe(slug, doc_limpo_e, id_excluir=id_sel):
                    doc_tipo_e = "CPF" if tipo_edit == "Membro" else "CNPJ"
                    erros.append(doc_tipo_e + " ja cadastrado em outro registro.")

                if erros:
                    for e in erros:
                        st.error(e)
                else:
                    try:
                        atualizar_cadastro(slug, c)
                    except LimiteMembrosExcedido as ex:
                        st.error(str(ex))
                    else:
                        _invalida(slug)

                        for k in list(st.session_state.keys()):
                            if k.startswith("_auth_") or k.startswith("_edit_cad_"):
                                st.session_state.pop(k, None)

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

                        for k in list(st.session_state.keys()):
                            if (
                                k.startswith("_auth_")
                                or k.startswith("_del_")
                                or k.startswith("_edit_cad_")
                                or k == "sel_cad_edit"
                            ):
                                st.session_state.pop(k, None)

                        st.toast("Excluido.")
                        st.rerun()
