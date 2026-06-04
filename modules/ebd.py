import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.repository import (
    carregar_cadastros,
    encerrar_ebd_matricula,
    excluir_ebd_classe,
    excluir_ebd_escala,
    listar_ebd_aulas,
    listar_ebd_classes,
    listar_ebd_escala,
    listar_ebd_matriculas,
    relatorio_ebd_frequencia,
    relatorio_ebd_resumo_classes,
    salvar_ebd_chamada,
    salvar_ebd_classe,
    salvar_ebd_escala,
    salvar_ebd_matricula,
)
from utils.helpers import confirmar_exclusao, gerar_csv, slug_da_sessao


CORES = {
    "verde": "#1D9E75",
    "azul": "#0F3D5E",
    "laranja": "#F59E0B",
    "vermelho": "#DC2626",
    "cinza": "#64748B",
}
CONFIG_PLOTLY = {"displayModeBar": False, "responsive": True}


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


def _pct(valor):
    try:
        return f"{float(valor):.1f}%"
    except Exception:
        return "0.0%"


def _metricas_ebd(resumo, aulas):
    alunos = int(resumo["alunos"].sum()) if not resumo.empty else 0
    classes = int(resumo["classe"].nunique()) if not resumo.empty else 0
    qtd_aulas = int(aulas["id_aula"].nunique()) if not aulas.empty else 0
    presencas = float(resumo["presencas"].sum()) if not resumo.empty else 0
    faltas = float(resumo["faltas"].sum()) if not resumo.empty else 0
    freq = (presencas / (presencas + faltas) * 100) if (presencas + faltas) else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Classes acompanhadas", classes)
    c2.metric("Alunos no relatorio", alunos)
    c3.metric("Aulas registradas", qtd_aulas)
    c4.metric("Frequencia media", _pct(freq))


def _grafico_frequencia_classes(resumo):
    if resumo.empty:
        st.info("Sem dados de frequencia para o periodo selecionado.")
        return
    dados = resumo.sort_values("frequencia_pct", ascending=True)
    fig = go.Figure(go.Bar(
        name="Frequencia",
        x=dados["frequencia_pct"],
        y=dados["classe"],
        orientation="h",
        marker_color=CORES["verde"],
        text=[_pct(v) for v in dados["frequencia_pct"]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Frequencia: %{x:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        height=max(360, 70 * len(dados)),
        margin=dict(t=35, b=40, l=20, r=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(range=[0, 105], title="Frequencia (%)", fixedrange=True),
        yaxis=dict(title="", fixedrange=True),
        showlegend=True,
        legend=dict(orientation="h", y=1.12, x=0),
    )
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


def _classes_opcoes(df_classes):
    return {
        f'{int(row["id_classe"])} - {row["nome"]}': int(row["id_classe"])
        for _, row in df_classes.iterrows()
    }


def _membros_opcoes(slug):
    df = carregar_cadastros(slug)
    if df.empty:
        return {}, df
    membros = df[
        (df["tipo_cadastro"].astype(str).str.upper() == "MEMBRO")
        & (df["situacao"].astype(str).str.upper() == "ATIVO")
    ].copy()
    membros = membros.sort_values("nome")
    opcoes = {
        f'{int(row["id_cadastro"])} - {row["nome"]}': int(row["id_cadastro"])
        for _, row in membros.iterrows()
    }
    return opcoes, membros


def _render_classes(slug):
    st.markdown("### Classes e alunos")
    df_classes = listar_ebd_classes(slug, incluir_inativas=True)

    with st.expander("Cadastrar ou atualizar classe", expanded=df_classes.empty):
        editar = None
        if not df_classes.empty:
            op_edicao = {"Nova classe": None}
            op_edicao.update(_classes_opcoes(df_classes))
            escolha = st.selectbox("Editar classe existente", list(op_edicao.keys()))
            editar = op_edicao[escolha]
        row = {}
        if editar:
            row = df_classes[df_classes["id_classe"] == editar].iloc[0].to_dict()

        with st.form("form_ebd_classe"):
            nome = st.text_input("Nome da classe", value=row.get("nome", ""))
            c1, c2, c3 = st.columns(3)
            faixa = c1.text_input("Faixa etaria", value=row.get("faixa_etaria", ""))
            professor = c2.text_input("Professor principal", value=row.get("professor_principal", ""))
            sala = c3.text_input("Sala/local", value=row.get("sala", ""))
            ativa = st.checkbox("Classe ativa", value=bool(row.get("ativa", 1)))
            obs = st.text_area("Observacoes", value=row.get("observacoes", ""))
            if st.form_submit_button("Salvar classe", type="primary"):
                try:
                    salvar_ebd_classe(slug, nome, faixa, professor, sala, obs, ativa, editar)
                    st.success("Classe salva com sucesso.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    df_classes_ativas = listar_ebd_classes(slug)
    if df_classes_ativas.empty:
        st.info("Cadastre ao menos uma classe para matricular alunos e registrar chamadas.")
        return

    st.markdown("#### Matricular alunos")
    op_classes = _classes_opcoes(df_classes_ativas)
    classe_label = st.selectbox("Classe", list(op_classes.keys()), key="matricula_classe")
    id_classe = op_classes[classe_label]
    op_membros, df_membros = _membros_opcoes(slug)

    with st.form("form_ebd_matricula"):
        modo = st.radio("Origem do aluno", ["Membro cadastrado", "Nome manual"], horizontal=True)
        id_cadastro = None
        nome_manual = ""
        if modo == "Membro cadastrado":
            if op_membros:
                membro_label = st.selectbox("Membro", list(op_membros.keys()))
                id_cadastro = op_membros[membro_label]
                nome_aluno = df_membros[df_membros["id_cadastro"] == id_cadastro].iloc[0]["nome"]
            else:
                nome_aluno = ""
                st.warning("Nao ha membros ativos cadastrados.")
        else:
            nome_manual = st.text_input("Nome do aluno")
            nome_aluno = nome_manual
        data_inicio = st.date_input("Data de inicio", value=_hoje())
        obs = st.text_area("Observacoes da matricula")
        if st.form_submit_button("Matricular", type="primary"):
            try:
                salvar_ebd_matricula(slug, id_classe, nome_aluno, id_cadastro, data_inicio.isoformat(), obs)
                st.success("Aluno matriculado.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    matriculas = listar_ebd_matriculas(slug, id_classe, incluir_inativas=True)
    if not matriculas.empty:
        tabela = matriculas.copy()
        tabela["situacao"] = tabela["ativa"].map({1: "Ativo", 0: "Encerrado"})
        tabela["data_inicio"] = tabela["data_inicio"].apply(_fmt_data)
        st.dataframe(
            tabela[["nome_aluno", "classe", "situacao", "data_inicio", "observacoes"]],
            use_container_width=True,
            hide_index=True,
        )
        encerrar = st.selectbox(
            "Encerrar matricula",
            ["Selecione"] + [
                f'{int(row["id_matricula"])} - {row["nome_aluno"]}'
                for _, row in matriculas[matriculas["ativa"] == 1].iterrows()
            ],
        )
        if encerrar != "Selecione" and confirmar_exclusao(f"encerrar_matricula_{encerrar}", "Encerrar matricula selecionada"):
            encerrar_ebd_matricula(slug, int(encerrar.split(" - ")[0]), _hoje().isoformat())
            st.success("Matricula encerrada.")
            st.rerun()

    st.markdown("#### Classes cadastradas")
    st.dataframe(
        df_classes[["nome", "faixa_etaria", "professor_principal", "sala", "ativa", "observacoes"]],
        use_container_width=True,
        hide_index=True,
    )
    if not df_classes.empty:
        excluir = st.selectbox(
            "Excluir/inativar classe",
            ["Selecione"] + [
                f'{int(row["id_classe"])} - {row["nome"]}'
                for _, row in df_classes.iterrows()
            ],
        )
        if excluir != "Selecione" and confirmar_exclusao(f"excluir_classe_{excluir}", "Excluir ou inativar classe"):
            removida = excluir_ebd_classe(slug, int(excluir.split(" - ")[0]))
            st.success("Classe excluida." if removida else "Classe inativada porque possui historico.")
            st.rerun()


def _render_chamada(slug):
    st.markdown("### Chamada por classe")
    df_classes = listar_ebd_classes(slug)
    if df_classes.empty:
        st.info("Cadastre uma classe antes de registrar chamada.")
        return
    op_classes = _classes_opcoes(df_classes)
    c1, c2 = st.columns([2, 1])
    classe_label = c1.selectbox("Classe", list(op_classes.keys()), key="chamada_classe")
    data_aula = c2.date_input("Data da aula", value=_hoje())
    id_classe = op_classes[classe_label]

    matriculas = listar_ebd_matriculas(slug, id_classe)
    if matriculas.empty:
        st.warning("Esta classe ainda nao possui alunos ativos.")
        return

    aulas = listar_ebd_aulas(slug, data_aula.isoformat(), data_aula.isoformat(), id_classe)
    presencas_salvas = {}
    tema_atual = ""
    professor_atual = ""
    obs_atual = ""
    if not aulas.empty:
        aula = aulas.iloc[0]
        tema_atual = aula.get("tema", "")
        professor_atual = aula.get("professor", "")
        obs_atual = aula.get("observacoes", "")
        from data.repository import carregar_ebd_presencas
        df_pres = carregar_ebd_presencas(slug, int(aula["id_aula"]))
        presencas_salvas = {
            int(row["id_matricula"]): bool(row["presente"])
            for _, row in df_pres.iterrows()
        }

    with st.form("form_ebd_chamada"):
        c1, c2 = st.columns(2)
        tema = c1.text_input("Tema da aula", value=tema_atual)
        professor = c2.text_input("Professor", value=professor_atual)
        obs = st.text_area("Observacoes da aula", value=obs_atual)
        st.caption("Marque os alunos presentes. Alunos desmarcados serao contabilizados como falta.")
        dados = matriculas[["id_matricula", "nome_aluno"]].copy()
        dados["presente"] = dados["id_matricula"].apply(lambda x: presencas_salvas.get(int(x), True))
        editado = st.data_editor(
            dados,
            hide_index=True,
            use_container_width=True,
            disabled=["id_matricula", "nome_aluno"],
            column_config={
                "id_matricula": st.column_config.NumberColumn("ID"),
                "nome_aluno": st.column_config.TextColumn("Aluno"),
                "presente": st.column_config.CheckboxColumn("Presente"),
            },
        )
        if st.form_submit_button("Salvar chamada", type="primary"):
            presencas = {
                int(row["id_matricula"]): bool(row["presente"])
                for _, row in editado.iterrows()
            }
            salvar_ebd_chamada(
                slug,
                id_classe,
                data_aula.isoformat(),
                tema,
                professor,
                obs,
                presencas,
            )
            st.success("Chamada salva.")
            st.rerun()


def _render_relatorios(slug):
    st.markdown("### Relatorios da EBD")
    c1, c2 = st.columns(2)
    inicio = c1.date_input("Data inicial", value=_inicio_mes(), key="ebd_rel_ini")
    fim = c2.date_input("Data final", value=_hoje(), key="ebd_rel_fim")
    if inicio > fim:
        st.error("A data inicial nao pode ser maior que a data final.")
        return

    aulas = listar_ebd_aulas(slug, inicio.isoformat(), fim.isoformat())
    resumo = relatorio_ebd_resumo_classes(slug, inicio.isoformat(), fim.isoformat())
    freq = relatorio_ebd_frequencia(slug, inicio.isoformat(), fim.isoformat())
    _metricas_ebd(resumo, aulas)

    st.markdown("#### Frequencia por classe")
    _grafico_frequencia_classes(resumo)
    if not resumo.empty:
        tabela = resumo.copy()
        tabela["frequencia_pct"] = tabela["frequencia_pct"].apply(_pct)
        st.dataframe(tabela, use_container_width=True, hide_index=True)
        st.download_button(
            "Baixar relatorio de classes CSV",
            data=gerar_csv(resumo),
            file_name="relatorio_ebd_classes.csv",
            mime="text/csv",
        )

    st.markdown("#### Relatorio individual por aluno")
    if freq.empty:
        st.info("Sem chamadas registradas no periodo.")
    else:
        freq = freq.copy()
        total = freq["presencas"] + freq["faltas"]
        freq["frequencia_pct"] = (freq["presencas"] / total.where(total > 0, 1) * 100).round(1)
        freq["acompanhamento"] = freq["frequencia_pct"].apply(
            lambda v: "Acompanhar aluno/familia" if v < 60 else "Regular"
        )
        exibicao = freq.copy()
        exibicao["frequencia_pct"] = exibicao["frequencia_pct"].apply(_pct)
        st.dataframe(exibicao, use_container_width=True, hide_index=True)
        st.download_button(
            "Baixar relatorio de alunos CSV",
            data=gerar_csv(freq),
            file_name="relatorio_ebd_alunos.csv",
            mime="text/csv",
        )

    st.markdown("#### Aulas registradas")
    if aulas.empty:
        st.info("Nenhuma aula no periodo.")
    else:
        aulas_exibir = aulas.copy()
        aulas_exibir["data"] = aulas_exibir["data"].apply(_fmt_data)
        aulas_exibir["frequencia"] = (
            aulas_exibir["presentes"].fillna(0)
            / aulas_exibir["matriculados"].replace(0, 1).fillna(1)
            * 100
        ).round(1).apply(_pct)
        st.dataframe(
            aulas_exibir[["data", "classe", "tema", "professor", "matriculados", "presentes", "frequencia"]],
            use_container_width=True,
            hide_index=True,
        )


def _render_escala(slug):
    st.markdown("### Escala de professores")
    df_classes = listar_ebd_classes(slug)
    op_classes = {"Sem classe definida": None}
    if not df_classes.empty:
        op_classes.update(_classes_opcoes(df_classes))

    with st.form("form_ebd_escala"):
        c1, c2 = st.columns(2)
        data = c1.date_input("Data", value=_hoje())
        classe_label = c2.selectbox("Classe", list(op_classes.keys()))
        c3, c4 = st.columns(2)
        professor = c3.text_input("Professor")
        auxiliar = c4.text_input("Auxiliar")
        tema = st.text_input("Tema/assunto")
        obs = st.text_area("Observacoes")
        classe_nome = "" if op_classes[classe_label] else classe_label
        if st.form_submit_button("Adicionar escala", type="primary"):
            try:
                salvar_ebd_escala(
                    slug,
                    data.isoformat(),
                    professor,
                    op_classes[classe_label],
                    classe_nome,
                    auxiliar,
                    tema,
                    obs,
                )
                st.success("Escala salva.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    c1, c2 = st.columns(2)
    inicio = c1.date_input("Inicio da escala", value=_inicio_mes(), key="escala_ini")
    fim = c2.date_input("Fim da escala", value=_hoje() + datetime.timedelta(days=60), key="escala_fim")
    escala = listar_ebd_escala(slug, inicio.isoformat(), fim.isoformat())
    if escala.empty:
        st.info("Nenhuma escala cadastrada para o periodo.")
        return
    exibir = escala.copy()
    exibir["data"] = exibir["data"].apply(_fmt_data)
    st.dataframe(
        exibir[["data", "classe", "professor", "auxiliar", "tema", "observacoes"]],
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Baixar escala CSV",
        data=gerar_csv(escala),
        file_name="escala_professores_ebd.csv",
        mime="text/csv",
    )
    excluir = st.selectbox(
        "Excluir item da escala",
        ["Selecione"] + [
            f'{int(row["id_escala"])} - {_fmt_data(row["data"])} - {row["professor"]}'
            for _, row in escala.iterrows()
        ],
    )
    if excluir != "Selecione" and confirmar_exclusao(f"excluir_escala_{excluir}", "Excluir escala selecionada"):
        excluir_ebd_escala(slug, int(excluir.split(" - ")[0]))
        st.success("Escala excluida.")
        st.rerun()


def render():
    st.subheader("EBD")
    st.caption("Gestao de classes, chamada, frequencia e escala de professores da Escola Biblica Dominical.")
    slug = slug_da_sessao()
    if not slug:
        st.error("Sessao invalida. Faca login novamente.")
        return

    tab_classes, tab_chamada, tab_relatorios, tab_escala = st.tabs([
        "Classes e alunos",
        "Chamada",
        "Relatorios",
        "Escala de professores",
    ])
    with tab_classes:
        _render_classes(slug)
    with tab_chamada:
        _render_chamada(slug)
    with tab_relatorios:
        _render_relatorios(slug)
    with tab_escala:
        _render_escala(slug)
