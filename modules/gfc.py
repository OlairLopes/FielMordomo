import datetime

import pandas as pd
import streamlit as st

from data.repository import (
    excluir_gfc_grupo,
    excluir_gfc_reuniao,
    listar_gfc_grupos,
    listar_gfc_reunioes,
    salvar_gfc_grupo,
    salvar_gfc_reuniao,
)
from utils.helpers import gerar_csv, slug_da_sessao


TIPOS_CULTO_GFC = [
    "Culto Evangelístico",
    "Culto de Oração",
    "Culto Ação de Graças",
    "Vigília",
]


def _hoje():
    return datetime.date.today()


def _inicio_mes():
    return _hoje().replace(day=1)


def _fmt_data(valor):
    try:
        return datetime.date.fromisoformat(str(valor)).strftime("%d/%m/%Y")
    except Exception:
        return str(valor or "")


def _grupo_opcoes(grupos):
    return {
        f'{int(row["id_grupo"])} - {row["nome"]} ({row.get("setor", "") or "Sem setor"})': int(row["id_grupo"])
        for _, row in grupos.iterrows()
    }


def _render_grupos(slug):
    st.markdown("### Grupos Familiares")
    st.caption("Cadastre os grupos familiares de crescimento e seus setores.")

    grupos = listar_gfc_grupos(slug, incluir_inativos=True)

    with st.expander("Cadastrar grupo familiar", expanded=grupos.empty):
        with st.form("form_gfc_grupo"):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome do grupo familiar")
            setor = c2.text_input("Setor do grupo familiar")
            c3, c4 = st.columns(2)
            responsavel = c3.text_input("Responsável")
            telefone = c4.text_input("Telefone")
            observacoes = st.text_area("Observações")
            if st.form_submit_button("Salvar grupo", type="primary"):
                try:
                    salvar_gfc_grupo(
                        slug,
                        nome=nome,
                        setor=setor,
                        responsavel=responsavel,
                        telefone=telefone,
                        observacoes=observacoes,
                    )
                    st.success("Grupo familiar salvo.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if grupos.empty:
        st.info("Nenhum grupo familiar cadastrado ainda.")
        return

    exibir = grupos.copy()
    exibir["situação"] = exibir["ativo"].map({1: "Ativo", 0: "Inativo"})
    st.dataframe(
        exibir[["nome", "setor", "responsavel", "telefone", "situação", "observacoes"]],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Editar ou inativar grupo", expanded=False):
        opcoes = {
            f'{int(row["id_grupo"])} - {row["nome"]} ({row.get("setor", "") or "Sem setor"})': row
            for _, row in grupos.iterrows()
        }
        selecionado = st.selectbox("Grupo familiar", ["Selecione"] + list(opcoes.keys()))
        if selecionado != "Selecione":
            row = opcoes[selecionado]
            with st.form(f"form_editar_gfc_grupo_{int(row['id_grupo'])}"):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome do grupo familiar", value=str(row.get("nome", "") or ""))
                setor = c2.text_input("Setor do grupo familiar", value=str(row.get("setor", "") or ""))
                c3, c4 = st.columns(2)
                responsavel = c3.text_input("Responsável", value=str(row.get("responsavel", "") or ""))
                telefone = c4.text_input("Telefone", value=str(row.get("telefone", "") or ""))
                ativo = st.selectbox(
                    "Situação",
                    ["Ativo", "Inativo"],
                    index=0 if int(row.get("ativo", 1) or 0) == 1 else 1,
                )
                observacoes = st.text_area("Observações", value=str(row.get("observacoes", "") or ""))
                if st.form_submit_button("Atualizar grupo", type="primary"):
                    try:
                        salvar_gfc_grupo(
                            slug,
                            nome=nome,
                            setor=setor,
                            responsavel=responsavel,
                            telefone=telefone,
                            observacoes=observacoes,
                            ativo=ativo == "Ativo",
                            id_grupo=int(row["id_grupo"]),
                        )
                        st.success("Grupo familiar atualizado.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

            if st.button("Inativar/excluir grupo", key=f"gfc_excluir_grupo_{int(row['id_grupo'])}"):
                removido = excluir_gfc_grupo(slug, int(row["id_grupo"]))
                st.success("Grupo excluído." if removido else "Grupo inativado porque possui histórico.")
                st.rerun()


def _render_reunioes(slug):
    st.markdown("### Registro de Culto GFC")
    grupos = listar_gfc_grupos(slug)
    if grupos.empty:
        st.warning("Cadastre ao menos um grupo familiar ativo antes de registrar o culto.")
        return

    reunioes_salvas = listar_gfc_reunioes(slug)
    modo = st.radio(
        "Modo",
        ["Novo registro", "Editar registro salvo"] if not reunioes_salvas.empty else ["Novo registro"],
        horizontal=True,
        key="gfc_modo_reuniao",
    )

    reuniao_atual = None
    if modo == "Editar registro salvo":
        c_ini, c_fim = st.columns(2)
        inicio = c_ini.date_input(
            "Data inicial para localizar registro",
            value=_inicio_mes(),
            key="gfc_edit_ini",
            format="DD/MM/YYYY",
        )
        fim = c_fim.date_input(
            "Data final para localizar registro",
            value=_hoje(),
            key="gfc_edit_fim",
            format="DD/MM/YYYY",
        )
        if inicio > fim:
            st.error("A data inicial não pode ser maior que a data final.")
            return
        reunioes_salvas = listar_gfc_reunioes(slug, inicio.isoformat(), fim.isoformat())
        if reunioes_salvas.empty:
            st.info("Nenhum registro encontrado no período selecionado.")
            return
        opcoes_reg = {
            f'{int(row["id_reuniao"])} - {_fmt_data(row["data"])} - {row["grupo"]} - {row["tipo_culto"]}': row
            for _, row in reunioes_salvas.iterrows()
        }
        labels = list(opcoes_reg.keys())
        chave = "gfc_editar_reuniao"
        if st.session_state.get(chave) not in labels:
            st.session_state[chave] = labels[0]
        idx_atual = labels.index(st.session_state[chave])
        nav_ant, nav_sel, nav_seg = st.columns([1, 3, 1])
        if nav_ant.button(
            "Dia anterior",
            use_container_width=True,
            disabled=idx_atual >= len(labels) - 1,
            key="gfc_reuniao_anterior",
        ):
            st.session_state[chave] = labels[idx_atual + 1]
        if nav_seg.button(
            "Dia seguinte",
            use_container_width=True,
            disabled=idx_atual <= 0,
            key="gfc_reuniao_seguinte",
        ):
            st.session_state[chave] = labels[idx_atual - 1]
        with nav_sel:
            selecionado = st.selectbox("Registro salvo", labels, key=chave)
        reuniao_atual = opcoes_reg[selecionado]
        data_padrao = datetime.date.fromisoformat(str(reuniao_atual["data"]))
    else:
        data_padrao = _hoje()

    op_grupos = _grupo_opcoes(grupos)
    grupo_index = 0
    if reuniao_atual is not None:
        id_atual = int(reuniao_atual.get("id_grupo", 0) or 0)
        for idx, label in enumerate(op_grupos):
            if op_grupos[label] == id_atual:
                grupo_index = idx
                break

    with st.form("form_gfc_reuniao"):
        c1, c2 = st.columns(2)
        data = c1.date_input("Data", value=data_padrao, format="DD/MM/YYYY")
        grupo_label = c2.selectbox("Grupo familiar", list(op_grupos.keys()), index=grupo_index)
        grupo_row = grupos[grupos["id_grupo"].astype(int) == int(op_grupos[grupo_label])].iloc[0]
        setor = str(grupo_row.get("setor", "") or "")
        st.text_input("Setor do grupo familiar", value=setor, disabled=True)

        tipo_atual = (
            str(reuniao_atual.get("tipo_culto", TIPOS_CULTO_GFC[0]))
            if reuniao_atual is not None
            else TIPOS_CULTO_GFC[0]
        )
        tipo_idx = TIPOS_CULTO_GFC.index(tipo_atual) if tipo_atual in TIPOS_CULTO_GFC else 0
        tipo_culto = st.selectbox("Tipo de culto", TIPOS_CULTO_GFC, index=tipo_idx)
        tema = st.text_input(
            "Tema/observação breve",
            value=str(reuniao_atual.get("tema", "") or "") if reuniao_atual is not None else "",
        )

        c3, c4, c5 = st.columns(3)
        qtd_pessoas = c3.number_input(
            "Quantidade de pessoas",
            min_value=0,
            step=1,
            value=int(reuniao_atual.get("qtd_pessoas", 0) or 0) if reuniao_atual is not None else 0,
        )
        qtd_nao_crentes = c4.number_input(
            "Quantidade de pessoas não crentes",
            min_value=0,
            step=1,
            value=int(reuniao_atual.get("qtd_nao_crentes", 0) or 0) if reuniao_atual is not None else 0,
        )
        qtd_conversoes = c5.number_input(
            "Quantidade de conversões a Cristo",
            min_value=0,
            step=1,
            value=int(reuniao_atual.get("qtd_conversoes", 0) or 0) if reuniao_atual is not None else 0,
        )
        observacoes = st.text_area(
            "Observações",
            value=str(reuniao_atual.get("observacoes", "") or "") if reuniao_atual is not None else "",
        )

        if st.form_submit_button("Salvar registro GFC", type="primary"):
            try:
                salvar_gfc_reuniao(
                    slug,
                    data=data.isoformat(),
                    id_grupo=op_grupos[grupo_label],
                    tipo_culto=tipo_culto,
                    tema=tema,
                    qtd_pessoas=qtd_pessoas,
                    qtd_nao_crentes=qtd_nao_crentes,
                    qtd_conversoes=qtd_conversoes,
                    observacoes=observacoes,
                    id_reuniao=int(reuniao_atual["id_reuniao"]) if reuniao_atual is not None else None,
                )
                st.success("Registro GFC salvo.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _render_relatorios(slug):
    st.markdown("### Relatórios GFC")
    c1, c2, c3 = st.columns(3)
    inicio = c1.date_input("Data inicial", value=_inicio_mes(), key="gfc_rel_ini", format="DD/MM/YYYY")
    fim = c2.date_input("Data final", value=_hoje(), key="gfc_rel_fim", format="DD/MM/YYYY")
    tipo = c3.selectbox("Tipo de culto", ["Todos"] + TIPOS_CULTO_GFC, key="gfc_rel_tipo")

    grupos = listar_gfc_grupos(slug, incluir_inativos=True)
    setores = sorted([
        s for s in grupos["setor"].fillna("").astype(str).str.strip().unique().tolist()
        if s
    ]) if not grupos.empty else []
    setor = st.selectbox("Setor", ["Todos"] + setores, key="gfc_rel_setor")

    if inicio > fim:
        st.error("A data inicial não pode ser maior que a data final.")
        return

    reunioes = listar_gfc_reunioes(
        slug,
        inicio.isoformat(),
        fim.isoformat(),
        setor="" if setor == "Todos" else setor,
        tipo_culto="" if tipo == "Todos" else tipo,
    )

    if reunioes.empty:
        st.info("Nenhum registro GFC encontrado no período.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cultos registrados", int(reunioes["id_reuniao"].nunique()))
    m2.metric("Pessoas", int(pd.to_numeric(reunioes["qtd_pessoas"], errors="coerce").fillna(0).sum()))
    m3.metric("Não crentes", int(pd.to_numeric(reunioes["qtd_nao_crentes"], errors="coerce").fillna(0).sum()))
    m4.metric("Conversões", int(pd.to_numeric(reunioes["qtd_conversoes"], errors="coerce").fillna(0).sum()))

    tabela = reunioes.copy()
    tabela["data"] = tabela["data"].apply(_fmt_data)
    tabela = tabela.rename(columns={
        "data": "Data",
        "grupo": "Grupo familiar",
        "setor": "Setor",
        "tipo_culto": "Tipo de culto",
        "tema": "Tema",
        "qtd_pessoas": "Pessoas",
        "qtd_nao_crentes": "Não crentes",
        "qtd_conversoes": "Conversões",
        "observacoes": "Observações",
    })
    st.dataframe(
        tabela[[
            "Data", "Grupo familiar", "Setor", "Tipo de culto", "Tema",
            "Pessoas", "Não crentes", "Conversões", "Observações",
        ]],
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Baixar relatório GFC CSV",
        data=gerar_csv(tabela),
        file_name="relatorio_gfc.csv",
        mime="text/csv",
    )

    with st.expander("Excluir registro GFC", expanded=False):
        opcoes = {
            f'{int(row["id_reuniao"])} - {_fmt_data(row["data"])} - {row["grupo"]} - {row["tipo_culto"]}': int(row["id_reuniao"])
            for _, row in reunioes.iterrows()
        }
        escolha = st.selectbox("Registro", ["Selecione"] + list(opcoes.keys()), key="gfc_excluir_reuniao")
        if escolha != "Selecione" and st.button("Excluir registro selecionado", type="primary"):
            excluir_gfc_reuniao(slug, opcoes[escolha])
            st.success("Registro excluído.")
            st.rerun()


def render():
    slug = slug_da_sessao()
    st.subheader("GFC - Grupos Familiares de Crescimento")
    st.caption("Primeira etapa: cadastro dos grupos, registro dos cultos e relatório básico.")

    tab_grupos, tab_reunioes, tab_relatorios = st.tabs([
        "Grupos",
        "Registro de culto",
        "Relatórios",
    ])

    with tab_grupos:
        _render_grupos(slug)
    with tab_reunioes:
        _render_reunioes(slug)
    with tab_relatorios:
        _render_relatorios(slug)
