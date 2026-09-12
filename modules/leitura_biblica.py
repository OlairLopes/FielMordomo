import datetime
import hashlib
import html
import io
import logging
import re

import pandas as pd
import requests
import streamlit as st

from data.repository import (
    PLANO_LEITURA_PADRAO,
    autenticar_leitor_biblia,
    cadastrar_leitor_biblia,
    carregar_cadastros,
    confirmar_leitura_biblica,
    definir_senha_leitor_biblia,
    importar_leitores_biblia_em_lote,
    leitor_biblia_precisa_definir_senha,
    leitura_ja_confirmada,
    listar_igrejas,
    listar_planos_leitura_biblica,
    localizar_leitor_plano_biblico,
    obter_audio_biblico_cache,
    obter_capitulo_biblico_cache,
    obter_leitura_do_dia,
    salvar_audio_biblico_cache,
    salvar_capitulo_biblico_cache,
)
from utils.helpers import normalizar_data_digitada

LOGGER = logging.getLogger(__name__)

BIBLIA_FONTE_BASE = "https://raw.githubusercontent.com/maatheusgois/bible/main/versions/pt-br"
BIBLIA_VERSAO_PADRAO = "nvi"

BIBLIA_VERSOES = {
    "nvi": "NVI — Nova Versão Internacional",
    "arc": "ARC — Almeida Revista e Corrigida",
    "aa": "ARA — Almeida Revisada e Atualizada",
    "acf": "ACF — Almeida Corrigida e Fiel",
    "kja": "KJA — King James Atualizada",
}

LIVRO_ABREV = {
    "gênesis": "gn", "êxodo": "ex", "levítico": "lv", "números": "nm", "deuteronômio": "dt",
    "josué": "js", "juízes": "jz", "rute": "rt",
    "1 samuel": "1sm", "2 samuel": "2sm",
    "1 reis": "1rs", "2 reis": "2rs",
    "1 crônicas": "1cr", "2 crônicas": "2cr",
    "esdras": "ed", "neemias": "ne", "ester": "et",
    "jó": "job", "salmos": "sl", "provérbios": "pv", "eclesiastes": "ec",
    "cânticos": "ct", "cântico dos cânticos": "ct",
    "isaías": "is", "jeremias": "jr", "lamentações": "lm", "ezequiel": "ez", "daniel": "dn",
    "oséias": "os", "oseias": "os", "joel": "jl", "amós": "am", "obadias": "ob", "jonas": "jn",
    "miquéias": "mq", "miqueias": "mq", "naum": "na", "habacuque": "hc", "sofonias": "sf",
    "ageu": "ag", "zacarias": "zc", "malaquias": "ml",
    "mateus": "mt", "marcos": "mc", "lucas": "lc", "joão": "jo", "atos": "at",
    "romanos": "rm", "1 coríntios": "1co", "2 coríntios": "2co", "gálatas": "gl",
    "efésios": "ef", "filipenses": "fp", "colossenses": "cl",
    "1 tessalonicenses": "1ts", "2 tessalonicenses": "2ts",
    "1 timóteo": "1tm", "2 timóteo": "2tm", "tito": "tt", "filemom": "fm",
    "hebreus": "hb", "tiago": "tg", "1 pedro": "1pe", "2 pedro": "2pe",
    "1 joão": "1jo", "2 joão": "2jo", "3 joão": "3jo", "judas": "jd", "apocalipse": "ap",
}

# Traduz a abreviacao interna (LIVRO_ABREV, acima) para o id de livro usado
# pela fonte de texto biblico (raw.githubusercontent.com/maatheusgois/bible),
# que mistura codigos em ingles/portugues. Conferido 1-a-1 pelo nome do livro
# e pela quantidade de capitulos de cada arquivo.
MAPA_LIVRO_FONTE = {
    "gn": "gn", "ex": "ex", "lv": "lv", "nm": "nm", "dt": "dt",
    "js": "js", "jz": "jud", "rt": "rt",
    "1sm": "1sm", "2sm": "2sm", "1rs": "1kgs", "2rs": "2kgs",
    "1cr": "1ch", "2cr": "2ch", "ed": "ezr", "ne": "ne", "et": "et",
    "job": "job", "sl": "ps", "pv": "prv", "ec": "ec", "ct": "so",
    "is": "is", "jr": "jr", "lm": "lm", "ez": "ez", "dn": "dn",
    "os": "ho", "jl": "jl", "am": "am", "ob": "ob", "jn": "jn",
    "mq": "mi", "na": "na", "hc": "hk", "sf": "zp",
    "ag": "hg", "zc": "zc", "ml": "ml",
    "mt": "mt", "mc": "mk", "lc": "lk", "jo": "jo", "at": "act",
    "rm": "rm", "1co": "1co", "2co": "2co", "gl": "gl",
    "ef": "eph", "fp": "ph", "cl": "cl",
    "1ts": "1ts", "2ts": "2ts", "1tm": "1tm", "2tm": "2tm",
    "tt": "tt", "fm": "phm", "hb": "hb", "tg": "jm",
    "1pe": "1pe", "2pe": "2pe", "1jo": "1jo", "2jo": "2jo", "3jo": "3jo",
    "jd": "jd", "ap": "re",
}

_REF_COM_LIVRO_RE = re.compile(
    r'^([1-3]?\s?[A-Za-zÀ-ÿ]+(?:\s[A-Za-zÀ-ÿ]+)*?)\s*(\d+)(?:[.:](\d+))?(?:-(\d+)(?:[.:](\d+))?)?$'
)
_REF_CONTINUACAO_RE = re.compile(r'^(\d+)(?:[.:](\d+))?(?:-(\d+)(?:[.:](\d+))?)?$')


def _abrev_livro(nome):
    chave = nome.strip().lower()
    if chave in LIVRO_ABREV:
        return LIVRO_ABREV[chave]
    chave_sem_espaco = chave.replace(" ", "")
    for k, v in LIVRO_ABREV.items():
        if k.replace(" ", "") == chave_sem_espaco:
            return v
    return None


def _interpretar_grupos(cap_ini, v_ini_raw, end_raw, v_fim_raw):
    """Resolve a ambiguidade do regex: sem verso inicial, o "fim" e capitulo;
    com verso inicial e um segundo verso, o "fim" e capitulo (span entre
    capitulos); com verso inicial e sem segundo verso, o "fim" e verso final
    no mesmo capitulo."""
    if v_ini_raw is None:
        return None, (int(end_raw) if end_raw else cap_ini), None
    vers_ini = int(v_ini_raw)
    if v_fim_raw is not None:
        return vers_ini, int(end_raw), int(v_fim_raw)
    if end_raw is not None:
        return vers_ini, cap_ini, int(end_raw)
    return vers_ini, cap_ini, vers_ini


def _parsear_passagens(texto):
    """Converte uma string de passagens (ex.: "Lucas 5.27-39; Gênesis 1-3") em
    uma lista de unidades de leitura, cada uma com livro/abreviacao/capitulos/
    versos, prontas para buscar na API biblica."""
    unidades = []
    livro_atual = None
    for parte in str(texto or "").split(";"):
        for pedaco in parte.split(","):
            pedaco = pedaco.strip()
            if not pedaco:
                continue
            m_cont = _REF_CONTINUACAO_RE.match(pedaco)
            if m_cont and livro_atual:
                nome_candidato, abrev = livro_atual
                cap_ini = int(m_cont.group(1))
                vers_ini, cap_fim, vers_fim = _interpretar_grupos(
                    cap_ini, m_cont.group(2), m_cont.group(3), m_cont.group(4)
                )
                unidades.append({
                    "livro": nome_candidato, "abrev": abrev,
                    "cap_ini": cap_ini, "cap_fim": cap_fim,
                    "vers_ini": vers_ini, "vers_fim": vers_fim,
                })
                continue
            m = _REF_COM_LIVRO_RE.match(pedaco)
            if not m:
                continue
            nome_candidato = m.group(1).strip()
            abrev = _abrev_livro(nome_candidato)
            if not abrev:
                continue
            livro_atual = (nome_candidato, abrev)
            cap_ini = int(m.group(2))
            vers_ini, cap_fim, vers_fim = _interpretar_grupos(
                cap_ini, m.group(3), m.group(4), m.group(5)
            )
            unidades.append({
                "livro": nome_candidato, "abrev": abrev,
                "cap_ini": cap_ini, "cap_fim": cap_fim,
                "vers_ini": vers_ini, "vers_fim": vers_fim,
            })
    return unidades


@st.cache_data(ttl=3600, show_spinner=False)
def _buscar_livro_completo(id_fonte, versao):
    """Busca o JSON do livro inteiro na fonte (raw.githubusercontent.com) e
    retorna a lista de capitulos (cada um, uma lista de textos de versos)."""
    try:
        resp = requests.get(
            f"{BIBLIA_FONTE_BASE}/{versao}/{id_fonte}/{id_fonte}.json",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("chapters", [])
    except Exception:
        LOGGER.exception("Falha ao buscar livro biblico %s (versao %s).", id_fonte, versao)
        return None


def _buscar_capitulo(abrev_livro, capitulo, versao=BIBLIA_VERSAO_PADRAO):
    cache = obter_capitulo_biblico_cache(versao, abrev_livro, capitulo)
    if cache is not None:
        return cache

    id_fonte = MAPA_LIVRO_FONTE.get(abrev_livro)
    if not id_fonte:
        return None

    capitulos = _buscar_livro_completo(id_fonte, versao)
    if capitulos is None:
        return None
    if not (1 <= capitulo <= len(capitulos)):
        return []

    versos = [
        {"number": i + 1, "text": texto}
        for i, texto in enumerate(capitulos[capitulo - 1])
    ]
    if versos:
        salvar_capitulo_biblico_cache(versao, abrev_livro, capitulo, versos)
    return versos


def _versos_da_unidade(unidade, versao):
    """Retorna lista de tuplas (capitulo, versos_filtrados) da unidade, ou
    None se algum capitulo nao pode ser carregado."""
    resultado = []
    for cap in range(unidade["cap_ini"], unidade["cap_fim"] + 1):
        versos = _buscar_capitulo(unidade["abrev"], cap, versao)
        if versos is None:
            return None
        v_ini = unidade["vers_ini"] if cap == unidade["cap_ini"] and unidade["vers_ini"] else 1
        v_fim = unidade["vers_fim"] if cap == unidade["cap_fim"] and unidade["vers_fim"] else None
        filtrados = [
            v for v in versos
            if v.get("number") is not None
            and v["number"] >= v_ini
            and (not v_fim or v["number"] <= v_fim)
        ]
        resultado.append((cap, filtrados))
    return resultado


def _texto_da_unidade(unidade, versao=BIBLIA_VERSAO_PADRAO):
    capitulos = _versos_da_unidade(unidade, versao)
    if capitulos is None:
        return None
    varios_capitulos = len(capitulos) > 1
    linhas = []
    for cap, versos in capitulos:
        if varios_capitulos and cap != unidade["cap_ini"]:
            linhas.append(f"---\n##### {unidade['livro']} {cap}")
        for verso in versos:
            linhas.append(f"**{verso['number']}** {verso.get('text', '')}")
    return "\n\n".join(linhas)


def _texto_audio_da_unidade(unidade, versao=BIBLIA_VERSAO_PADRAO):
    """Versao em texto corrido (sem numeros de versiculo) da unidade,
    pronta para sintese de voz."""
    capitulos = _versos_da_unidade(unidade, versao)
    if capitulos is None:
        return None
    varios_capitulos = len(capitulos) > 1
    partes = []
    for cap, versos in capitulos:
        if varios_capitulos:
            partes.append(f"Capítulo {cap}.")
        partes.extend(verso.get("text", "") for verso in versos if verso.get("text"))
    return " ".join(partes)


def _audio_da_unidade(unidade, versao=BIBLIA_VERSAO_PADRAO):
    """Gera (ou recupera do cache) o audio MP3 da unidade via gTTS."""
    texto_audio = _texto_audio_da_unidade(unidade, versao)
    if not texto_audio:
        return None

    chave = hashlib.sha256(f"{unidade['abrev']}|{texto_audio}".encode()).hexdigest()
    audio_bytes = obter_audio_biblico_cache(versao, chave)
    if audio_bytes is not None:
        return audio_bytes

    try:
        from gtts import gTTS

        buffer = io.BytesIO()
        gTTS(text=texto_audio, lang="pt", tld="com.br").write_to_fp(buffer)
        audio_bytes = buffer.getvalue()
    except Exception:
        LOGGER.exception("Falha ao gerar audio biblico para %s.", unidade.get("abrev"))
        return None

    salvar_audio_biblico_cache(versao, chave, audio_bytes)
    return audio_bytes


def _rotulo_unidade(unidade):
    if unidade["cap_ini"] == unidade["cap_fim"]:
        base = f"{unidade['livro']} {unidade['cap_ini']}"
    else:
        base = f"{unidade['livro']} {unidade['cap_ini']}-{unidade['cap_fim']}"
    if unidade["vers_ini"] and not (
        unidade["vers_ini"] == 1 and unidade["vers_fim"] is None
    ):
        if unidade["cap_ini"] == unidade["cap_fim"]:
            base += f".{unidade['vers_ini']}-{unidade['vers_fim']}"
    return base


def _render_texto_biblico(passagens_texto, versao=BIBLIA_VERSAO_PADRAO):
    unidades = _parsear_passagens(passagens_texto)
    if not unidades:
        return

    st.markdown("##### Ler o texto")
    versao_atual = st.selectbox(
        "Versão da Bíblia",
        list(BIBLIA_VERSOES.keys()),
        index=list(BIBLIA_VERSOES.keys()).index(versao) if versao in BIBLIA_VERSOES else 0,
        format_func=lambda k: BIBLIA_VERSOES[k],
        key="leitura_versao_biblia",
    )
    for idx, unidade in enumerate(unidades):
        with st.expander(f"📖 {_rotulo_unidade(unidade)}"):
            texto = _texto_da_unidade(unidade, versao_atual)
            if texto is None:
                st.warning(
                    "Não foi possível carregar o texto agora. Tente novamente em instantes."
                )
            elif not texto:
                st.info("Texto indisponível para esta passagem.")
            else:
                st.markdown(texto)
                audio_key = f"leitura_audio_{versao_atual}_{idx}"
                if st.button("🔊 Ouvir este trecho", key=f"btn_{audio_key}"):
                    with st.spinner("Gerando áudio..."):
                        st.session_state[audio_key] = _audio_da_unidade(unidade, versao_atual)
                if st.session_state.get(audio_key):
                    st.audio(st.session_state[audio_key], format="audio/mp3")
                elif audio_key in st.session_state:
                    st.warning(
                        "Não foi possível gerar o áudio agora. Tente novamente em instantes."
                    )


def _parse_data_nascimento(valor):
    texto = normalizar_data_digitada(str(valor or "").strip())
    if not texto:
        return ""
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return ""


def _dia_do_plano(data):
    return min(data.timetuple().tm_yday, 365)


def _html_sem_indentacao(html_final):
    return "\n".join(linha.strip() for linha in str(html_final).splitlines() if linha.strip())


def _hero_html(planos):
    badges = "".join(
        f'<span class="leitura-hero-badge">{html.escape(p["nome"])}</span>' for p in planos
    )
    return _html_sem_indentacao(f"""
        <div class="leitura-hero">
            <span class="leitura-hero-eyebrow">Plano de leitura</span>
            <div class="leitura-hero-badges">{badges}</div>
            <h1 class="leitura-hero-title">Plano de Leitura Bíblica</h1>
            <p class="leitura-hero-subtitle">Leia a sua Bíblia todos os dias.</p>
        </div>
    """)


def _card_leitura_html(dia_numero, data_escolhida, passagens, tema=""):
    pills = "".join(
        f'<span class="leitura-pill">{html.escape(p.strip())}</span>'
        for p in passagens.split(";")
        if p.strip()
    )
    tema_html = (
        f'<p class="leitura-tema">{html.escape(tema)}</p>' if tema else ""
    )
    return _html_sem_indentacao(f"""
        <div class="leitura-card">
            <div class="leitura-card-header">
                <span class="leitura-day-badge">Dia {dia_numero}</span>
                <span class="leitura-date">{data_escolhida.strftime('%d/%m/%Y')}</span>
            </div>
            {tema_html}
            <p class="leitura-passagens-label">Passagens de hoje</p>
            <div class="leitura-passagens">{pills}</div>
        </div>
    """)


def _selecionar_igreja_publica():
    try:
        igrejas = listar_igrejas()
    except Exception:
        LOGGER.exception("Nao foi possivel carregar a lista de igrejas.")
        igrejas = pd.DataFrame()

    if igrejas.empty:
        st.error("Nenhuma igreja cadastrada no sistema.")
        return None

    igrejas = igrejas[igrejas["ativa"].astype(int) == 1].copy()
    if igrejas.empty:
        st.error("Nenhuma igreja ativa encontrada.")
        return None

    opcoes = {
        f'{row["nome"]} ({row["slug"]})': str(row["slug"])
        for _, row in igrejas.sort_values("nome").iterrows()
    }

    with st.form("form_identificar_igreja_leitura"):
        st.markdown("#### Identificação da igreja")
        selecionada = st.selectbox("Igreja / congregação", list(opcoes.keys()))
        continuar = st.form_submit_button("Continuar", type="primary")
    if not continuar:
        return None

    slug = opcoes.get(selecionada, "").strip().lower()
    if not slug:
        st.error("Selecione uma igreja.")
        return None
    try:
        carregar_cadastros(slug)
    except Exception:
        LOGGER.exception("Falha ao carregar cadastros para o plano de leitura.")
        st.error("Nao foi possivel localizar essa igreja.")
        return None
    st.session_state["leitura_slug"] = slug
    return slug


def _identificar_membro(slug):
    st.caption(
        "Para membros já cadastrados na igreja. Se você não é membro, use a "
        "aba de login ou cadastro de leitor."
    )
    with st.form("form_identificar_membro_leitura"):
        c1, c2 = st.columns(2)
        cpf = c1.text_input("CPF")
        data_nascimento_txt = c2.text_input(
            "Data de nascimento", placeholder="Ex.: 26/06/1979 ou 26061979"
        )
        confirmar = st.form_submit_button("Continuar", type="primary")

    if not confirmar:
        return

    data_nascimento = _parse_data_nascimento(data_nascimento_txt)
    if not cpf or not data_nascimento:
        st.error("Informe CPF e data de nascimento válidos.")
        return

    cadastro = localizar_leitor_plano_biblico(slug, cpf, data_nascimento)
    if not cadastro:
        st.error(
            "Cadastro não encontrado. Confira o CPF e a data de nascimento, "
            "ou use a aba de login/cadastro de leitor se você não é membro."
        )
        return

    st.session_state["leitura_cadastro"] = cadastro
    st.rerun()


def _login_leitor(slug):
    st.caption(
        "Use o número de WhatsApp cadastrado. Se a igreja te cadastrou em lote e "
        "esta é sua primeira vez aqui, escolha uma senha abaixo para criar seu acesso."
    )
    with st.form("form_login_leitor"):
        telefone = st.text_input("Número de WhatsApp", placeholder="Ex.: (11) 99999-8888")
        senha = st.text_input("Senha", type="password")
        confirmar = st.form_submit_button("Entrar", type="primary")

    if not confirmar:
        return

    if not telefone.strip() or not senha:
        st.error("Informe o número de WhatsApp e a senha.")
        return

    if leitor_biblia_precisa_definir_senha(slug, telefone):
        try:
            cadastro = definir_senha_leitor_biblia(slug, telefone, senha)
        except ValueError as erro:
            st.error(str(erro))
            return
        st.session_state["leitura_cadastro"] = cadastro
        st.success("Senha criada com sucesso! Use-a para entrar da próxima vez.")
        st.rerun()

    cadastro = autenticar_leitor_biblia(slug, telefone, senha)
    if not cadastro:
        st.error(
            "Número ou senha incorretos. Se você ainda não tem cadastro, use a "
            "aba \"Ainda não tenho cadastro\"."
        )
        return

    st.session_state["leitura_cadastro"] = cadastro
    st.rerun()


def _cadastro_leitor(slug):
    st.caption(
        "Crie seu acesso de leitor com um número de WhatsApp e uma senha. "
        "Você usa essas mesmas credenciais para entrar nas próximas vezes."
    )
    with st.form("form_cadastro_leitor"):
        nome = st.text_input("Nome completo")
        telefone = st.text_input("Número de WhatsApp", placeholder="Ex.: (11) 99999-8888")
        c1, c2 = st.columns(2)
        senha = c1.text_input("Senha", type="password")
        confirmar_senha = c2.text_input("Confirmar senha", type="password")
        confirmar = st.form_submit_button("Criar cadastro", type="primary")

    if not confirmar:
        return

    if not nome.strip() or not telefone.strip() or not senha:
        st.error("Informe nome, número de WhatsApp e senha.")
        return
    if senha != confirmar_senha:
        st.error("As senhas informadas não coincidem.")
        return

    try:
        cadastrar_leitor_biblia(slug, nome, telefone, senha)
    except ValueError as erro:
        st.error(str(erro))
        return

    cadastro = autenticar_leitor_biblia(slug, telefone, senha)
    st.session_state["leitura_cadastro"] = cadastro
    st.rerun()


def _identificar_leitor(slug):
    st.markdown("#### Entre ou cadastre-se para confirmar sua leitura")
    modo = st.radio(
        "Como você quer acessar?",
        ["Já tenho login de leitor", "Ainda não tenho cadastro", "Sou membro cadastrado"],
        key="leitura_modo_identificacao",
    )
    if modo == "Já tenho login de leitor":
        _login_leitor(slug)
    elif modo == "Ainda não tenho cadastro":
        _cadastro_leitor(slug)
    else:
        _identificar_membro(slug)


def render_importar_leitores(slug):
    st.markdown("#### Importar leitores em lote")
    st.caption(
        "Cole a lista de participantes do grupo do WhatsApp, um por linha, no "
        "formato \"Nome, Telefone\". Esses leitores não terão CPF cadastrado — "
        "eles confirmam a leitura diária informando o mesmo número de WhatsApp "
        "na tela pública do plano de leitura."
    )
    texto = st.text_area(
        "Nome, Telefone (um por linha)",
        height=160,
        placeholder="Maria Silva, (11) 99999-0000\nJoão Souza, 11 98888-7777",
        key="leitura_importar_texto",
    )
    if not st.button("Importar leitores", type="primary"):
        return

    entradas = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        partes = linha.split(",", 1)
        if len(partes) == 2:
            entradas.append({"nome": partes[0].strip(), "telefone": partes[1].strip()})
        else:
            entradas.append({"nome": linha, "telefone": ""})

    if not entradas:
        st.warning("Cole ao menos uma linha no formato Nome, Telefone.")
        return

    resultado = importar_leitores_biblia_em_lote(slug, entradas)
    if resultado["importados"]:
        st.success(f"{resultado['importados']} leitor(es) importado(s).")
    if resultado["duplicados"]:
        st.info(f"Já cadastrados (ignorados): {', '.join(resultado['duplicados'])}")
    if resultado["invalidos"]:
        st.warning(
            f"Sem nome ou telefone válido (ignorados): {', '.join(resultado['invalidos'])}"
        )


def render_publico():
    st.markdown(_hero_html(listar_planos_leitura_biblica()), unsafe_allow_html=True)

    slug = st.session_state.get("leitura_slug")
    if not slug:
        slug = _selecionar_igreja_publica()
        if not slug:
            return

    cadastro = st.session_state.get("leitura_cadastro")
    if not cadastro:
        _identificar_leitor(slug)
        return

    col_info, col_trocar = st.columns([3, 1])
    with col_info:
        st.success(
            f"Leitor: {cadastro.get('nome', '')} — {cadastro.get('igreja_nome', slug)}"
        )
    with col_trocar:
        if st.button("Trocar igreja/membro"):
            st.session_state.pop("leitura_slug", None)
            st.session_state.pop("leitura_cadastro", None)
            st.rerun()

    planos = listar_planos_leitura_biblica()
    opcoes_planos = {p["nome"]: p["id"] for p in planos}
    nomes_planos = list(opcoes_planos.keys())
    plano_id_atual = st.session_state.get("leitura_plano_id", PLANO_LEITURA_PADRAO)
    nome_atual = next(
        (nome for nome, pid in opcoes_planos.items() if pid == plano_id_atual),
        nomes_planos[0],
    )
    nome_escolhido = st.selectbox(
        "Plano de leitura", nomes_planos, index=nomes_planos.index(nome_atual)
    )
    plano_id = opcoes_planos[nome_escolhido]
    st.session_state["leitura_plano_id"] = plano_id

    data_escolhida = st.date_input(
        "Escolha o dia da leitura", value=datetime.date.today()
    )
    dia_numero = _dia_do_plano(data_escolhida)

    leitura = obter_leitura_do_dia(dia_numero, plano_id=plano_id)
    if not leitura:
        st.info("Leitura ainda não cadastrada para este dia.")
        return

    st.markdown(
        _card_leitura_html(
            dia_numero, data_escolhida, leitura["passagens"], leitura.get("tema", "")
        ),
        unsafe_allow_html=True,
    )
    _render_texto_biblico(leitura["passagens"])

    origem = cadastro.get("origem")
    id_pessoa = cadastro.get("id_pessoa")
    if leitura_ja_confirmada(slug, origem, id_pessoa, dia_numero, plano_id=plano_id):
        st.success("✅ Leitura deste dia já confirmada. Continue firme!")
    else:
        if st.button("Confirmar leitura deste dia", type="primary"):
            confirmar_leitura_biblica(slug, origem, id_pessoa, dia_numero, plano_id=plano_id)
            st.rerun()
