import asyncio
import datetime
import hashlib
import html
import logging
import re
import threading

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

BIBLIA_VOZES = {
    "feminina": "pt-BR-FranciscaNeural",
    "masculina": "pt-BR-AntonioNeural",
}
BIBLIA_VOZ_PADRAO = "feminina"

VELOCIDADES_AUDIO = [1.0, 1.25, 1.5, 1.75, 2.0]
VELOCIDADE_AUDIO_PADRAO = 1.0

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


def _texto_audio_do_dia(passagens_texto, versao=BIBLIA_VERSAO_PADRAO):
    """Texto corrido (sem numeros de versiculo) de toda a leitura do dia,
    pronto para sintese de voz. Anuncia livro/capitulo a cada troca, para
    orientar quem esta ouvindo sem ver a tela."""
    unidades = _parsear_passagens(passagens_texto)
    if not unidades:
        return None
    partes = []
    livro_anterior = None
    for unidade in unidades:
        capitulos = _versos_da_unidade(unidade, versao)
        if capitulos is None:
            return None
        anunciar_capitulo = len(unidades) > 1 or len(capitulos) > 1
        for cap, versos in capitulos:
            if unidade["livro"] != livro_anterior:
                partes.append(f"{unidade['livro']}, capítulo {cap}.")
                livro_anterior = unidade["livro"]
            elif anunciar_capitulo:
                partes.append(f"Capítulo {cap}.")
            partes.extend(v.get("text", "") for v in versos if v.get("text"))
    return " ".join(partes)


def _taxa_edge_tts(velocidade):
    """Converte um multiplicador de velocidade (1.25 = 1.25x) na string de
    taxa percentual que o edge-tts espera (ex.: '+25%')."""
    percentual = round((velocidade - 1) * 100)
    return f"{'+' if percentual >= 0 else ''}{percentual}%"


async def _sintetizar_edge_tts(texto, voz_id, taxa):
    import edge_tts

    comunicador = edge_tts.Communicate(texto, voz_id, rate=taxa)
    partes = []
    async for pedaco in comunicador.stream():
        if pedaco["type"] == "audio":
            partes.append(pedaco["data"])
    return b"".join(partes)


def _audio_do_dia(passagens_texto, versao=BIBLIA_VERSAO_PADRAO,
                   voz=BIBLIA_VOZ_PADRAO, velocidade=VELOCIDADE_AUDIO_PADRAO):
    """Gera (ou recupera do cache) o audio MP3 da leitura completa do dia,
    via edge-tts, na versao, voz e velocidade escolhidas."""
    texto_audio = _texto_audio_do_dia(passagens_texto, versao)
    if not texto_audio:
        return None

    voz_id = BIBLIA_VOZES.get(voz, BIBLIA_VOZES[BIBLIA_VOZ_PADRAO])
    taxa = _taxa_edge_tts(velocidade)
    chave = hashlib.sha256(f"{voz_id}|{taxa}|{texto_audio}".encode()).hexdigest()
    audio_bytes = obter_audio_biblico_cache(versao, chave)
    if audio_bytes is not None:
        return audio_bytes

    try:
        audio_bytes = asyncio.run(_sintetizar_edge_tts(texto_audio, voz_id, taxa))
    except Exception:
        LOGGER.exception("Falha ao gerar audio biblico (versao=%s, voz=%s).", versao, voz)
        return None

    salvar_audio_biblico_cache(versao, chave, audio_bytes)
    return audio_bytes


_PREWARM_LOCK = threading.Lock()
_PREWARM_FEITO = set()


def _pre_gerar_audio_dia(passagens_texto):
    """Gera (em background) o audio de todas as versoes da leitura do dia,
    na voz e velocidade padrao, para que o audio ja esteja em cache quando
    um leitor pedir para ouvir."""
    for versao in BIBLIA_VERSOES:
        try:
            _audio_do_dia(passagens_texto, versao, BIBLIA_VOZ_PADRAO, VELOCIDADE_AUDIO_PADRAO)
        except Exception:
            LOGGER.exception("Falha ao pre-gerar audio do dia (versao=%s).", versao)


def _agendar_prewarm_audio(dia_numero, plano_id, passagens_texto):
    """Dispara a pre-geracao de audio do dia em uma thread separada, uma
    unica vez por (dia, plano) por processo em execucao."""
    chave = (dia_numero, plano_id)
    with _PREWARM_LOCK:
        if chave in _PREWARM_FEITO:
            return
        _PREWARM_FEITO.add(chave)
    threading.Thread(
        target=_pre_gerar_audio_dia, args=(passagens_texto,), daemon=True
    ).start()


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
    col_versao, col_voz, col_vel = st.columns(3)
    with col_versao:
        versao_atual = st.selectbox(
            "Versão da Bíblia",
            list(BIBLIA_VERSOES.keys()),
            index=list(BIBLIA_VERSOES.keys()).index(versao) if versao in BIBLIA_VERSOES else 0,
            format_func=lambda k: BIBLIA_VERSOES[k],
            key="leitura_versao_biblia",
        )
    with col_voz:
        voz_atual = st.selectbox(
            "Voz",
            list(BIBLIA_VOZES.keys()),
            index=list(BIBLIA_VOZES.keys()).index(BIBLIA_VOZ_PADRAO),
            format_func=lambda k: k.capitalize(),
            key="leitura_voz_biblia",
        )
    with col_vel:
        velocidade_atual = st.selectbox(
            "Velocidade",
            VELOCIDADES_AUDIO,
            index=VELOCIDADES_AUDIO.index(VELOCIDADE_AUDIO_PADRAO),
            format_func=lambda v: f"{v}x",
            key="leitura_velocidade_biblia",
        )

    st.markdown("**🔊 Ouvir a leitura do dia**")
    with st.spinner("Preparando áudio..."):
        audio_bytes = _audio_do_dia(passagens_texto, versao_atual, voz_atual, velocidade_atual)
    if audio_bytes:
        st.audio(audio_bytes, format="audio/mp3")
    else:
        st.warning("Não foi possível gerar o áudio agora. Tente novamente em instantes.")

    for unidade in unidades:
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


def _hero_html():
    return _html_sem_indentacao("""
        <div class="leitura-hero">
            <span class="leitura-hero-eyebrow">📖 Plano de leitura</span>
            <h1 class="leitura-hero-title">Leia a Bíblia com a sua igreja</h1>
            <p class="leitura-hero-subtitle">
                Escolha o seu plano, acompanhe o texto (ou ouça) e confirme sua
                leitura de hoje — em poucos passos.
            </p>
        </div>
    """)


def _step_card_html(icone, titulo, descricao=""):
    desc_html = f'<p class="leitura-step-desc">{html.escape(descricao)}</p>' if descricao else ""
    return _html_sem_indentacao(f"""
        <p class="leitura-step-title">{icone} {html.escape(titulo)}</p>
        {desc_html}
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

    with st.container(border=True):
        st.markdown(
            _step_card_html(
                "🏠", "Qual é a sua igreja?",
                "Selecione a igreja ou congregação para carregar o plano certo.",
            ),
            unsafe_allow_html=True,
        )
        with st.form("form_identificar_igreja_leitura"):
            selecionada = st.selectbox("Igreja / congregação", list(opcoes.keys()))
            continuar = st.form_submit_button(
                "Continuar →", type="primary", use_container_width=True
            )
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
        confirmar = st.form_submit_button(
            "Continuar →", type="primary", use_container_width=True
        )

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
        confirmar = st.form_submit_button(
            "Entrar →", type="primary", use_container_width=True
        )

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
        confirmar = st.form_submit_button(
            "Criar cadastro →", type="primary", use_container_width=True
        )

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
    with st.container(border=True):
        st.markdown(
            _step_card_html(
                "🔑", "Entre ou cadastre-se",
                "Precisamos saber quem é você para acompanhar sua leitura diária.",
            ),
            unsafe_allow_html=True,
        )
        modo = st.radio(
            "Como você quer acessar?",
            ["Já tenho login de leitor", "Ainda não tenho cadastro", "Sou membro cadastrado"],
            key="leitura_modo_identificacao",
            horizontal=True,
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


def _leitor_info_html(cadastro, slug):
    nome = str(cadastro.get("nome", "") or "Leitor")
    igreja_nome = str(cadastro.get("igreja_nome", "") or slug)
    inicial = (nome.strip()[:1] or "?").upper()
    return _html_sem_indentacao(f"""
        <div class="leitura-leitor-info">
            <span class="leitura-leitor-avatar">{html.escape(inicial)}</span>
            <div>
                <p class="leitura-leitor-nome">{html.escape(nome)}</p>
                <p class="leitura-leitor-igreja">{html.escape(igreja_nome)}</p>
            </div>
        </div>
    """)


def render_publico():
    with st.container(key="leitura-pagina"):
        st.markdown(_hero_html(), unsafe_allow_html=True)

        slug = st.session_state.get("leitura_slug")
        if not slug:
            slug = _selecionar_igreja_publica()
            if not slug:
                return

        cadastro = st.session_state.get("leitura_cadastro")
        if not cadastro:
            _identificar_leitor(slug)
            return

        with st.container(key="leitura-step-leitor"):
            col_info, col_trocar = st.columns([4, 1])
            with col_info:
                st.markdown(_leitor_info_html(cadastro, slug), unsafe_allow_html=True)
            with col_trocar:
                if st.button("Trocar", use_container_width=True):
                    st.session_state.pop("leitura_slug", None)
                    st.session_state.pop("leitura_cadastro", None)
                    st.rerun()

        with st.container(key="leitura-step-plano"):
            st.markdown(
                _step_card_html("📅", "Plano e dia de leitura"),
                unsafe_allow_html=True,
            )
            planos = listar_planos_leitura_biblica()
            opcoes_planos = {p["nome"]: p["id"] for p in planos}
            nomes_planos = list(opcoes_planos.keys())
            plano_id_atual = st.session_state.get("leitura_plano_id", PLANO_LEITURA_PADRAO)
            nome_atual = next(
                (nome for nome, pid in opcoes_planos.items() if pid == plano_id_atual),
                nomes_planos[0],
            )
            col_plano, col_dia = st.columns(2)
            with col_plano:
                nome_escolhido = st.selectbox(
                    "Plano de leitura", nomes_planos, index=nomes_planos.index(nome_atual)
                )
            with col_dia:
                data_escolhida = st.date_input(
                    "Dia da leitura", value=datetime.date.today()
                )
        plano_id = opcoes_planos[nome_escolhido]
        st.session_state["leitura_plano_id"] = plano_id
        dia_numero = _dia_do_plano(data_escolhida)

        leitura = obter_leitura_do_dia(dia_numero, plano_id=plano_id)
        if not leitura:
            st.info("Leitura ainda não cadastrada para este dia.")
            return

        _agendar_prewarm_audio(dia_numero, plano_id, leitura["passagens"])

        st.markdown(
            _card_leitura_html(
                dia_numero, data_escolhida, leitura["passagens"], leitura.get("tema", "")
            ),
            unsafe_allow_html=True,
        )
        with st.container(key="leitura-step-texto"):
            _render_texto_biblico(leitura["passagens"])

        origem = cadastro.get("origem")
        id_pessoa = cadastro.get("id_pessoa")
        if leitura_ja_confirmada(slug, origem, id_pessoa, dia_numero, plano_id=plano_id):
            st.markdown(
                _html_sem_indentacao("""
                    <div class="leitura-confirmado">
                        ✅ <strong>Leitura de hoje confirmada!</strong>
                        Continue firme na sua jornada.
                    </div>
                """),
                unsafe_allow_html=True,
            )
        else:
            if st.button(
                "✅ Confirmar leitura deste dia", type="primary", use_container_width=True
            ):
                confirmar_leitura_biblica(slug, origem, id_pessoa, dia_numero, plano_id=plano_id)
                st.rerun()
