"""
Modulo de aniversariantes — cards visuais, calendario e WhatsApp.
"""

import calendar
import datetime
import urllib.parse
import pandas as pd
import streamlit as st

from data.repository import carregar_cadastros
from utils.helpers import slug_da_sessao, gerar_csv


MESES_PT = {
    1: "Janeiro",   2: "Fevereiro", 3: "Marco",     4: "Abril",
    5: "Maio",      6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro", 10: "Outubro",  11: "Novembro", 12: "Dezembro",
}

DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]


def _injetar_css():
    st.markdown("""
    <style>
    .aniv-card {
        background: white;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        border-left: 4px solid #0F6E56;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 14px;
    }
    .aniv-card.hoje    { border-left-color: #D85A30; background: #FFF7F2; }
    .aniv-card.semana  { border-left-color: #F5A623; }

    .aniv-icone {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        background: linear-gradient(135deg, #1D9E75, #0F6E56);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.4rem;
        flex-shrink: 0;
    }
    .aniv-card.hoje .aniv-icone {
        background: linear-gradient(135deg, #F5A623, #D85A30);
    }

    .aniv-info { flex: 1; }
    .aniv-nome {
        font-size: 1rem;
        font-weight: 700;
        color: #1a1a1a;
        margin-bottom: 2px;
    }
    .aniv-data { font-size: 0.8rem; color: #666; }
    .aniv-idade {
        font-size: 0.82rem;
        font-weight: 600;
        color: #0F6E56;
        margin-top: 2px;
    }
    .aniv-card.hoje .aniv-idade { color: #D85A30; }

    .cal-titulo {
        text-align: center;
        font-weight: 700;
        font-size: 1.05rem;
        color: #0F6E56;
        margin-bottom: 8px;
    }
    .cal-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 4px;
    }
    .cal-cab {
        text-align: center;
        font-size: 0.72rem;
        font-weight: 700;
        color: #888;
        padding: 4px 0;
        text-transform: uppercase;
    }
    .cal-dia {
        aspect-ratio: 1;
        border-radius: 6px;
        padding: 4px;
        background: #f8f9fa;
        text-align: center;
        font-size: 0.78rem;
        min-height: 38px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    .cal-dia.vazio { background: transparent; }
    .cal-dia.hoje { background: #D85A30; color: white; font-weight: 700; }
    .cal-dia.tem-aniv {
        background: #E8F5E9;
        border: 2px solid #1D9E75;
        font-weight: 600;
    }
    .cal-dia.hoje.tem-aniv { background: #D85A30; border-color: #D85A30; }
    .cal-aniv-marcador { font-size: 0.6rem; color: #0F6E56; font-weight: 700; }
    .cal-dia.hoje .cal-aniv-marcador { color: white; }

    .aniv-vazio {
        text-align: center;
        padding: 30px 20px;
        color: #888;
        font-style: italic;
    }
    </style>
    """, unsafe_allow_html=True)


def _limpar_tel(tel):
    return "".join(c for c in str(tel) if c.isdigit())


def _link_whatsapp(tel, mensagem):
    tel_limpo = _limpar_tel(tel)
    if not tel_limpo:
        return ""
    if not tel_limpo.startswith("55"):
        tel_limpo = "55" + tel_limpo
    msg_enc = urllib.parse.quote(mensagem)
    return f"https://wa.me/{tel_limpo}?text={msg_enc}"


def _preparar_df_aniv(df_cad):
    if df_cad.empty or "data_nascimento" not in df_cad.columns:
        return pd.DataFrame()

    df = df_cad[df_cad["tipo_cadastro"].str.upper() == "MEMBRO"].copy()
    df = df[df["data_nascimento"].fillna("").str.strip() != ""]

    if df.empty:
        return df

    def parse_data(d):
        try:
            return datetime.date.fromisoformat(str(d))
        except Exception:
            return None

    df["dt_nasc"] = df["data_nascimento"].apply(parse_data)
    df = df[df["dt_nasc"].notna()].copy()

    if df.empty:
        return df

    hoje = datetime.date.today()
    df["dia_aniv"] = df["dt_nasc"].apply(lambda d: d.day)
    df["mes_aniv"] = df["dt_nasc"].apply(lambda d: d.month)
    df["idade"]    = df["dt_nasc"].apply(
        lambda d: hoje.year - d.year - (
            (hoje.month, hoje.day) < (d.month, d.day)
        )
    )
    df["aniv_str"] = df["dt_nasc"].apply(lambda d: d.strftime("%d/%m"))

    if "sexo" not in df.columns:
        df["sexo"] = ""

    return df


def _card_aniv(nome, data_str, idade, telefone, nome_igreja, sexo="", classe=""):
    """Renderiza card e botao do WhatsApp com mensagem personalizada por sexo."""
    inicial = (nome[0] if nome else "?").upper()
    ano_str = "anos" if idade != 1 else "ano"

    st.markdown(f"""
    <div class="aniv-card {classe}">
        <div class="aniv-icone">{inicial}</div>
        <div class="aniv-info">
            <div class="aniv-nome">{nome}</div>
            <div class="aniv-data">🎂 {data_str}</div>
            <div class="aniv-idade">{idade} {ano_str}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tel_limpo = _limpar_tel(telefone)
    if tel_limpo:
        # Tratamento conforme sexo
        sexo_up = str(sexo).strip().upper()
        if sexo_up.startswith("M"):
            tratamento = "irmao"
        elif sexo_up.startswith("F"):
            tratamento = "irma"
        else:
            tratamento = "irmao(a)"

        mensagem = (
            f"A paz do Senhor {tratamento} {nome}! 🙏\n\n"
            f"A familia {nome_igreja} deseja a voce um feliz aniversario! "
            f"Oramos para que Deus continue te abencoando ricamente e agracie "
            f"com muitos anos de vida, e que estes sejam repletos de muita "
            f"saude, paz, alegria, felicidade e muitas realizacoes. "
            f"Parabens pelos seus {idade} {ano_str} de vida! 🎉🎂"
        )
        link = _link_whatsapp(telefone, mensagem)
        if link:
            st.markdown(
                f'<a href="{link}" target="_blank" '
                f'style="display:inline-block;background:#25D366;color:white;'
                f'padding:6px 14px;border-radius:6px;text-decoration:none;'
                f'font-size:0.82rem;margin-bottom:14px">'
                f'💬 Enviar parabens pelo WhatsApp</a>',
                unsafe_allow_html=True,
            )


def _renderizar_calendario(df_aniv, ano, mes):
    hoje = datetime.date.today()
    dias_com_aniv = set(df_aniv[df_aniv["mes_aniv"] == mes]["dia_aniv"].tolist())

    cal = calendar.Calendar(firstweekday=0)
    dias_mes = cal.monthdayscalendar(ano, mes)

    nome_mes = MESES_PT[mes]
    st.markdown(f'<div class="cal-titulo">{nome_mes} {ano}</div>', unsafe_allow_html=True)

    html = '<div class="cal-grid">'
    for d in DIAS_SEMANA:
        html += f'<div class="cal-cab">{d}</div>'

    for semana in dias_mes:
        for dia in semana:
            if dia == 0:
                html += '<div class="cal-dia vazio"></div>'
            else:
                classes = ["cal-dia"]
                if dia in dias_com_aniv:
                    classes.append("tem-aniv")
                if ano == hoje.year and mes == hoje.month and dia == hoje.day:
                    classes.append("hoje")
                marcador = '<div class="cal-aniv-marcador">🎂</div>' if dia in dias_com_aniv else ""
                html += (
                    f'<div class="{" ".join(classes)}">'
                    f'<div>{dia}</div>{marcador}</div>'
                )

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render():
    _injetar_css()

    slug   = slug_da_sessao()
    igreja = st.session_state.get("igreja", {})
    nome_igreja = igreja.get("nome", "Igreja")

    df_cad  = carregar_cadastros(slug)
    df_aniv = _preparar_df_aniv(df_cad)

    st.subheader("🎂 Aniversariantes")
    st.caption("Acompanhe os aniversariantes dos membros da igreja.")

    if df_aniv.empty:
        st.info("Nenhum membro com data de nascimento cadastrada ainda.")
        st.caption("Para usar este modulo, cadastre a data de nascimento dos membros.")
        return

    hoje = datetime.date.today()

    aba_hoje, aba_semana, aba_mes, aba_cal = st.tabs([
        "Hoje", "Semana", "Mes", "📅 Calendario"
    ])

    # ── ABA: HOJE ─────────────────────────────────────────────────────────
    with aba_hoje:
        dias_pt = {0:"Segunda",1:"Terca",2:"Quarta",3:"Quinta",4:"Sexta",5:"Sabado",6:"Domingo"}
        st.markdown(f"**{hoje.strftime('%d/%m/%Y')}** — {dias_pt[hoje.weekday()]}")

        hoje_df = df_aniv[
            (df_aniv["dia_aniv"] == hoje.day) &
            (df_aniv["mes_aniv"] == hoje.month)
        ].sort_values("nome")

        if hoje_df.empty:
            st.markdown(
                '<div class="aniv-vazio">Nenhum aniversariante hoje. 🌷</div>',
                unsafe_allow_html=True,
            )
        else:
            st.success(f"🎉 {len(hoje_df)} aniversariante(s) hoje!")
            for _, r in hoje_df.iterrows():
                _card_aniv(
                    nome=str(r["nome"]),
                    data_str=r["aniv_str"],
                    idade=int(r["idade"]),
                    telefone=str(r.get("telefone", "")),
                    nome_igreja=nome_igreja,
                    sexo=str(r.get("sexo", "")),
                    classe="hoje",
                )

    # ── ABA: SEMANA ───────────────────────────────────────────────────────
    with aba_semana:
        ini_sem = hoje - datetime.timedelta(days=hoje.weekday())
        fim_sem = ini_sem + datetime.timedelta(days=6)
        st.markdown(f"De **{ini_sem.strftime('%d/%m')}** a **{fim_sem.strftime('%d/%m/%Y')}**")

        dias_semana_set = set()
        d = ini_sem
        while d <= fim_sem:
            dias_semana_set.add((d.day, d.month))
            d += datetime.timedelta(days=1)

        sem_df = df_aniv[
            df_aniv.apply(lambda r: (int(r["dia_aniv"]), int(r["mes_aniv"])) in dias_semana_set, axis=1)
        ].sort_values(["mes_aniv", "dia_aniv", "nome"])

        if sem_df.empty:
            st.markdown(
                '<div class="aniv-vazio">Nenhum aniversariante nesta semana.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info(f"🎈 {len(sem_df)} aniversariante(s) nesta semana")
            for _, r in sem_df.iterrows():
                eh_hoje = (int(r["dia_aniv"]) == hoje.day and int(r["mes_aniv"]) == hoje.month)
                _card_aniv(
                    nome=str(r["nome"]),
                    data_str=r["aniv_str"],
                    idade=int(r["idade"]),
                    telefone=str(r.get("telefone", "")),
                    nome_igreja=nome_igreja,
                    sexo=str(r.get("sexo", "")),
                    classe="hoje" if eh_hoje else "semana",
                )

            st.divider()
            df_exp = sem_df[["nome", "aniv_str", "idade", "telefone"]].copy()
            df_exp.columns = ["Nome", "Data", "Idade", "Telefone"]
            st.download_button(
                "📥 Exportar CSV da semana",
                gerar_csv(df_exp),
                f"aniversariantes_semana_{hoje.strftime('%Y%m%d')}.csv",
                "text/csv",
            )

    # ── ABA: MES ──────────────────────────────────────────────────────────
    with aba_mes:
        st.markdown(f"Mes de **{MESES_PT[hoje.month]}/{hoje.year}**")

        mes_df = df_aniv[df_aniv["mes_aniv"] == hoje.month].sort_values(["dia_aniv", "nome"])

        if mes_df.empty:
            st.markdown(
                '<div class="aniv-vazio">Nenhum aniversariante este mes.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info(f"🎊 {len(mes_df)} aniversariante(s) em {MESES_PT[hoje.month]}")
            for _, r in mes_df.iterrows():
                eh_hoje = (int(r["dia_aniv"]) == hoje.day and int(r["mes_aniv"]) == hoje.month)
                _card_aniv(
                    nome=str(r["nome"]),
                    data_str=r["aniv_str"],
                    idade=int(r["idade"]),
                    telefone=str(r.get("telefone", "")),
                    nome_igreja=nome_igreja,
                    sexo=str(r.get("sexo", "")),
                    classe="hoje" if eh_hoje else "",
                )

            st.divider()
            df_exp = mes_df[["nome", "aniv_str", "idade", "telefone"]].copy()
            df_exp.columns = ["Nome", "Data", "Idade", "Telefone"]
            st.download_button(
                "📥 Exportar CSV do mes",
                gerar_csv(df_exp),
                f"aniversariantes_{MESES_PT[hoje.month]}_{hoje.year}.csv",
                "text/csv",
            )

    # ── ABA: CALENDARIO ───────────────────────────────────────────────────
    with aba_cal:
        c1, c2 = st.columns(2)
        with c1:
            mes_sel = st.selectbox(
                "Mes",
                list(MESES_PT.keys()),
                index=hoje.month - 1,
                format_func=lambda m: MESES_PT[m],
                key="aniv_cal_mes",
            )
        with c2:
            ano_sel = st.number_input(
                "Ano", min_value=2020, max_value=2100,
                value=hoje.year, key="aniv_cal_ano",
            )

        _renderizar_calendario(df_aniv, int(ano_sel), int(mes_sel))

        st.markdown("")
        st.caption("🎂 = dia com aniversariante  |  Vermelho = hoje")

        mes_sel_df = df_aniv[df_aniv["mes_aniv"] == int(mes_sel)].sort_values(["dia_aniv", "nome"])
        if not mes_sel_df.empty:
            st.divider()
            st.markdown(f"**Aniversariantes de {MESES_PT[int(mes_sel)]}:**")
            tabela = mes_sel_df[["aniv_str", "nome", "idade"]].copy()
            tabela.columns = ["Data", "Nome", "Idade atual"]
            st.dataframe(tabela, use_container_width=True, hide_index=True)
