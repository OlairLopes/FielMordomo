import datetime

import pandas as pd
import streamlit as st

from data.repository import (
    excluir_visitante_culto,
    listar_visitantes_cultos,
    salvar_visitante_culto,
)
from utils.helpers import confirmar_exclusao, gerar_csv, slug_da_sessao


ESTADOS_BR = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
]

DEPARTAMENTOS_CULTO = [
    "Conscientização Missionária",
    "Consagração",
    "Culto de Ensino",
    "Culto Ministério de Homens",
    "Culto Ministério Família",
    "Culto Ministério Infantil",
    "Culto Ministério Jovens",
    "Culto Ministério Missões",
    "Culto Ministério Mulheres",
    "Dia com Deus",
    "Encontro Unificado",
    "Escola Bíblica",
    "Fraternal",
    "Outros",
    "Vigília",
]


def _hoje():
    return datetime.date.today()


def _inicio_mes():
    hoje = _hoje()
    return hoje.replace(day=1)


def _fmt_data(valor):
    try:
        return datetime.date.fromisoformat(str(valor)).strftime("%d/%m/%Y")
    except Exception:
        return str(valor or "")


def _sim_nao(valor):
    return "Sim" if bool(valor) else "Não"


def _totais(df):
    if df.empty:
        return {
            "visitantes": 0,
            "crentes": 0,
            "nao_crentes": 0,
            "apresentar": 0,
            "oracao": 0,
        }
    return {
        "visitantes": int(len(df)),
        "crentes": int((df["tipo_visitante"] == "Crente").sum()),
        "nao_crentes": int((df["tipo_visitante"] == "Nao crente").sum()),
        "apresentar": int(df["deseja_ser_apresentado"].fillna(0).astype(int).sum()),
        "oracao": int(df["deseja_oracao_final"].fillna(0).astype(int).sum()),
    }


def _render_formulario(slug):
    st.markdown("### Registrar visitante")
    st.caption("Registre visitantes recebidos nos cultos e departamentos da igreja.")

    with st.form("form_registro_visitante"):
        c1, c2 = st.columns(2)
        c1.text_input("Identificador da igreja", value=slug, disabled=True)
        data = c2.date_input("Data", value=_hoje())

        departamento_opcao = st.selectbox(
            "Departamento na direcao do culto",
            DEPARTAMENTOS_CULTO,
            index=0,
        )
        departamento = departamento_opcao
        if departamento_opcao == "Outros":
            departamento = st.text_input(
                "Informe o departamento",
                placeholder="Ex.: Ministerio de louvor, familia, adolescentes...",
            )
        nome_visitante = st.text_input("Nome do visitante")

        crente = st.radio(
            "Tipo de visitante: é crente?",
            ["Sim", "Não"],
            horizontal=True,
        )
        tipo_visitante = "Crente" if crente == "Sim" else "Nao crente"

        igreja_origem = ""
        cidade = ""
        estado = ""
        denominacao = ""

        if tipo_visitante == "Crente":
            st.markdown("#### Dados da igreja de origem")
            c3, c4, c5 = st.columns([2, 1.4, 1])
            igreja_origem = c3.text_input("De qual igreja?")
            cidade = c4.text_input("Qual cidade?")
            estado = c5.selectbox("Qual estado?", ["Selecione"] + ESTADOS_BR)
            estado = "" if estado == "Selecione" else estado
        else:
            denominacao = st.text_input(
                "Pertence a qual denominação?",
                placeholder="Ex.: Católica, Assembleia de Deus, sem denominação...",
            )

        c6, c7 = st.columns(2)
        deseja_ser_apresentado = c6.checkbox("Deseja ser apresentado?")
        deseja_oracao_final = c7.checkbox("Deseja receber oração ao final do culto?")
        observacoes = st.text_area("Observações", placeholder="Opcional")

        if st.form_submit_button("Salvar visitante", type="primary"):
            try:
                salvar_visitante_culto(
                    slug,
                    data.isoformat(),
                    departamento,
                    nome_visitante,
                    tipo_visitante,
                    igreja_origem,
                    cidade,
                    estado,
                    denominacao,
                    deseja_ser_apresentado,
                    deseja_oracao_final,
                    observacoes,
                )
                st.success("Visitante registrado com sucesso.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _render_consulta(slug):
    st.markdown("### Visitantes registrados")
    c1, c2, c3 = st.columns(3)
    inicio = c1.date_input("Data inicial", value=_inicio_mes(), key="visitantes_ini")
    fim = c2.date_input("Data final", value=_hoje(), key="visitantes_fim")
    departamento = c3.text_input("Filtrar departamento", placeholder="Opcional")
    if inicio > fim:
        st.error("A data inicial não pode ser maior que a data final.")
        return

    df = listar_visitantes_cultos(
        slug,
        inicio.isoformat(),
        fim.isoformat(),
        departamento.strip(),
    )
    totais = _totais(df)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Visitantes", totais["visitantes"])
    m2.metric("Crentes", totais["crentes"])
    m3.metric("Não crentes", totais["nao_crentes"])
    m4.metric("Apresentar", totais["apresentar"])
    m5.metric("Oração final", totais["oracao"])

    if df.empty:
        st.info("Nenhum visitante encontrado no período selecionado.")
        return

    exibir = df.copy()
    exibir["data"] = exibir["data"].apply(_fmt_data)
    exibir["deseja_ser_apresentado"] = exibir["deseja_ser_apresentado"].apply(_sim_nao)
    exibir["deseja_oracao_final"] = exibir["deseja_oracao_final"].apply(_sim_nao)
    st.dataframe(
        exibir[[
            "data", "departamento", "nome_visitante", "tipo_visitante",
            "igreja_origem", "cidade", "estado", "denominacao",
            "deseja_ser_apresentado", "deseja_oracao_final", "observacoes",
        ]],
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Baixar visitantes CSV",
        data=gerar_csv(df),
        file_name="visitantes_cultos.csv",
        mime="text/csv",
    )

    excluir = st.selectbox(
        "Excluir registro",
        ["Selecione"] + [
            f'{int(row["id_visitante"])} - {_fmt_data(row["data"])} - {row["nome_visitante"]}'
            for _, row in df.iterrows()
        ],
    )
    if excluir != "Selecione" and confirmar_exclusao(
        f"excluir_visitante_{excluir}",
        "Excluir registro selecionado",
    ):
        excluir_visitante_culto(slug, int(excluir.split(" - ")[0]))
        st.success("Registro excluído.")
        st.rerun()


def render():
    st.subheader("Registro de Visitantes")
    slug = slug_da_sessao()
    if not slug:
        st.error("Sessão inválida. Faça login novamente.")
        return

    tab_form, tab_consulta = st.tabs(["Registrar visitante", "Consultar registros"])
    with tab_form:
        _render_formulario(slug)
    with tab_consulta:
        _render_consulta(slug)
