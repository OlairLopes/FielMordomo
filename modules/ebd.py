import datetime
import html
import urllib.parse
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.repository import (
    carregar_cadastros,
    encerrar_ebd_matricula,
    excluir_ebd_classe,
    excluir_ebd_escala,
    inativar_ebd_secretario,
    listar_ebd_aulas,
    listar_ebd_classes,
    listar_ebd_escala,
    listar_ebd_matriculas,
    listar_ebd_secretarios,
    relatorio_ebd_frequencia,
    relatorio_ebd_resumo_classes,
    obter_config_igreja,
    salvar_ebd_chamada,
    salvar_ebd_classe,
    salvar_ebd_escala,
    salvar_ebd_matricula,
    salvar_ebd_secretario,
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
MENSAGEM_ESCALA_PADRAO = """Paz do Senhor, {nome}!

Voce esta escalado(a) para servir na Escola Bíblica.
Data: {data}
Classe: {classe}
Funcao: {funcao}
Tema: {tema}

Contamos com sua presenca e dedicacao. Deus abencoe!"""


def _hoje():
    return datetime.date.today()


def _inicio_mes():
    hoje = _hoje()
    return hoje.replace(day=1)


def _fmt_data(valor):
    try:
        data = _parse_data(valor)
        return data.strftime("%d/%m/%Y") if data else str(valor or "")
    except Exception:
        return str(valor or "")


def _parse_data(valor):
    if valor is None:
        return None
    if isinstance(valor, datetime.datetime):
        return valor.date()
    if isinstance(valor, datetime.date):
        return valor

    try:
        data = pd.to_datetime(valor, errors="coerce")
        if pd.notna(data):
            return data.date()
    except Exception:
        pass

    texto = str(valor or "").strip()
    if not texto:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(texto, formato).date()
        except Exception:
            pass
    return None


def _data_iso(valor):
    try:
        data = _parse_data(valor)
        return data.isoformat() if data else ""
    except Exception:
        return ""


def _filtrar_matriculas_validas_na_data(matriculas, data_referencia):
    if matriculas.empty:
        return matriculas

    data_ref = _data_iso(data_referencia)
    if not data_ref:
        return matriculas[matriculas["ativa"] == 1].copy()

    dados = matriculas.copy()
    if "data_inicio" not in dados.columns:
        dados["data_inicio"] = ""
    if "data_fim" not in dados.columns:
        dados["data_fim"] = ""
    inicio = dados["data_inicio"].apply(_data_iso)
    fim = dados["data_fim"].apply(_data_iso)

    validas = (inicio.eq("") | (inicio <= data_ref)) & (fim.eq("") | (fim >= data_ref))
    return dados[validas].copy()


def _diagnostico_matriculas_na_data(matriculas, data_referencia):
    if matriculas.empty:
        return pd.DataFrame()

    data_ref = _data_iso(data_referencia)
    dados = matriculas.copy()

    for col in ["data_inicio", "data_fim", "ativa"]:
        if col not in dados.columns:
            dados[col] = "" if col != "ativa" else 1

    def situacao(row):
        inicio = _data_iso(row.get("data_inicio"))
        fim = _data_iso(row.get("data_fim"))
        ativa = _int_seguro(row.get("ativa"), 1) == 1

        if data_ref and inicio and inicio > data_ref:
            return "Inicia após esta data"
        if data_ref and fim and fim < data_ref:
            return "Encerrada antes desta data"
        if not ativa and not fim:
            return "Inativa"
        return "Ativa na data"

    dados["Situação na data"] = dados.apply(situacao, axis=1)
    dados["Início"] = dados["data_inicio"].apply(_fmt_data)
    dados["Encerramento"] = dados["data_fim"].apply(lambda v: _fmt_data(v) if str(v or "").strip() else "")

    colunas = ["nome_aluno", "Situação na data", "Início", "Encerramento"]
    if "classe" in dados.columns:
        colunas.insert(1, "classe")

    return dados[colunas].rename(columns={
        "nome_aluno": "Aluno",
        "classe": "Classe",
    })


def _pct(valor):
    try:
        return f"{float(valor):.1f}%"
    except Exception:
        return "0.0%"


def _moeda(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def _int_seguro(valor, padrao=0):
    try:
        if pd.isna(valor):
            return int(padrao)
    except Exception:
        pass
    try:
        texto = str(valor).strip()
        if not texto:
            return int(padrao)
        return int(float(texto.replace(",", ".")))
    except Exception:
        return int(padrao)


def _float_seguro(valor, padrao=0.0):
    try:
        if pd.isna(valor):
            return float(padrao)
    except Exception:
        pass
    try:
        texto = str(valor).strip()
        if not texto:
            return float(padrao)
        return float(texto.replace(".", "").replace(",", ".") if "," in texto else texto)
    except Exception:
        return float(padrao)


def _render_cards_superintendentes(slug):
    escala = listar_ebd_escala(slug)
    if escala.empty or "superintendente" not in escala.columns:
        return

    dados = escala.copy()
    dados["superintendente"] = dados["superintendente"].fillna("").astype(str).str.strip()
    dados = dados[dados["superintendente"] != ""].copy()
    if dados.empty:
        return

    if "data" in dados.columns:
        dados["_data_ordem"] = pd.to_datetime(dados["data"], errors="coerce")
        dados = dados.sort_values("_data_ordem", ascending=False)

    cards = []
    vistos = set()
    for _, row in dados.iterrows():
        nome = str(row.get("superintendente", "") or "").strip()
        chave = nome.lower()
        if not nome or chave in vistos:
            continue
        vistos.add(chave)
        telefone = str(row.get("telefone_superintendente", "") or "").strip()
        cards.append(
            '<div class="ebd-super-card">'
            '<span class="ebd-super-label">Superintendente</span>'
            f'<b>{html.escape(nome)}</b>'
            '<small>Escola Bíblica</small>'
            f'<small>{html.escape(telefone)}</small>'
            '</div>'
        )
        if len(cards) >= 4:
            break

    if not cards:
        return

    st.markdown(
        """
        <style>
        .ebd-super-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 18px 0 22px 0;
        }
        .ebd-super-card {
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 18px 20px;
            background: #FFFFFF;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
            min-height: 104px;
        }
        .ebd-super-card b {
            display: block;
            color: #0F172A;
            font-size: 1.05rem;
            font-weight: 800;
            margin-bottom: 8px;
        }
        .ebd-super-card small {
            display: block;
            color: #64748B;
            font-size: 0.82rem;
            line-height: 1.45;
        }
        .ebd-super-label {
            display: block;
            color: #DC2626;
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.02em;
            margin-bottom: 8px;
            text-transform: uppercase;
        }
        @media(max-width: 1100px) {
            .ebd-super-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        @media(max-width: 620px) {
            .ebd-super-grid { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="ebd-super-grid">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def _limpar_tel(tel):
    return "".join(c for c in str(tel or "") if c.isdigit())


def _normalizar_tel_brasil(tel):
    tel_limpo = _limpar_tel(tel)
    if not tel_limpo:
        return ""
    while tel_limpo.startswith("0"):
        tel_limpo = tel_limpo[1:]
    if len(tel_limpo) in (10, 11):
        tel_limpo = "55" + tel_limpo
    return tel_limpo if len(tel_limpo) in (12, 13) and tel_limpo.startswith("55") else ""


def _link_whatsapp(tel, mensagem):
    numero = _normalizar_tel_brasil(tel)
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={urllib.parse.quote(mensagem)}"


def _mensagem_escala(slug, row, nome, funcao):
    data = _fmt_data(row.get("data", ""))
    classe = str(row.get("classe", "") or "Escola Bíblica").strip()
    tema = str(row.get("tema", "") or "").strip()
    modelo = obter_config_igreja(slug, "mensagem_whatsapp_escala_ebd", MENSAGEM_ESCALA_PADRAO)
    dados = defaultdict(
        str,
        nome=nome,
        data=data,
        classe=classe,
        funcao=funcao,
        tema=tema or "A definir",
    )
    return str(modelo or MENSAGEM_ESCALA_PADRAO).format_map(dados)


def _botao_whatsapp(label, telefone, mensagem, key):
    link = _link_whatsapp(telefone, mensagem)
    if not link:
        st.caption(f"{label}: informe um WhatsApp valido para gerar o aviso.")
        return
    st.markdown(
        f'<a href="{html.escape(link, quote=True)}" target="_blank" '
        'style="display:inline-block;padding:0.55rem 0.85rem;border-radius:10px;'
        'background:#1D9E75;color:white;text-decoration:none;font-weight:700;'
        'box-shadow:0 8px 18px rgba(29,158,117,.25)">'
        f'{html.escape(label)}</a>',
        unsafe_allow_html=True,
    )


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


def _grafico_totais_ebd(titulo, dados):
    if not dados:
        st.info("Sem dados para gerar o grafico.")
        return
    df = pd.DataFrame(
        [{"Indicador": chave, "Total": valor} for chave, valor in dados.items()]
    )
    fig = go.Figure(go.Bar(
        name="Total",
        x=df["Indicador"],
        y=df["Total"],
        marker_color=[
            CORES["azul"], CORES["verde"], CORES["vermelho"], CORES["laranja"],
            "#7C3AED", "#0891B2", "#B45309",
        ][:len(df)],
        text=[
            _moeda(v) if "Oferta" in str(k) else str(int(v))
            for k, v in dados.items()
        ],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Total: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title=titulo,
        height=430,
        margin=dict(t=60, b=80, l=25, r=25),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(fixedrange=True),
        yaxis=dict(fixedrange=True, gridcolor="#E2E8F0"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


def _totais_aulas(aulas):
    if aulas.empty:
        return {
            "Matriculados": 0,
            "Presentes": 0,
            "Ausentes": 0,
            "Visitantes": 0,
            "Biblias": 0,
            "Revistas": 0,
            "Harpas": 0,
            "Ofertas": 0.0,
        }
    return {
        "Matriculados": int(aulas["matriculados"].fillna(0).sum()),
        "Presentes": int(aulas["presentes"].fillna(0).sum()),
        "Ausentes": int(aulas["ausentes"].fillna(0).sum()),
        "Visitantes": int(aulas["visitantes"].fillna(0).sum()),
        "Biblias": int(aulas["qtd_biblias"].fillna(0).sum()),
        "Revistas": int(aulas["qtd_revistas"].fillna(0).sum()),
        "Harpas": int(aulas["qtd_harpas"].fillna(0).sum()),
        "Ofertas": float(aulas["ofertas"].fillna(0).sum()),
    }


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


def _selecionar_pessoa_escala(slug, titulo, key_prefix, obrigatorio=False):
    op_membros, df_membros = _membros_opcoes(slug)
    origem = st.radio(
        titulo,
        ["Buscar no cadastro de membros", "Inserir manualmente"],
        horizontal=True,
        key=f"{key_prefix}_origem",
    )
    if origem == "Buscar no cadastro de membros" and op_membros:
        membro_label = st.selectbox(
            f"{titulo} - membro",
            list(op_membros.keys()),
            key=f"{key_prefix}_membro",
        )
        id_cadastro = op_membros[membro_label]
        row = df_membros[df_membros["id_cadastro"] == id_cadastro].iloc[0]
        nome = str(row.get("nome", "") or "")
        telefone = str(row.get("telefone", "") or "")
        funcao = str(row.get("funcao", "") or "")
        st.caption(f"Funcao preenchida pelo cadastro: {funcao or 'sem funcao informada'}")
        return nome, telefone, funcao
    if origem == "Buscar no cadastro de membros":
        st.warning("Nao ha membros ativos cadastrados. Use a insercao manual.")
    c1, c2 = st.columns(2)
    nome = c1.text_input(
        f"{titulo} - nome manual",
        key=f"{key_prefix}_nome_manual",
    )
    telefone = c2.text_input(
        f"{titulo} - WhatsApp",
        key=f"{key_prefix}_telefone_manual",
        placeholder="Opcional",
    )
    funcao = st.text_input(
        f"{titulo} - funcao",
        key=f"{key_prefix}_funcao_manual",
        value="",
        help="Preencha manualmente quando a pessoa nao estiver no cadastro.",
    )
    if obrigatorio and not nome.strip():
        st.caption("Informe o nome antes de salvar.")
    return nome, telefone, funcao


def _escala_da_aula(slug, data_aula, id_classe):
    escala = listar_ebd_escala(
        slug, data_aula.isoformat(), data_aula.isoformat(), id_classe
    )
    if escala.empty:
        return None
    escala_classe = escala[escala["id_classe"].fillna(0).astype(int) == int(id_classe)]
    if escala_classe.empty:
        return None
    return escala_classe.iloc[0].to_dict()


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

    st.markdown("#### Matrículas por classe")
    st.caption(
        "Matricule alunos em cada classe da EBD. A chamada respeita a data de início "
        "e a data de encerramento da matrícula, preservando o histórico."
    )
    op_classes = _classes_opcoes(df_classes_ativas)
    op_membros, df_membros = _membros_opcoes(slug)

    with st.expander("Nova matrícula", expanded=False):
        with st.form("form_ebd_matricula"):
            classe_label = st.selectbox("Classe", list(op_classes.keys()), key="matricula_classe_nova")
            modo = st.radio("Origem do aluno", ["Membro cadastrado", "Nome manual"], horizontal=True)
            id_cadastro = None
            nome_aluno = ""
            if modo == "Membro cadastrado":
                if op_membros:
                    membro_label = st.selectbox("Membro", list(op_membros.keys()))
                    id_cadastro = op_membros[membro_label]
                    nome_aluno = df_membros[df_membros["id_cadastro"] == id_cadastro].iloc[0]["nome"]
                else:
                    st.warning("Nao ha membros ativos cadastrados.")
            else:
                nome_aluno = st.text_input("Nome do aluno")
            c1, c2 = st.columns(2)
            data_inicio = c1.date_input("Data de início", value=_hoje(), format="DD/MM/YYYY")
            obs = c2.text_input("Observações")
            if st.form_submit_button("Matricular", type="primary"):
                if not str(nome_aluno or "").strip():
                    st.error("Informe ou selecione o aluno.")
                else:
                    try:
                        salvar_ebd_matricula(
                            slug,
                            op_classes[classe_label],
                            nome_aluno,
                            id_cadastro,
                            data_inicio.isoformat(),
                            obs,
                        )
                        st.success("Matrícula salva.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    filtro_label = st.selectbox(
        "Filtrar matrículas por classe",
        ["Todas"] + list(op_classes.keys()),
        key="ebd_matriculas_filtro_classe",
    )
    id_classe_filtro = None if filtro_label == "Todas" else op_classes[filtro_label]
    matriculas = listar_ebd_matriculas(slug, id_classe_filtro, incluir_inativas=True)

    if matriculas.empty:
        st.info("Nenhuma matrícula cadastrada para o filtro selecionado.")
    else:
        tabela = matriculas.copy()
        tabela["situacao"] = tabela["ativa"].map({1: "Ativa", 0: "Encerrada"}).fillna("Ativa")
        tabela["data_inicio"] = tabela["data_inicio"].apply(_fmt_data)
        tabela["data_fim"] = tabela["data_fim"].apply(_fmt_data)
        st.dataframe(
            tabela[["classe", "nome_aluno", "situacao", "data_inicio", "data_fim", "observacoes"]],
            use_container_width=True,
            hide_index=True,
        )

        op_matriculas = {
            f'{int(row["id_matricula"])} - {row["nome_aluno"]} ({row["classe"]})': row
            for _, row in matriculas.iterrows()
        }

        with st.expander("Editar matrícula", expanded=False):
            selecionada = st.selectbox(
                "Matrícula para editar",
                ["Selecione"] + list(op_matriculas.keys()),
                key="ebd_editar_matricula",
            )
            if selecionada != "Selecione":
                row = op_matriculas[selecionada]
                classe_labels = list(op_classes.keys())
                classe_idx = 0
                for idx, label in enumerate(classe_labels):
                    if op_classes[label] == int(row["id_classe"]):
                        classe_idx = idx
                        break
                with st.form(f"form_editar_matricula_ebd_{int(row['id_matricula'])}"):
                    classe_edit = st.selectbox("Classe", classe_labels, index=classe_idx)
                    c1, c2 = st.columns(2)
                    nome_edit = c1.text_input("Nome do aluno", value=str(row.get("nome_aluno", "") or ""))
                    data_inicio_edit = c2.text_input(
                        "Data de início",
                        value=str(row.get("data_inicio", "") or ""),
                    )
                    ativa_edit = st.selectbox(
                        "Situação",
                        ["Ativa", "Encerrada"],
                        index=0 if _int_seguro(row.get("ativa"), 1) == 1 else 1,
                    )
                    obs_edit = st.text_area("Observações", value=str(row.get("observacoes", "") or ""))
                    if st.form_submit_button("Atualizar matrícula", type="primary"):
                        try:
                            salvar_ebd_matricula(
                                slug,
                                op_classes[classe_edit],
                                nome_edit,
                                row.get("id_cadastro"),
                                data_inicio_edit,
                                obs_edit,
                                id_matricula=int(row["id_matricula"]),
                                ativa=ativa_edit == "Ativa",
                            )
                            st.success("Matrícula atualizada.")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

        ativas = matriculas[matriculas["ativa"] == 1]
        if not ativas.empty:
            op_ativas = [
                f'{int(row["id_matricula"])} - {row["nome_aluno"]} ({row["classe"]})'
                for _, row in ativas.iterrows()
            ]
            with st.expander("Encerrar matrícula", expanded=False):
                st.caption(
                    "Use esta opção para retirar o aluno das próximas chamadas "
                    "sem apagar o histórico de participação já registrado."
                )
                encerrar = st.selectbox(
                    "Matrícula ativa",
                    ["Selecione"] + op_ativas,
                    key="ebd_encerrar_matricula",
                )
                data_fim = st.date_input(
                    "Data de encerramento",
                    value=_hoje(),
                    format="DD/MM/YYYY",
                    key="ebd_data_fim_matricula",
                )
                if encerrar != "Selecione" and confirmar_exclusao(
                    f"encerrar_ebd_{encerrar}",
                    "Confirmar encerramento da matrícula",
                ):
                    encerrar_ebd_matricula(
                        slug,
                        int(encerrar.split(" - ")[0]),
                        data_fim.isoformat(),
                    )
                    st.success(
                        "Matrícula encerrada. O histórico foi preservado e o aluno "
                        "não aparecerá nas chamadas após a data de encerramento."
                    )
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


def _render_chamada(slug, id_classe_fixo=None):
    try:
        _render_chamada_conteudo(slug, id_classe_fixo)
    except Exception as exc:
        st.error(
            "Nao foi possivel carregar a chamada da Escola Bíblica. "
            f"Tipo do erro: {type(exc).__name__}. Detalhe: {exc}"
        )


def _render_chamada_conteudo(slug, id_classe_fixo=None):
    st.markdown("### Chamada por classe")
    df_classes = listar_ebd_classes(slug)
    if df_classes.empty:
        st.info("Cadastre uma classe antes de registrar chamada.")
        return
    if id_classe_fixo:
        df_classes = df_classes[df_classes["id_classe"] == int(id_classe_fixo)]
        if df_classes.empty:
            st.error("Sua classe vinculada nao esta ativa ou nao foi encontrada.")
            return

    op_classes = _classes_opcoes(df_classes)
    classe_label = st.selectbox(
        "Classe",
        list(op_classes.keys()),
        key="chamada_classe",
        disabled=bool(id_classe_fixo),
    )
    id_classe = op_classes[classe_label]

    escala_classe = listar_ebd_escala(slug, id_classe=id_classe)
    chamadas_salvas = listar_ebd_aulas(slug, id_classe=id_classe)
    opcoes_modo = ["Registrar/editar pela escala"]
    if not chamadas_salvas.empty:
        opcoes_modo.append("Editar chamada salva")
    if st.session_state.get("modo_chamada_ebd") not in opcoes_modo:
        st.session_state.pop("modo_chamada_ebd", None)
    modo_chamada = st.radio(
        "Modo da chamada",
        opcoes_modo,
        horizontal=True,
        key="modo_chamada_ebd",
    )

    escala_aula = None
    aula_editada = None
    if modo_chamada == "Editar chamada salva":
        c_ini, c_fim = st.columns(2)
        editar_inicio = c_ini.date_input(
            "Data inicial para localizar chamada",
            value=_inicio_mes(),
            key=f"ebd_edit_ini_{id_classe}",
            format="DD/MM/YYYY",
        )
        editar_fim = c_fim.date_input(
            "Data final para localizar chamada",
            value=_hoje(),
            key=f"ebd_edit_fim_{id_classe}",
            format="DD/MM/YYYY",
        )
        if editar_inicio > editar_fim:
            st.error("A data inicial nao pode ser maior que a data final.")
            return
        chamadas_salvas = listar_ebd_aulas(
            slug,
            editar_inicio.isoformat(),
            editar_fim.isoformat(),
            id_classe,
        )
        if chamadas_salvas.empty:
            st.info("Nenhuma chamada encontrada no periodo selecionado.")
            return
        op_chamadas = {
            f'{_fmt_data(row["data"])} - {row["classe"]} - {row.get("tema", "") or "sem tema"}': row
            for _, row in chamadas_salvas.iterrows()
        }
        labels_chamadas = list(op_chamadas.keys())
        chave_chamada_salva = "editar_chamada_salva"
        if st.session_state.get(chave_chamada_salva) not in labels_chamadas:
            st.session_state[chave_chamada_salva] = labels_chamadas[0]
        idx_atual = labels_chamadas.index(st.session_state[chave_chamada_salva])
        nav_ant, nav_sel, nav_seg = st.columns([1, 3, 1])
        if nav_ant.button(
            "Dia anterior",
            use_container_width=True,
            disabled=idx_atual >= len(labels_chamadas) - 1,
            key=f"ebd_chamada_anterior_{id_classe}",
        ):
            st.session_state[chave_chamada_salva] = labels_chamadas[idx_atual + 1]
        if nav_seg.button(
            "Dia seguinte",
            use_container_width=True,
            disabled=idx_atual <= 0,
            key=f"ebd_chamada_seguinte_{id_classe}",
        ):
            st.session_state[chave_chamada_salva] = labels_chamadas[idx_atual - 1]
        with nav_sel:
            chamada_label = st.selectbox(
                "Chamada salva para editar",
                labels_chamadas,
                key=chave_chamada_salva,
            )
        chamada_row = op_chamadas[chamada_label]
        aula_editada = chamada_row
        data_aula_original = _parse_data(chamada_row["data"]) or _hoje()
        data_aula = st.date_input(
            "Data da aula",
            value=data_aula_original,
            key=f"ebd_data_edit_{int(chamada_row['id_aula'])}",
            format="DD/MM/YYYY",
        )
        escala_aula = _escala_da_aula(slug, data_aula, id_classe)
        st.info(f"Editando chamada salva de {_fmt_data(data_aula.isoformat())}.")
    else:
        if escala_classe.empty:
            st.warning(
                "Nao ha escala de professores cadastrada para esta classe. "
                "Cadastre uma escala antes de registrar a chamada."
            )
            return
        op_escalas = {
            f'{_fmt_data(row["data"])} - {row.get("tema", "") or "sem tema"} - {row["professor"]}': row
            for _, row in escala_classe.iterrows()
        }
        chave_escala = f"escala_para_chamada_{int(id_classe)}"
        if st.session_state.get(chave_escala) not in op_escalas:
            st.session_state.pop(chave_escala, None)
        escala_label = st.selectbox(
            "Data da chamada conforme escala",
            list(op_escalas.keys()),
            key=chave_escala,
        )
        escala_aula = op_escalas[escala_label]
        data_aula = _parse_data(escala_aula["data"]) or _hoje()

    matriculas_todas = listar_ebd_matriculas(slug, id_classe, incluir_inativas=True)
    if matriculas_todas.empty:
        st.warning("Esta classe ainda nao possui alunos matriculados.")
        return

    matriculas = _filtrar_matriculas_validas_na_data(matriculas_todas, data_aula)
    if not matriculas.empty:
        matriculas = matriculas.copy()
        matriculas["id_matricula"] = matriculas["id_matricula"].apply(lambda x: _int_seguro(x, 0))
        matriculas = matriculas[matriculas["id_matricula"] > 0].copy()

    if matriculas.empty:
        st.warning(
            "Nenhuma matricula estava ativa na data desta chamada. "
            "Abaixo estao as matriculas encontradas para esta classe e a situacao delas nesta data."
        )
        st.caption(f"Data selecionada para a chamada: {_fmt_data(data_aula)}")
        st.dataframe(
            _diagnostico_matriculas_na_data(matriculas_todas, data_aula),
            use_container_width=True,
            hide_index=True,
        )
        return

    presencas_salvas = {}
    tema_atual = ""
    professor_atual = ""
    obs_atual = ""
    visitantes_atual = 0
    revistas_atual = 0
    biblias_atual = 0
    harpas_atual = 0
    ofertas_atual = 0.0

    if aula_editada is not None:
        aula = aula_editada
        tema_atual = aula.get("tema", "")
        professor_atual = aula.get("professor", "")
        obs_atual = aula.get("observacoes", "")
        visitantes_atual = _int_seguro(aula.get("visitantes", 0), 0)
        revistas_atual = _int_seguro(aula.get("qtd_revistas", 0), 0)
        biblias_atual = _int_seguro(aula.get("qtd_biblias", 0), 0)
        harpas_atual = _int_seguro(aula.get("qtd_harpas", 0), 0)
        ofertas_atual = _float_seguro(aula.get("ofertas", 0), 0.0)
        id_aula_atual = _int_seguro(aula.get("id_aula"), 0)
        if id_aula_atual:
            from data.repository import carregar_ebd_presencas
            df_pres = carregar_ebd_presencas(slug, id_aula_atual)
            for _, row in df_pres.iterrows():
                id_matricula = _int_seguro(row.get("id_matricula"), 0)
                if id_matricula:
                    presencas_salvas[id_matricula] = bool(row.get("presente"))
    elif escala_aula:
        tema_atual = str(escala_aula.get("tema", "") or "")
        professor_atual = str(escala_aula.get("professor", "") or "")

    acao_presencas = st.radio(
        "Presenças da lista de chamada",
        ["Manter marcação atual", "Marcar todos", "Desmarcar todos"],
        horizontal=True,
        key=f"ebd_acao_presencas_{id_classe}_{data_aula.isoformat()}",
    )

    with st.form("form_ebd_chamada"):
        if escala_aula:
            st.success("Tema e professor preenchidos automaticamente pela escala de professores.")
        else:
            st.info("Nenhuma escala encontrada para esta classe e data.")

        c1, c2 = st.columns(2)
        tema = c1.text_input("Tema da aula", value=tema_atual)
        professor = c2.text_input("Professor", value=professor_atual)

        st.caption("Marque os alunos presentes. Alunos desmarcados serao contabilizados como falta.")
        dados = matriculas[["id_matricula", "nome_aluno"]].copy()
        if acao_presencas == "Marcar todos":
            dados["presente"] = True
        elif acao_presencas == "Desmarcar todos":
            dados["presente"] = False
        else:
            dados["presente"] = dados["id_matricula"].apply(
                lambda x: presencas_salvas.get(_int_seguro(x), True)
            )
        editado = st.data_editor(
            dados,
            hide_index=True,
            use_container_width=True,
            key=f"ebd_editor_chamada_{id_classe}_{data_aula.isoformat()}_{acao_presencas}",
            disabled=["id_matricula", "nome_aluno"],
            column_config={
                "id_matricula": st.column_config.NumberColumn("ID"),
                "nome_aluno": st.column_config.TextColumn("Aluno"),
                "presente": st.column_config.CheckboxColumn("Presente"),
            },
        )

        qtd_matriculados_calc = int(len(editado))
        qtd_presentes_calc = int(editado["presente"].fillna(False).astype(bool).sum())
        qtd_ausentes_calc = max(qtd_matriculados_calc - qtd_presentes_calc, 0)

        st.markdown("#### Totais da chamada")
        qtd_visitantes = st.number_input("Visitantes", min_value=0, step=1, value=visitantes_atual)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Matriculados", qtd_matriculados_calc)
        m2.metric("Presentes", qtd_presentes_calc)
        m3.metric("Ausentes", qtd_ausentes_calc)
        m4.metric("Visitantes", qtd_visitantes)

        st.markdown("#### Recursos e ofertas da aula")
        r1, r2, r3, r4 = st.columns(4)
        qtd_revistas = r1.number_input("Revistas", min_value=0, step=1, value=revistas_atual)
        qtd_biblias = r2.number_input("Biblias", min_value=0, step=1, value=biblias_atual)
        qtd_harpas = r3.number_input("Harpas", min_value=0, step=1, value=harpas_atual)
        ofertas = r4.number_input("Ofertas", min_value=0.0, step=1.0, value=ofertas_atual, format="%.2f")
        obs = st.text_area("Observacoes da aula", value=obs_atual)

        if st.form_submit_button("Salvar chamada", type="primary"):
            presencas = {}
            for _, row in editado.iterrows():
                id_matricula = _int_seguro(row.get("id_matricula"), 0)
                if id_matricula:
                    presencas[id_matricula] = bool(row.get("presente"))
            try:
                salvar_ebd_chamada(
                    slug,
                    id_classe,
                    data_aula.isoformat(),
                    tema,
                    professor,
                    obs,
                    presencas,
                    qtd_matriculados_calc,
                    qtd_presentes_calc,
                    qtd_ausentes_calc,
                    qtd_visitantes,
                    qtd_revistas,
                    qtd_biblias,
                    qtd_harpas,
                    ofertas,
                    id_aula=int(aula_editada["id_aula"]) if aula_editada is not None else None,
                )
                st.success("Chamada salva.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _render_relatorios(slug):
    st.markdown("### Relatorios da Escola Bíblica")
    c1, c2 = st.columns(2)
    inicio = c1.date_input("Data inicial", value=_inicio_mes(), key="ebd_rel_ini", format="DD/MM/YYYY")
    fim = c2.date_input("Data final", value=_hoje(), key="ebd_rel_fim", format="DD/MM/YYYY")
    if inicio > fim:
        st.error("A data inicial nao pode ser maior que a data final.")
        return

    aulas = listar_ebd_aulas(slug, inicio.isoformat(), fim.isoformat())
    resumo = relatorio_ebd_resumo_classes(slug, inicio.isoformat(), fim.isoformat())
    freq = relatorio_ebd_frequencia(slug, inicio.isoformat(), fim.isoformat())

    st.markdown("#### Relatorio geral")
    if aulas.empty:
        st.info("Nenhuma aula registrada no periodo selecionado.")
    else:
        totais = _totais_aulas(aulas)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de matriculados", totais["Matriculados"])
        c2.metric("Total de presentes", totais["Presentes"])
        c3.metric("Total de ausentes", totais["Ausentes"])
        c4.metric("Total de visitantes", totais["Visitantes"])
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Biblias", totais["Biblias"])
        c6.metric("Revistas", totais["Revistas"])
        c7.metric("Harpas", totais["Harpas"])
        c8.metric("Total de ofertas", _moeda(totais["Ofertas"]))

        st.markdown("#### Grafico por classe")
        classes = sorted(aulas["classe"].dropna().astype(str).unique().tolist())
        classe_escolhida = st.selectbox("Escolha a classe", classes, key="grafico_ebd_classe")
        aulas_classe = aulas[aulas["classe"].astype(str) == classe_escolhida]
        _grafico_totais_ebd(
            f"Resumo da classe {classe_escolhida}",
            _totais_aulas(aulas_classe),
        )

        st.markdown("#### Grafico geral da Escola Bíblica")
        _grafico_totais_ebd("Resumo geral da Escola Bíblica", totais)

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

    with st.expander("Relatorio individual por aluno", expanded=False):
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

    with st.expander("Aulas registradas", expanded=False):
        if aulas.empty:
            st.info("Nenhuma aula no periodo.")
        else:
            aulas_exibir = aulas.copy()
            aulas_exibir["data"] = aulas_exibir["data"].apply(_fmt_data)
            aulas_exibir["ofertas"] = aulas_exibir["ofertas"].apply(_moeda)
            aulas_exibir["frequencia"] = (
                aulas_exibir["presentes"].fillna(0)
                / aulas_exibir["matriculados"].replace(0, 1).fillna(1)
                * 100
            ).round(1).apply(_pct)
            st.dataframe(
                aulas_exibir[[
                    "data", "classe", "tema", "professor", "matriculados",
                    "presentes", "ausentes", "visitantes", "frequencia",
                    "qtd_revistas", "qtd_biblias", "qtd_harpas", "ofertas",
                ]],
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
        data = c1.date_input("Data", value=_hoje(), format="DD/MM/YYYY")
        classe_label = c2.selectbox("Classe", list(op_classes.keys()))
        st.markdown("#### Professor")
        professor, telefone_professor, funcao_professor = _selecionar_pessoa_escala(
            slug, "Professor", "escala_professor", obrigatorio=True
        )
        st.markdown("#### Superintendente")
        superintendente, telefone_superintendente, _ = _selecionar_pessoa_escala(
            slug, "Superintendente", "escala_superintendente"
        )
        st.markdown("#### Auxiliar")
        auxiliar, telefone_auxiliar, _ = _selecionar_pessoa_escala(
            slug, "Auxiliar", "escala_auxiliar"
        )
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
                    telefone_professor=telefone_professor,
                    funcao_professor=funcao_professor,
                    superintendente=superintendente,
                    telefone_superintendente=telefone_superintendente,
                    telefone_auxiliar=telefone_auxiliar,
                )
                st.success("Escala salva.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    c1, c2 = st.columns(2)
    inicio = c1.date_input("Inicio da escala", value=_inicio_mes(), key="escala_ini", format="DD/MM/YYYY")
    fim = c2.date_input("Fim da escala", value=_hoje() + datetime.timedelta(days=60), key="escala_fim", format="DD/MM/YYYY")
    escala = listar_ebd_escala(slug, inicio.isoformat(), fim.isoformat())
    if escala.empty:
        st.info("Nenhuma escala cadastrada para o periodo.")
        return
    exibir = escala.copy()
    exibir["data"] = exibir["data"].apply(_fmt_data)
    st.dataframe(
        exibir[[
            "data", "classe", "professor", "funcao_professor",
            "telefone_professor", "superintendente", "telefone_superintendente",
            "auxiliar", "telefone_auxiliar", "tema", "observacoes",
        ]],
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("#### Avisos por WhatsApp")
    st.caption("Filtre por data e clique para abrir o WhatsApp com a mensagem pronta.")
    modo_aviso = st.radio(
        "Filtro dos avisos",
        ["Todos do período", "Uma data específica"],
        horizontal=True,
        key="ebd_avisos_modo_data",
    )
    escala_avisos = escala.copy()
    if modo_aviso == "Uma data específica":
        datas_disponiveis = sorted(
            {
                _data_iso(data)
                for data in escala_avisos["data"].dropna().tolist()
                if _data_iso(data)
            }
        )
        if not datas_disponiveis:
            st.info("Nenhuma data disponível para avisos no período selecionado.")
            escala_avisos = escala_avisos.iloc[0:0]
        else:
            data_padrao = _data_iso(_hoje())
            index_data = datas_disponiveis.index(data_padrao) if data_padrao in datas_disponiveis else 0
            data_aviso = st.selectbox(
                "Data dos avisos",
                datas_disponiveis,
                index=index_data,
                format_func=_fmt_data,
                key="ebd_avisos_data",
            )
            escala_avisos = escala_avisos[
                escala_avisos["data"].apply(_data_iso) == data_aviso
            ].copy()

    if escala_avisos.empty:
        st.info("Nenhum aviso encontrado para o filtro selecionado.")

    for _, row in escala_avisos.iterrows():
        titulo = f'{_fmt_data(row["data"])} - {row.get("classe", "Escola Bíblica")} - {row["professor"]}'
        with st.expander(titulo):
            c1, c2 = st.columns(2)
            with c1:
                mensagem = _mensagem_escala(slug, row, row["professor"], "Professor")
                _botao_whatsapp("Avisar professor", row.get("telefone_professor", ""), mensagem, f"prof_{row['id_escala']}")
                st.text_area("Mensagem ao professor", value=mensagem, height=180, key=f"msg_prof_{row['id_escala']}")
            with c2:
                superintendente = str(row.get("superintendente", "") or "").strip()
                if superintendente:
                    mensagem = _mensagem_escala(slug, row, superintendente, "Superintendente")
                    _botao_whatsapp(
                        "Avisar superintendente",
                        row.get("telefone_superintendente", ""),
                        mensagem,
                        f"sup_{row['id_escala']}",
                    )
                    st.text_area("Mensagem ao superintendente", value=mensagem, height=180, key=f"msg_sup_{row['id_escala']}")
                else:
                    st.info("Nenhum superintendente informado para esta escala.")
            c3, _ = st.columns(2)
            with c3:
                auxiliar = str(row.get("auxiliar", "") or "").strip()
                if auxiliar:
                    mensagem = _mensagem_escala(slug, row, auxiliar, "Auxiliar")
                    _botao_whatsapp("Avisar auxiliar", row.get("telefone_auxiliar", ""), mensagem, f"aux_{row['id_escala']}")
                    st.text_area("Mensagem ao auxiliar", value=mensagem, height=180, key=f"msg_aux_{row['id_escala']}")
                else:
                    st.info("Nenhum auxiliar informado para esta escala.")
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


def _render_secretarios(slug):
    st.markdown("### Secretarios da Escola Bíblica")
    st.caption(
        "Cadastre acessos restritos: secretario de classe acessa somente a chamada "
        "da classe vinculada; secretario geral acessa todo o modulo Escola Bíblica."
    )
    df_classes = listar_ebd_classes(slug)
    if df_classes.empty:
        st.info("Cadastre uma classe antes de criar secretario de classe.")
    op_classes = {"Selecione": None}
    op_classes.update(_classes_opcoes(df_classes))

    with st.expander("Cadastrar secretario", expanded=False):
        with st.form("form_ebd_secretario"):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome")
            usuario = c2.text_input("Usuario", help="Use letras, numeros, ponto, hifen ou underline.")
            c3, c4 = st.columns(2)
            senha = c3.text_input("PIN de 4 digitos", type="password", max_chars=4)
            perfil_rotulo = c4.selectbox(
                "Perfil",
                ["Secretario de classe", "Secretario geral"],
            )
            perfil = "geral" if perfil_rotulo == "Secretario geral" else "classe"
            id_classe = None
            if perfil == "classe":
                classe_label = st.selectbox("Classe vinculada", list(op_classes.keys()))
                id_classe = op_classes[classe_label]
            c5, c6 = st.columns(2)
            telefone = c5.text_input("Telefone / WhatsApp")
            email = c6.text_input("E-mail")
            observacoes = st.text_area("Observacoes")
            if st.form_submit_button("Salvar secretario", type="primary"):
                try:
                    salvar_ebd_secretario(
                        slug, nome, usuario, senha, perfil, id_classe,
                        telefone, email, "Ativo", observacoes,
                    )
                    st.success("Secretario da Escola Bíblica cadastrado.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    df = listar_ebd_secretarios(slug)
    if df.empty:
        st.info("Nenhum secretario da Escola Bíblica cadastrado.")
        return

    exibir = df.copy()
    exibir["perfil"] = exibir["perfil"].map({
        "classe": "Secretario de classe",
        "geral": "Secretario geral",
    }).fillna(exibir["perfil"])
    st.dataframe(
        exibir[["nome", "usuario", "perfil", "classe", "telefone", "email", "situacao"]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Editar acesso")
    opcoes = {
        f'{int(row["id_secretario"])} - {row["nome"]} - {row["usuario"]}': row
        for _, row in df.iterrows()
    }
    selecionado = st.selectbox("Selecionar secretario", ["Selecione"] + list(opcoes.keys()))
    if selecionado == "Selecione":
        return
    row = opcoes[selecionado]
    id_secretario = int(row["id_secretario"])
    with st.form(f"form_editar_secretario_ebd_{id_secretario}"):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome", value=row["nome"])
        usuario = c2.text_input("Usuario", value=row["usuario"])
        perfil_atual = "Secretario geral" if row["perfil"] == "geral" else "Secretario de classe"
        c3, c4 = st.columns(2)
        senha = c3.text_input(
            "Novo PIN de 4 digitos",
            type="password",
            max_chars=4,
            help="Deixe em branco para manter o PIN atual.",
        )
        perfil_rotulo = c4.selectbox(
            "Perfil",
            ["Secretario de classe", "Secretario geral"],
            index=1 if perfil_atual == "Secretario geral" else 0,
        )
        perfil = "geral" if perfil_rotulo == "Secretario geral" else "classe"
        id_classe = None
        if perfil == "classe":
            classe_labels = list(op_classes.keys())
            classe_atual = "Selecione"
            for label, valor in op_classes.items():
                if valor and row.get("id_classe") and int(valor) == int(row["id_classe"]):
                    classe_atual = label
                    break
            classe_label = st.selectbox(
                "Classe vinculada",
                classe_labels,
                index=classe_labels.index(classe_atual) if classe_atual in classe_labels else 0,
            )
            id_classe = op_classes[classe_label]
        c5, c6 = st.columns(2)
        telefone = c5.text_input("Telefone / WhatsApp", value=row.get("telefone", ""))
        email = c6.text_input("E-mail", value=row.get("email", ""))
        situacao = st.selectbox(
            "Situacao",
            ["Ativo", "Inativo"],
            index=0 if row.get("situacao") == "Ativo" else 1,
        )
        observacoes = st.text_area("Observacoes", value=row.get("observacoes", ""))
        if st.form_submit_button("Atualizar secretario", type="primary"):
            try:
                salvar_ebd_secretario(
                    slug, nome, usuario, senha, perfil, id_classe, telefone,
                    email, situacao, observacoes, id_secretario,
                )
                st.success("Secretario da Escola Bíblica atualizado.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if confirmar_exclusao(f"inativar_secretario_ebd_{id_secretario}", "Inativar secretario selecionado"):
        inativar_ebd_secretario(slug, id_secretario)
        st.success("Secretario inativado.")
        st.rerun()


def render():
    st.subheader("Escola Bíblica")
    st.caption("Gestao de classes, chamada, frequencia e escala de professores da Escola Bíblica.")
    slug = slug_da_sessao()
    if not slug:
        st.error("Sessao invalida. Faca login novamente.")
        return

    def render_seguro(titulo, fn, *args):
        try:
            fn(*args)
        except Exception as exc:
            st.error(
                f"Nao foi possivel carregar {titulo}. "
                f"Tipo do erro: {type(exc).__name__}. Detalhe: {exc}"
            )

    _render_cards_superintendentes(slug)

    secretario = st.session_state.get("secretario_ebd", {})
    modo = st.session_state.get("modo", "")
    if modo == "pastor_auxiliar":
        st.info("Acesso de Pastor Auxiliar: somente relatórios da Escola Bíblica.")
        render_seguro("os relatórios da Escola Bíblica", _render_relatorios, slug)
        return
    if modo == "secretario_ebd" and isinstance(secretario, dict):
        perfil = secretario.get("perfil", "classe")
        if perfil == "classe":
            st.info(
                f"Acesso de secretario de classe: {secretario.get('classe', 'classe vinculada')}."
            )
            render_seguro("a chamada da Escola Bíblica", _render_chamada, slug, secretario.get("id_classe"))
            return
        st.info("Acesso de secretario geral da Escola Bíblica.")

    pode_gerenciar_secretarios = (
        modo != "secretario_ebd"
        or secretario.get("perfil") == "geral"
    )
    abas = [
        "Classes e alunos",
        "Chamada",
        "Relatorios",
        "Escala de professores",
    ]
    if pode_gerenciar_secretarios:
        abas.append("Secretarios")

    tabs = st.tabs(abas)
    tab_classes, tab_chamada, tab_relatorios, tab_escala = tabs[:4]
    with tab_classes:
        render_seguro("classes e alunos", _render_classes, slug)
    with tab_chamada:
        render_seguro("a chamada da Escola Bíblica", _render_chamada, slug)
    with tab_relatorios:
        render_seguro("os relatórios da Escola Bíblica", _render_relatorios, slug)
    with tab_escala:
        render_seguro("a escala de professores", _render_escala, slug)
    if pode_gerenciar_secretarios:
        with tabs[4]:
            render_seguro("secretários da Escola Bíblica", _render_secretarios, slug)

