"""
Monitoramento por Localizacao - controle de presenca via geolocalizacao.

CORRECAO v2:
- streamlit_geolocation() agora e chamada UMA UNICA VEZ no topo do modulo
- Todas as abas consomem o resultado da captura via session_state
- Eliminado o erro "multiple elements with the same key='loc'"

REQUISITOS:
    requirements.txt deve conter:
        streamlit-geolocation>=0.0.10
"""

import datetime
import html
import math
import re
import json
import sqlite3
import urllib.parse
import urllib.request
import urllib.error

import pandas as pd
import streamlit as st

# Tentativa de importar a biblioteca de geolocalizacao
try:
    from streamlit_geolocation import streamlit_geolocation
    GEO_LIB_OK = True
except ImportError:
    GEO_LIB_OK = False
    streamlit_geolocation = None

from data.repository import (
    carregar_cadastros,
    formatar_telefone,
    listar_geo_eventos,
    salvar_geo_evento,
    excluir_geo_evento,
    obter_geo_evento,
    registrar_geo_presenca,
    listar_geo_presencas,
    _tenant_db,
)
from utils.helpers import gerar_csv, slug_da_sessao


# ─── Constantes ────────────────────────────────────────────────────────
TIPOS_SITUACAO = {True: "Presente", False: "Ausente"}
DEFAULT_RAIO_METROS = 30
USER_AGENT = "FielMordomo/1.0 contato@fielmordomo.com.br"
TIMEOUT_HTTP = 12

MENSAGEM_PADRAO_PRESENTES = (
    "Paz do Senhor, {nome}! Sua presenca foi registrada em {evento}, "
    "no dia {data}. Deus abencoe."
)
MENSAGEM_PADRAO_AUSENTES = (
    "Paz do Senhor, {nome}! Sentimos sua falta em {evento}, "
    "no dia {data}. Deus abencoe."
)


# ═══════════════════════════════════════════════════════════════════════
# Migracao e gestao de horario do evento (colunas hora_inicio/hora_fim)
# ═══════════════════════════════════════════════════════════════════════

def _garantir_colunas_horario(slug):
    """
    Garante que as colunas hora_inicio e hora_fim existam na tabela geo_eventos.
    Executa apenas uma vez por sessao para evitar overhead.
    """
    cache_key = f"_geo_horario_migrado_{slug}"
    if st.session_state.get(cache_key):
        return

    try:
        db_path = _tenant_db(slug)
        if not db_path.exists():
            return

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("PRAGMA table_info(geo_eventos)")
            colunas = {row[1] for row in cursor.fetchall()}

            if "hora_inicio" not in colunas:
                conn.execute(
                    "ALTER TABLE geo_eventos ADD COLUMN hora_inicio TEXT DEFAULT ''"
                )
            if "hora_fim" not in colunas:
                conn.execute(
                    "ALTER TABLE geo_eventos ADD COLUMN hora_fim TEXT DEFAULT ''"
                )
            conn.commit()

        st.session_state[cache_key] = True
    except Exception as exc:
        st.warning(f"Aviso: nao consegui migrar tabela geo_eventos: {exc}")


def _ler_horarios_eventos(slug):
    """
    Retorna dict {id_evento: (hora_inicio, hora_fim)} com os horarios
    de todos os eventos do tenant.
    """
    _garantir_colunas_horario(slug)
    try:
        db_path = _tenant_db(slug)
        if not db_path.exists():
            return {}

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT id_evento, hora_inicio, hora_fim FROM geo_eventos"
            )
            return {
                int(row[0]): (str(row[1] or ""), str(row[2] or ""))
                for row in cursor.fetchall()
            }
    except Exception:
        return {}


def _salvar_horario_evento(slug, hora_inicio, hora_fim, id_evento=None, nome=None, data=None):
    """
    Salva hora_inicio e hora_fim para um evento.
    Se id_evento for fornecido, atualiza por ID.
    Caso contrario, atualiza o evento mais recente com aquele (nome, data).
    """
    _garantir_colunas_horario(slug)
    try:
        db_path = _tenant_db(slug)
        if not db_path.exists():
            return

        with sqlite3.connect(db_path) as conn:
            if id_evento:
                conn.execute(
                    "UPDATE geo_eventos SET hora_inicio=?, hora_fim=? WHERE id_evento=?",
                    (str(hora_inicio or ""), str(hora_fim or ""), int(id_evento)),
                )
            elif nome and data:
                conn.execute(
                    """UPDATE geo_eventos
                       SET hora_inicio=?, hora_fim=?
                       WHERE id_evento = (
                           SELECT MAX(id_evento) FROM geo_eventos
                           WHERE nome=? AND data=?
                       )""",
                    (str(hora_inicio or ""), str(hora_fim or ""), str(nome), str(data)),
                )
            conn.commit()
    except Exception as exc:
        st.warning(f"Aviso: nao consegui salvar horario: {exc}")


def _str_to_time(s):
    """Converte 'HH:MM' em datetime.time, ou None se invalido."""
    try:
        partes = str(s or "").strip().split(":")
        if len(partes) >= 2:
            return datetime.time(int(partes[0]), int(partes[1]))
    except Exception:
        pass
    return None


def _time_to_str(t):
    """Converte datetime.time em 'HH:MM', ou string vazia se None."""
    if not t:
        return ""
    try:
        return t.strftime("%H:%M")
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════
# Helpers de telefone e WhatsApp
# ═══════════════════════════════════════════════════════════════════════

def _limpar_tel(tel):
    return "".join(c for c in str(tel if tel is not None else "") if c.isdigit())


def _normalizar_tel_brasil(tel):
    tel_limpo = _limpar_tel(tel)
    if not tel_limpo:
        return ""

    while tel_limpo.startswith("0"):
        tel_limpo = tel_limpo[1:]

    if not tel_limpo.startswith("55"):
        tel_limpo = "55" + tel_limpo

    return tel_limpo


def _link_whatsapp(tel, mensagem):
    tel_limpo = _normalizar_tel_brasil(tel)
    if not tel_limpo:
        return ""
    return f"https://wa.me/{tel_limpo}?text={urllib.parse.quote(mensagem)}"


def _config_whatsapp():
    try:
        cfg = st.secrets.get("whatsapp", {})
    except Exception:
        cfg = {}

    return {
        "access_token": str(cfg.get("access_token", "")).strip(),
        "phone_number_id": str(cfg.get("phone_number_id", "")).strip(),
        "api_version": str(cfg.get("api_version", "v20.0")).strip(),
    }


def _whatsapp_api_configurada():
    cfg = _config_whatsapp()
    return bool(cfg["access_token"] and cfg["phone_number_id"])


def _enviar_whatsapp_texto_api(telefone, mensagem):
    cfg = _config_whatsapp()
    numero = _normalizar_tel_brasil(telefone)
    if not numero:
        return False, "Telefone invalido ou vazio."
    if not _whatsapp_api_configurada():
        return False, "WhatsApp Cloud API nao configurada no st.secrets."

    url = (
        f"https://graph.facebook.com/"
        f"{cfg['api_version']}/{cfg['phone_number_id']}/messages"
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"preview_url": False, "body": mensagem},
    }
    dados = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=dados,
        headers={
            "Authorization": f"Bearer {cfg['access_token']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            status = resp.status
            corpo = resp.read().decode("utf-8", errors="ignore")
            if 200 <= status < 300:
                return True, "Mensagem enviada."
            return False, f"Erro HTTP {status}: {corpo[:200]}"
    except urllib.error.HTTPError as exc:
        try:
            corpo_err = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            corpo_err = ""
        return False, f"Erro HTTP {exc.code}: {corpo_err[:200]}"
    except Exception as exc:
        return False, f"Falha no envio: {exc}"


# ═══════════════════════════════════════════════════════════════════════
# Helpers de geolocalizacao
# ═══════════════════════════════════════════════════════════════════════

def _botao_abrir_google_maps(url, texto="Abrir no Google Maps"):
    if not str(url or "").strip():
        return

    st.markdown(
        (
            f'<a href="{html.escape(str(url), quote=True)}" target="_blank" '
            'style="display:inline-block;background:#0F6E56;color:white;'
            'padding:9px 16px;border-radius:8px;text-decoration:none;'
            'font-size:0.9rem;font-weight:700;margin:4px 0 10px 0">'
            f'{html.escape(str(texto), quote=True)}</a>'
        ),
        unsafe_allow_html=True,
    )


def _extrair_coordenadas_google_maps(texto):
    texto_original = str(texto or "").strip()
    if not texto_original:
        return None

    candidatos = [texto_original]
    try:
        decoded = urllib.parse.unquote(texto_original)
        if decoded != texto_original:
            candidatos.append(decoded)
    except Exception:
        pass

    padroes = [
        r"@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)",
        r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)",
        r"[?&]q=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)",
        r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$",
    ]

    for cand in candidatos:
        for padrao in padroes:
            match = re.search(padrao, cand)
            if not match:
                continue
            try:
                lat = float(match.group(1))
                lon = float(match.group(2))
            except (ValueError, IndexError):
                continue
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon

    return None


def _expandir_link_google_maps(url):
    url = str(url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return ""

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.geturl()
    except Exception:
        return ""


def _obter_coordenadas_de_texto_ou_link(texto):
    coords = _extrair_coordenadas_google_maps(texto)
    if coords:
        return coords, ""

    link_expandido = _expandir_link_google_maps(texto)
    if link_expandido:
        coords = _extrair_coordenadas_google_maps(link_expandido)
        if coords:
            return coords, link_expandido

    return None, link_expandido


def _buscar_coordenadas_por_endereco(endereco):
    endereco = str(endereco or "").strip()
    if not endereco:
        return None

    url = (
        "https://nominatim.openstreetmap.org/search?"
        + urllib.parse.urlencode({
            "q": endereco,
            "format": "json",
            "limit": "1",
            "addressdetails": "1",
        })
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT_HTTP) as resp:
            dados = json.loads(resp.read().decode("utf-8"))

        if not dados:
            return None

        item = dados[0]
        lat_str = item.get("lat")
        lon_str = item.get("lon")
        if lat_str is None or lon_str is None:
            return None

        display = str(item.get("display_name", endereco))
        return float(lat_str), float(lon_str), display
    except Exception:
        return None


def _buscar_endereco_por_coordenadas(latitude, longitude):
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return ""

    if lat == 0 and lon == 0:
        return ""

    url = (
        "https://nominatim.openstreetmap.org/reverse?"
        + urllib.parse.urlencode({
            "lat": f"{lat:.8f}",
            "lon": f"{lon:.8f}",
            "format": "json",
            "zoom": "18",
            "addressdetails": "1",
        })
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT_HTTP) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
        return str(dados.get("display_name", "") or "")
    except Exception:
        return ""


def _distancia_metros(lat1, lon1, lat2, lon2):
    try:
        raio_terra = 6371000
        lat1_rad = math.radians(float(lat1))
        lat2_rad = math.radians(float(lat2))
        delta_lat = math.radians(float(lat2) - float(lat1))
        delta_lon = math.radians(float(lon2) - float(lon1))

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return raio_terra * c
    except (TypeError, ValueError):
        return float("inf")


# ═══════════════════════════════════════════════════════════════════════
# CAPTURA UNICA DE LOCALIZACAO (compartilhada entre abas)
# ═══════════════════════════════════════════════════════════════════════

def _captura_unica_topo():
    """
    Chama streamlit_geolocation() UMA UNICA VEZ no topo do modulo.
    Resultado fica em st.session_state['geo_cap_lat']/['geo_cap_lon'].
    """
    if not GEO_LIB_OK:
        return

    col_geo, col_info = st.columns([1, 4])

    with col_geo:
        try:
            loc = streamlit_geolocation()
        except Exception as exc:
            st.error(f"Erro: {exc}")
            loc = None

    with col_info:
        cap_lat = st.session_state.get("geo_cap_lat")
        cap_lon = st.session_state.get("geo_cap_lon")
        cap_ts = st.session_state.get("geo_cap_ts")

        if cap_lat is not None and cap_lon is not None:
            ts_txt = ""
            if cap_ts:
                ts_txt = f" (em {cap_ts.strftime('%H:%M:%S')})"
            st.success(
                f"📍 **Localizacao ativa:** `{cap_lat:.6f}, {cap_lon:.6f}`{ts_txt}\n\n"
                "Use o botao **Aplicar** em qualquer aba para usar estas coordenadas."
            )
        else:
            st.info(
                "👆 **Clique no icone GPS** ao lado para capturar sua localizacao. "
                "Ela ficara disponivel em todas as abas."
            )

    if loc:
        lat_novo = loc.get("latitude")
        lon_novo = loc.get("longitude")

        if lat_novo is not None and lon_novo is not None:
            try:
                lat_novo = float(lat_novo)
                lon_novo = float(lon_novo)

                cap_lat_atual = st.session_state.get("geo_cap_lat")
                cap_lon_atual = st.session_state.get("geo_cap_lon")

                mudou = (
                    cap_lat_atual is None
                    or cap_lon_atual is None
                    or abs(cap_lat_atual - lat_novo) > 1e-7
                    or abs(cap_lon_atual - lon_novo) > 1e-7
                )

                if mudou:
                    st.session_state["geo_cap_lat"] = lat_novo
                    st.session_state["geo_cap_lon"] = lon_novo
                    st.session_state["geo_cap_ts"] = datetime.datetime.now()
                    st.rerun()
            except (TypeError, ValueError):
                pass


def _ler_localizacao_capturada():
    """Retorna (lat, lon) se ha captura, ou None."""
    lat = st.session_state.get("geo_cap_lat")
    lon = st.session_state.get("geo_cap_lon")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


# ═══════════════════════════════════════════════════════════════════════
# Helpers de query params (para link de check-in via WhatsApp)
# ═══════════════════════════════════════════════════════════════════════

def _valor_query(chave, padrao=""):
    valor = st.query_params.get(chave, padrao)
    if isinstance(valor, list):
        return valor[0] if valor else padrao
    return valor


def _limpar_query_geo():
    for chave in ["geo_id_evento", "geo_id_cadastro"]:
        if chave in st.query_params:
            del st.query_params[chave]


# ═══════════════════════════════════════════════════════════════════════
# Helpers de dados
# ═══════════════════════════════════════════════════════════════════════

def _membros_ativos(slug):
    df = carregar_cadastros(slug)
    if df.empty:
        return pd.DataFrame(columns=["id_cadastro", "nome", "telefone"])

    for col in ["tipo_cadastro", "situacao", "nome", "telefone"]:
        if col not in df.columns:
            df[col] = ""

    membros = df[
        (df["tipo_cadastro"].fillna("").astype(str).str.upper() == "MEMBRO")
        & (df["situacao"].fillna("").astype(str).str.upper() == "ATIVO")
    ].copy()

    if membros.empty:
        return pd.DataFrame(columns=["id_cadastro", "nome", "telefone"])

    membros["telefone"] = membros["telefone"].apply(formatar_telefone)
    return membros[["id_cadastro", "nome", "telefone"]].sort_values("nome")


def _rotulo_evento(row, horarios=None):
    data_fmt = pd.to_datetime(row.get("data"), errors="coerce")
    data_txt = data_fmt.strftime("%d/%m/%Y") if pd.notna(data_fmt) else str(row.get("data", ""))

    # Adiciona hora de inicio ao rotulo se disponivel
    hora_txt = ""
    if horarios:
        try:
            id_evt = int(row["id_evento"])
            hora_ini, _ = horarios.get(id_evt, ("", ""))
            if hora_ini:
                hora_txt = f" {hora_ini}"
        except (TypeError, ValueError):
            pass

    status = "habilitado" if int(row.get("captura_habilitada", 0) or 0) else "desabilitado"
    ativo = "" if int(row.get("ativo", 1) or 1) else " - INATIVO"
    return f'{int(row["id_evento"])} - {data_txt}{hora_txt} - {row["nome"]} ({status}){ativo}'


def _rotulo_membro(row):
    tel = row.get("telefone", "")
    return f'{int(row["id_cadastro"])} - {row["nome"]}' + (f" - {tel}" if tel else "")


def _montar_tabela_frequencia(slug, id_evento):
    membros = _membros_ativos(slug)
    presencas = listar_geo_presencas(slug, id_evento)

    if membros.empty:
        return pd.DataFrame()

    if presencas.empty:
        membros["presente"] = False
        membros["distancia_m"] = pd.NA
        membros["status"] = "Sem registro"
        membros["registrado_em"] = ""
        membros["situacao"] = "Ausente"
        return membros

    presencas = presencas[[
        "id_cadastro", "presente", "distancia_m", "status", "registrado_em"
    ]].copy()
    presencas["id_cadastro"] = pd.to_numeric(presencas["id_cadastro"], errors="coerce")
    membros["id_cadastro"] = pd.to_numeric(membros["id_cadastro"], errors="coerce")

    tabela = membros.merge(presencas, on="id_cadastro", how="left")
    tabela["presente"] = tabela["presente"].fillna(0).astype(int).astype(bool)
    tabela["status"] = tabela["status"].fillna("Sem registro")
    tabela["registrado_em"] = tabela["registrado_em"].fillna("")
    tabela["situacao"] = tabela["presente"].map(TIPOS_SITUACAO)
    return tabela


def _mensagem_padrao(evento, grupo):
    if grupo == "Presentes":
        msg = str(evento.get("mensagem_presentes") or "").strip()
        return msg if msg else MENSAGEM_PADRAO_PRESENTES
    msg = str(evento.get("mensagem_ausentes") or "").strip()
    return msg if msg else MENSAGEM_PADRAO_AUSENTES


def _calcular_resultado_presenca(evento, lat, lon):
    dist = _distancia_metros(evento["latitude"], evento["longitude"], lat, lon)
    raio = float(evento.get("raio_metros", DEFAULT_RAIO_METROS) or DEFAULT_RAIO_METROS)
    dentro = dist <= raio
    habilitado = bool(int(evento.get("captura_habilitada", 0) or 0))
    ativo = bool(int(evento.get("ativo", 1) or 1))
    presente = dentro and habilitado and ativo

    if not ativo:
        status = "Evento inativo"
    elif not habilitado:
        status = "Captura desabilitada"
    elif dentro:
        status = "Presente por localizacao"
    else:
        status = "Fora do raio configurado"

    return dist, dentro, presente, status


# ═══════════════════════════════════════════════════════════════════════
# Aba 1: Eventos
# ═══════════════════════════════════════════════════════════════════════

def _init_estado_evento(evento_atual, horarios=None):
    evento_id = str(evento_atual.get("id_evento", "novo"))

    if st.session_state.get("evt_ref") != evento_id:
        st.session_state["evt_ref"] = evento_id
        st.session_state["evt_lat"] = float(evento_atual.get("latitude", 0) or 0)
        st.session_state["evt_lon"] = float(evento_atual.get("longitude", 0) or 0)
        st.session_state["evt_end"] = str(evento_atual.get("endereco", "") or "")

        # Horarios: busca do dict horarios se disponivel
        hora_ini_str, hora_fim_str = "", ""
        if horarios and evento_atual.get("id_evento"):
            try:
                hora_ini_str, hora_fim_str = horarios.get(
                    int(evento_atual["id_evento"]), ("", "")
                )
            except (TypeError, ValueError):
                pass

        st.session_state["evt_hora_ini"] = hora_ini_str
        st.session_state["evt_hora_fim"] = hora_fim_str

        st.session_state["evt_ver"] = st.session_state.get("evt_ver", 0) + 1


def _render_eventos(slug):
    st.subheader("📅 Evento e local de referencia")
    st.caption(
        "Cadastre o culto/reuniao, defina o ponto central e habilite a captura "
        "de localizacao quando for o momento."
    )

    # Garante que as colunas de horario existem e carrega os horarios
    _garantir_colunas_horario(slug)
    horarios = _ler_horarios_eventos(slug)

    eventos = listar_geo_eventos(slug, incluir_inativos=True)

    opcoes = ["➕ Novo evento"]
    mapa_eventos = {}
    if not eventos.empty:
        for _, row in eventos.iterrows():
            rotulo = _rotulo_evento(row, horarios)
            opcoes.append(rotulo)
            mapa_eventos[rotulo] = row.to_dict()

    escolhido = st.selectbox("Evento", opcoes, key="evt_sel")
    evento_atual = mapa_eventos.get(escolhido, {})

    _init_estado_evento(evento_atual, horarios)
    ver = st.session_state["evt_ver"]

    # ─── Botao APLICAR localizacao capturada ────────────────────────
    st.markdown("#### 📍 Localizacao do evento")

    coord_global = _ler_localizacao_capturada()

    if coord_global:
        cap_lat, cap_lon = coord_global
        col_apl1, col_apl2 = st.columns([3, 1])
        with col_apl1:
            st.info(
                f"📌 **Localizacao capturada:** `{cap_lat:.6f}, {cap_lon:.6f}`"
            )
        with col_apl2:
            if st.button(
                "✅ Usar no evento",
                use_container_width=True,
                key=f"aplicar_evt_v{ver}",
                type="primary",
            ):
                st.session_state["evt_lat"] = cap_lat
                st.session_state["evt_lon"] = cap_lon
                endereco_capt = _buscar_endereco_por_coordenadas(cap_lat, cap_lon)
                if endereco_capt:
                    st.session_state["evt_end"] = endereco_capt
                st.session_state["evt_ver"] += 1
                st.success("✅ Localizacao aplicada ao evento!")
                st.rerun()
    else:
        st.caption(
            "💡 **Dica:** capture sua localizacao no botao GPS no topo da pagina "
            "para usar como ponto do evento."
        )

    # ─── Endereco ───────────────────────────────────────────────────
    col_end_1, col_end_2 = st.columns([3, 1])
    with col_end_1:
        endereco_input = st.text_input(
            "Endereco do evento",
            value=st.session_state["evt_end"],
            key=f"evt_end_v{ver}",
            placeholder="Ex.: Assembleia de Deus Central, Minacu GO",
        )
    with col_end_2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        buscar_endereco = st.button(
            "🔍 Buscar coords",
            use_container_width=True,
            key=f"btn_buscar_end_v{ver}",
        )

    if endereco_input != st.session_state["evt_end"]:
        st.session_state["evt_end"] = endereco_input

    if buscar_endereco:
        if not endereco_input.strip():
            st.warning("Informe um endereco para buscar.")
        else:
            with st.spinner("Buscando coordenadas..."):
                resultado = _buscar_coordenadas_por_endereco(endereco_input)
            if resultado:
                lat_b, lon_b, end_b = resultado
                st.session_state["evt_lat"] = lat_b
                st.session_state["evt_lon"] = lon_b
                st.session_state["evt_end"] = end_b
                st.session_state["evt_ver"] += 1
                st.success("✅ Coordenadas encontradas!")
                st.rerun()
            else:
                st.error("❌ Nao encontrei coordenadas. Complemente com cidade e estado.")

    # ─── Google Maps ────────────────────────────────────────────────
    with st.expander("🗺️ Buscar no Google Maps ou colar link/coordenadas"):
        busca_maps = st.text_input(
            "Buscar local no Google Maps",
            key=f"busca_maps_v{ver}",
            placeholder="Nome do local, igreja ou endereco",
        )
        if busca_maps.strip():
            if busca_maps.strip().lower().startswith(("http://", "https://")):
                _botao_abrir_google_maps(busca_maps.strip(), "Abrir link no Maps")
            else:
                link_busca = (
                    "https://www.google.com/maps/search/?api=1&query="
                    + urllib.parse.quote_plus(busca_maps.strip())
                )
                _botao_abrir_google_maps(link_busca, "Abrir busca no Maps")

        col_m_1, col_m_2 = st.columns([3, 1])
        with col_m_1:
            texto_maps = st.text_input(
                "Cole o link ou as coordenadas",
                key=f"link_maps_v{ver}",
                placeholder="-13.533,-48.220 ou link completo",
            )
        with col_m_2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            usar_maps = st.button(
                "Usar",
                use_container_width=True,
                key=f"btn_usar_maps_v{ver}",
            )

        if usar_maps:
            if not texto_maps.strip():
                st.warning("Cole um link ou coordenadas.")
            else:
                coords, link_exp = _obter_coordenadas_de_texto_ou_link(texto_maps)
                if coords:
                    lat_m, lon_m = coords
                    st.session_state["evt_lat"] = lat_m
                    st.session_state["evt_lon"] = lon_m
                    end_m = _buscar_endereco_por_coordenadas(lat_m, lon_m)
                    if end_m:
                        st.session_state["evt_end"] = end_m
                    st.session_state["evt_ver"] += 1
                    st.success("✅ Coordenadas carregadas!")
                    st.rerun()
                else:
                    st.error(
                        "❌ Use o formato `lat,lon` (ex: -13.5,-48.2) "
                        "ou um link completo do Google Maps."
                    )
                    if link_exp:
                        st.caption(f"Link analisado: {link_exp}")

    # ─── Form principal ─────────────────────────────────────────────
    data_default = pd.to_datetime(evento_atual.get("data"), errors="coerce")
    if pd.isna(data_default):
        data_default = pd.Timestamp(datetime.date.today())

    with st.form(f"form_evt_v{ver}"):
        c1, c2 = st.columns([2, 1])
        with c1:
            nome = st.text_input(
                "Nome do evento",
                value=str(evento_atual.get("nome", "Culto") or "Culto"),
            )
        with c2:
            data_evt = st.date_input(
                "Data",
                value=data_default.date(),
                format="DD/MM/YYYY",
            )

        # Horarios de inicio e fim
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            hora_ini_default = _str_to_time(st.session_state.get("evt_hora_ini")) or datetime.time(19, 30)
            hora_inicio_form = st.time_input(
                "🕐 Hora de inicio",
                value=hora_ini_default,
                step=datetime.timedelta(minutes=15),
                help="Horario em que o evento comeca.",
            )
        with col_h2:
            hora_fim_default = _str_to_time(st.session_state.get("evt_hora_fim")) or datetime.time(21, 0)
            hora_fim_form = st.time_input(
                "🕐 Hora de fim",
                value=hora_fim_default,
                step=datetime.timedelta(minutes=15),
                help="Horario previsto de termino.",
            )

        c3, c4, c5 = st.columns(3)
        with c3:
            latitude = st.number_input(
                "Latitude",
                value=float(st.session_state["evt_lat"]),
                format="%.8f",
            )
        with c4:
            longitude = st.number_input(
                "Longitude",
                value=float(st.session_state["evt_lon"]),
                format="%.8f",
            )
        with c5:
            raio = st.number_input(
                "Raio (m)",
                min_value=5,
                max_value=1000,
                value=int(evento_atual.get("raio_metros", DEFAULT_RAIO_METROS) or DEFAULT_RAIO_METROS),
                step=5,
            )

        c6, c7 = st.columns(2)
        with c6:
            captura = st.checkbox(
                "Habilitar captura de localizacao",
                value=bool(int(evento_atual.get("captura_habilitada", 0) or 0)),
            )
        with c7:
            ativo = st.checkbox(
                "Evento ativo",
                value=bool(int(evento_atual.get("ativo", 1) or 1)),
            )

        mensagem_p = st.text_area(
            "Mensagem padrao para presentes",
            value=str(evento_atual.get("mensagem_presentes", "") or ""),
            height=80,
            help="Use {nome}, {evento}, {data}.",
        )
        mensagem_a = st.text_area(
            "Mensagem padrao para ausentes",
            value=str(evento_atual.get("mensagem_ausentes", "") or ""),
            height=80,
            help="Use {nome}, {evento}, {data}.",
        )
        observacoes = st.text_area(
            "Observacoes",
            value=str(evento_atual.get("observacoes", "") or ""),
            height=60,
        )

        if latitude == 0.0 and longitude == 0.0:
            st.warning("⚠️ Latitude/longitude em 0,0. Capture ou informe coordenadas validas.")

        salvar = st.form_submit_button("💾 Salvar evento", type="primary")

    if salvar:
        if not nome.strip():
            st.error("❌ Informe o nome do evento.")
        elif latitude == 0.0 and longitude == 0.0:
            st.error("❌ Informe coordenadas validas.")
        elif hora_inicio_form and hora_fim_form and hora_fim_form <= hora_inicio_form:
            st.error("❌ A hora de fim deve ser maior que a hora de inicio.")
        else:
            try:
                id_existente = evento_atual.get("id_evento")

                salvar_geo_evento(
                    slug=slug,
                    id_evento=id_existente,
                    nome=nome,
                    data=data_evt.isoformat(),
                    endereco=st.session_state["evt_end"],
                    latitude=latitude,
                    longitude=longitude,
                    raio_metros=raio,
                    captura_habilitada=captura,
                    ativo=ativo,
                    mensagem_presentes=mensagem_p,
                    mensagem_ausentes=mensagem_a,
                    observacoes=observacoes,
                )

                # Salva os horarios separadamente (colunas adicionadas via migracao)
                hora_ini_str = _time_to_str(hora_inicio_form)
                hora_fim_str = _time_to_str(hora_fim_form)

                if id_existente:
                    _salvar_horario_evento(
                        slug, hora_ini_str, hora_fim_str, id_evento=id_existente
                    )
                else:
                    _salvar_horario_evento(
                        slug, hora_ini_str, hora_fim_str,
                        nome=nome, data=data_evt.isoformat(),
                    )

                st.success("✅ Evento salvo!")
                st.session_state.pop("evt_ref", None)
                st.rerun()
            except Exception as exc:
                st.error(f"❌ Erro ao salvar: {exc}")

    # ─── Acoes ──────────────────────────────────────────────────────
    if evento_atual.get("id_evento"):
        st.markdown("#### ⚙️ Cancelar ou excluir")
        st.caption("**Cancelar:** mantem historico. **Excluir:** remove permanentemente.")

        ac1, ac2 = st.columns(2)
        with ac1:
            if st.button(
                "⏸️ Cancelar/desativar",
                use_container_width=True,
                key=f"btn_cancelar_{int(evento_atual['id_evento'])}",
            ):
                try:
                    salvar_geo_evento(
                        slug=slug,
                        id_evento=evento_atual["id_evento"],
                        nome=evento_atual.get("nome", ""),
                        data=evento_atual.get("data", ""),
                        endereco=evento_atual.get("endereco", ""),
                        latitude=evento_atual.get("latitude", 0),
                        longitude=evento_atual.get("longitude", 0),
                        raio_metros=evento_atual.get("raio_metros", DEFAULT_RAIO_METROS),
                        captura_habilitada=False,
                        ativo=False,
                        mensagem_presentes=evento_atual.get("mensagem_presentes", ""),
                        mensagem_ausentes=evento_atual.get("mensagem_ausentes", ""),
                        observacoes=(
                            str(evento_atual.get("observacoes", "") or "")
                            + "\nEvento cancelado/desativado."
                        ).strip(),
                    )
                    st.success("✅ Desativado.")
                    st.session_state.pop("evt_ref", None)
                    st.rerun()
                except Exception as exc:
                    st.error(f"❌ Erro: {exc}")

        with ac2:
            confirmar = st.checkbox(
                "Confirmo exclusao definitiva",
                key=f"conf_excluir_{int(evento_atual['id_evento'])}",
            )
            if st.button(
                "🗑️ Excluir definitivamente",
                use_container_width=True,
                disabled=not confirmar,
                key=f"btn_excluir_{int(evento_atual['id_evento'])}",
            ):
                try:
                    excluir_geo_evento(slug, evento_atual["id_evento"])
                    st.success("✅ Excluido.")
                    st.session_state.pop("evt_ref", None)
                    st.rerun()
                except Exception as exc:
                    st.error(f"❌ Erro: {exc}")

    # ─── Tabela ─────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 📋 Eventos cadastrados")

    if eventos.empty:
        st.info("Nenhum evento cadastrado ainda.")
    else:
        df_view = eventos.copy()
        df_view["data"] = pd.to_datetime(df_view["data"], errors="coerce").dt.strftime("%d/%m/%Y")
        df_view["captura_habilitada"] = df_view["captura_habilitada"].map({1: "Sim", 0: "Nao"})
        df_view["ativo"] = df_view["ativo"].map({1: "Sim", 0: "Nao"})

        # Adiciona coluna de horario combinando hora_inicio e hora_fim
        def _formatar_horario(id_evt):
            try:
                ini, fim = horarios.get(int(id_evt), ("", ""))
                if ini and fim:
                    return f"{ini} - {fim}"
                return ini or fim or "-"
            except (TypeError, ValueError):
                return "-"

        df_view["horario"] = df_view["id_evento"].apply(_formatar_horario)

        st.dataframe(
            df_view[[
                "id_evento", "data", "horario", "nome", "endereco",
                "latitude", "longitude", "raio_metros",
                "captura_habilitada", "ativo",
            ]].rename(columns={
                "id_evento": "ID",
                "data": "Data",
                "horario": "Horario",
                "nome": "Evento",
                "endereco": "Endereco",
                "latitude": "Lat",
                "longitude": "Lon",
                "raio_metros": "Raio (m)",
                "captura_habilitada": "Captura",
                "ativo": "Ativo",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ═══════════════════════════════════════════════════════════════════════
# Helpers comuns
# ═══════════════════════════════════════════════════════════════════════

def _selecionar_evento(slug, apenas_ativos=False, apenas_habilitados=False, key="sel_evt"):
    eventos = listar_geo_eventos(slug, incluir_inativos=not apenas_ativos)
    if eventos.empty:
        st.info("📭 Cadastre um evento primeiro na aba **Eventos**.")
        return None

    if apenas_ativos:
        eventos = eventos[eventos["ativo"].astype(int) == 1]
    if apenas_habilitados:
        eventos = eventos[eventos["captura_habilitada"].astype(int) == 1]

    if eventos.empty:
        st.warning("⚠️ Nenhum evento disponivel.")
        return None

    # Le horarios para enriquecer os rotulos
    horarios = _ler_horarios_eventos(slug)

    mapa = {}
    opcoes = []
    for _, row in eventos.iterrows():
        rotulo = _rotulo_evento(row, horarios)
        mapa[rotulo] = row.to_dict()
        opcoes.append(rotulo)

    escolhido = st.selectbox("Evento", opcoes, key=key)
    return mapa[escolhido]


# ═══════════════════════════════════════════════════════════════════════
# Aba 2: Check-in
# ═══════════════════════════════════════════════════════════════════════

def _render_checkin(slug):
    st.subheader("📲 Check-in por localizacao")
    st.caption(
        "📌 Capture sua localizacao no botao GPS no **topo da pagina**. "
        "A captura fica compartilhada entre todas as abas."
    )

    id_evt_url = _valor_query("geo_id_evento")
    id_cad_url = _valor_query("geo_id_cadastro")

    evento = _selecionar_evento(
        slug,
        apenas_ativos=True,
        apenas_habilitados=False,
        key="evt_checkin",
    )
    if not evento:
        return

    if not bool(int(evento.get("captura_habilitada", 0) or 0)):
        st.warning("⚠️ A captura esta **desabilitada** para este evento.")

    membros = _membros_ativos(slug)
    if membros.empty:
        st.info("Nenhum membro ativo encontrado.")
        return

    coord_global = _ler_localizacao_capturada()

    tab_ind, tab_massa = st.tabs(["👤 Individual", "👥 Em massa"])

    # ─── INDIVIDUAL ─────────────────────────────────────────────────
    with tab_ind:
        st.caption("Selecione um membro e use a localizacao capturada no topo.")

        mapa_membros = {_rotulo_membro(row): row.to_dict() for _, row in membros.iterrows()}
        opcoes_membros = list(mapa_membros.keys())

        index_pre = 0
        if id_cad_url:
            for i, rot in enumerate(opcoes_membros):
                try:
                    if str(mapa_membros[rot]["id_cadastro"]) == str(int(id_cad_url)):
                        index_pre = i
                        break
                except (ValueError, KeyError):
                    pass

        membro_label = st.selectbox(
            "Membro",
            opcoes_membros,
            index=index_pre,
            key="checkin_membro",
        )
        membro = mapa_membros[membro_label]
        st.caption(f"📞 Telefone: {membro.get('telefone') or 'sem telefone'}")

        if not coord_global:
            st.warning(
                "📍 **Nenhuma localizacao capturada ainda.** "
                "Use o botao GPS no **topo da pagina** para capturar sua localizacao."
            )
        else:
            lat_c, lon_c = coord_global
            dist, dentro, presente_calc, status_calc = _calcular_resultado_presenca(
                evento, lat_c, lon_c
            )

            c_dist, c_status = st.columns(2)
            c_dist.metric("Distancia ate o evento", f"{dist:.0f} m")
            if dentro:
                c_status.success(f"✅ Dentro do raio ({int(evento.get('raio_metros', DEFAULT_RAIO_METROS))} m)")
            else:
                c_status.warning(f"⚠️ Fora do raio ({int(evento.get('raio_metros', DEFAULT_RAIO_METROS))} m)")

            st.caption(f"Status: {status_calc}")

            if st.button(
                "✅ Registrar minha presenca",
                type="primary",
                use_container_width=True,
                key=f"btn_reg_ind_{evento['id_evento']}_{membro['id_cadastro']}",
            ):
                try:
                    registrar_geo_presenca(
                        slug=slug,
                        id_evento=evento["id_evento"],
                        id_cadastro=membro["id_cadastro"],
                        latitude=lat_c,
                        longitude=lon_c,
                        distancia_m=dist,
                        dentro_raio=dentro,
                        presente=presente_calc,
                        status=status_calc,
                    )
                    if presente_calc:
                        st.success(f"✅ Presenca registrada para {membro['nome']}!")
                    else:
                        st.warning(f"⚠️ Registrado como ausente. Motivo: {status_calc}")

                    if id_evt_url or id_cad_url:
                        _limpar_query_geo()
                except Exception as exc:
                    st.error(f"❌ Erro ao registrar: {exc}")

        with st.expander("🛠️ Registrar localizacao manualmente"):
            st.caption("Use somente se a captura automatica nao funcionar.")
            cm1, cm2 = st.columns(2)
            lat_m = cm1.number_input("Latitude", value=0.0, format="%.8f", key="manual_lat")
            lon_m = cm2.number_input("Longitude", value=0.0, format="%.8f", key="manual_lon")

            if st.button(
                "Registrar manualmente",
                key=f"btn_reg_manual_{evento['id_evento']}_{membro['id_cadastro']}",
            ):
                if lat_m == 0 and lon_m == 0:
                    st.error("Informe coordenadas validas.")
                else:
                    dist_m, dentro_m, presente_m, status_m = _calcular_resultado_presenca(
                        evento, lat_m, lon_m
                    )
                    try:
                        registrar_geo_presenca(
                            slug=slug,
                            id_evento=evento["id_evento"],
                            id_cadastro=membro["id_cadastro"],
                            latitude=lat_m,
                            longitude=lon_m,
                            distancia_m=dist_m,
                            dentro_raio=dentro_m,
                            presente=presente_m,
                            status=status_m,
                        )
                        st.success("Registro salvo.")
                    except Exception as exc:
                        st.error(f"Erro: {exc}")

    # ─── EM MASSA ───────────────────────────────────────────────────
    with tab_massa:
        st.caption(
            "Use quando a lideranca esta no local. Use a localizacao capturada no topo "
            "e selecione todos os membros presentes."
        )

        if not coord_global:
            st.warning(
                "📍 **Nenhuma localizacao capturada.** "
                "Use o botao GPS no **topo da pagina**."
            )
            return

        lat_massa, lon_massa = coord_global
        dist_massa, dentro_massa, _, _ = _calcular_resultado_presenca(
            evento, lat_massa, lon_massa
        )

        col_d1, col_d2, col_d3 = st.columns(3)
        col_d1.metric("Latitude", f"{lat_massa:.6f}")
        col_d2.metric("Longitude", f"{lon_massa:.6f}")
        col_d3.metric("Distancia", f"{dist_massa:.0f} m")

        if dentro_massa:
            st.success("✅ Voce esta dentro do raio do evento.")
        else:
            st.warning(
                f"⚠️ Voce esta fora do raio ({int(evento.get('raio_metros', DEFAULT_RAIO_METROS))} m). "
                "Registros serao marcados como ausentes."
            )

        st.markdown("##### Selecione os membros presentes:")

        mapa_membros_massa = {_rotulo_membro(row): row.to_dict() for _, row in membros.iterrows()}
        opcoes_massa = list(mapa_membros_massa.keys())

        sel_key = f"sel_massa_{evento['id_evento']}"
        if sel_key not in st.session_state:
            st.session_state[sel_key] = []

        b1, b2 = st.columns(2)
        with b1:
            if st.button(
                "✓ Selecionar todos",
                use_container_width=True,
                key=f"btn_all_{evento['id_evento']}",
            ):
                st.session_state[sel_key] = opcoes_massa.copy()
                st.rerun()
        with b2:
            if st.button(
                "✗ Limpar selecao",
                use_container_width=True,
                key=f"btn_clear_{evento['id_evento']}",
            ):
                st.session_state[sel_key] = []
                st.rerun()

        selecionados = st.multiselect(
            "Membros presentes no local",
            opcoes_massa,
            default=st.session_state[sel_key],
            key=f"ms_{evento['id_evento']}",
        )
        st.session_state[sel_key] = selecionados

        confirmar_massa = st.checkbox(
            f"Confirmo o registro de {len(selecionados)} membro(s)",
            key=f"conf_massa_{evento['id_evento']}",
        )

        if st.button(
            "💾 Registrar check-in em massa",
            type="primary",
            use_container_width=True,
            disabled=not confirmar_massa or not selecionados,
            key=f"btn_reg_massa_{evento['id_evento']}",
        ):
            habilitado = bool(int(evento.get("captura_habilitada", 0) or 0))
            ativo = bool(int(evento.get("ativo", 1) or 1))
            presente = bool(dentro_massa and habilitado and ativo)

            if not ativo:
                status = "Evento inativo"
            elif not habilitado:
                status = "Captura desabilitada"
            elif dentro_massa:
                status = "Presente por check-in em massa"
            else:
                status = "Check-in em massa fora do raio"

            registrados = 0
            erros = []
            with st.spinner(f"Registrando {len(selecionados)} membro(s)..."):
                for rotulo in selecionados:
                    membro_m = mapa_membros_massa.get(rotulo)
                    if not membro_m:
                        continue
                    try:
                        registrar_geo_presenca(
                            slug=slug,
                            id_evento=evento["id_evento"],
                            id_cadastro=membro_m["id_cadastro"],
                            latitude=lat_massa,
                            longitude=lon_massa,
                            distancia_m=dist_massa,
                            dentro_raio=dentro_massa,
                            presente=presente,
                            status=status,
                        )
                        registrados += 1
                    except Exception as exc:
                        erros.append(f"{membro_m.get('nome', rotulo)}: {exc}")

            if registrados:
                st.success(f"✅ {registrados} check-in(s) registrados.")
                st.session_state[sel_key] = []
            if erros:
                st.error(f"⚠️ {len(erros)} erro(s):")
                for e in erros[:5]:
                    st.caption(f"- {e}")


# ═══════════════════════════════════════════════════════════════════════
# Aba 3: Frequencia
# ═══════════════════════════════════════════════════════════════════════

def _render_frequencia(slug):
    st.subheader("📊 Presentes e ausentes")
    evento = _selecionar_evento(slug, apenas_ativos=False, key="evt_freq")
    if not evento:
        return

    tabela = _montar_tabela_frequencia(slug, evento["id_evento"])
    if tabela.empty:
        st.info("Nenhum membro ativo encontrado.")
        return

    qtd_presentes = int(tabela["presente"].sum())
    qtd_total = len(tabela)
    qtd_ausentes = qtd_total - qtd_presentes
    pct = (qtd_presentes / qtd_total * 100) if qtd_total > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Membros ativos", qtd_total)
    c2.metric("Presentes", qtd_presentes)
    c3.metric("Ausentes", qtd_ausentes)
    c4.metric("Presenca %", f"{pct:.1f}%")

    filtro = st.radio(
        "Filtro",
        ["Todos", "Presentes", "Ausentes"],
        horizontal=True,
        key="filtro_freq",
    )

    view = tabela.copy()
    if filtro == "Presentes":
        view = view[view["presente"]]
    elif filtro == "Ausentes":
        view = view[~view["presente"]]

    view["distancia_m"] = pd.to_numeric(view["distancia_m"], errors="coerce").round(0)
    view = view.rename(columns={
        "nome": "Nome",
        "telefone": "Telefone",
        "situacao": "Situacao",
        "distancia_m": "Distancia (m)",
        "status": "Status",
        "registrado_em": "Registrado em",
    })

    st.dataframe(
        view[["Nome", "Telefone", "Situacao", "Distancia (m)", "Status", "Registrado em"]],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "📥 Exportar CSV",
        gerar_csv(view),
        f"frequencia_geo_{int(evento['id_evento'])}.csv",
        "text/csv",
    )


# ═══════════════════════════════════════════════════════════════════════
# Aba 4: Mensagens
# ═══════════════════════════════════════════════════════════════════════

def _render_mensagens(slug):
    st.subheader("💬 Mensagens para presentes e ausentes")

    evento = _selecionar_evento(slug, apenas_ativos=False, key="evt_msg")
    if not evento:
        return

    tabela = _montar_tabela_frequencia(slug, evento["id_evento"])
    if tabela.empty:
        st.info("Nenhum membro ativo encontrado.")
        return

    grupo = st.radio(
        "Enviar para",
        ["Ausentes", "Presentes", "Todos"],
        horizontal=True,
        key="grupo_msg",
    )

    if grupo == "Presentes":
        destinatarios = tabela[tabela["presente"]].copy()
    elif grupo == "Ausentes":
        destinatarios = tabela[~tabela["presente"]].copy()
    else:
        destinatarios = tabela.copy()

    modelo_grupo = grupo if grupo != "Todos" else "Ausentes"
    modelo = st.text_area(
        "Mensagem",
        value=_mensagem_padrao(evento, modelo_grupo),
        height=130,
        help="Use {nome}, {evento}, {data}.",
    )

    data_fmt = pd.to_datetime(evento.get("data"), errors="coerce")
    data_txt = data_fmt.strftime("%d/%m/%Y") if pd.notna(data_fmt) else str(evento.get("data", ""))

    st.caption(f"📤 {len(destinatarios)} destinatario(s) selecionado(s).")

    linhas = []
    for _, row in destinatarios.iterrows():
        nome = str(row.get("nome", "")).strip()
        telefone = str(row.get("telefone", "")).strip()
        mensagem = (
            modelo.replace("{nome}", nome)
            .replace("{evento}", str(evento.get("nome", "")))
            .replace("{data}", data_txt)
        )
        link = _link_whatsapp(telefone, mensagem)
        linhas.append({
            "Nome": nome,
            "Telefone": telefone,
            "Situacao": row.get("situacao", ""),
            "Mensagem": mensagem,
            "Link WhatsApp": link,
        })

    df_msg = pd.DataFrame(linhas)
    if not df_msg.empty:
        st.dataframe(
            df_msg[["Nome", "Telefone", "Situacao", "Mensagem"]],
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "📥 Exportar lista",
            gerar_csv(df_msg),
            f"mensagens_geo_{grupo.lower()}.csv",
            "text/csv",
            use_container_width=True,
        )

    st.markdown("#### 📨 Envio em massa")

    if _whatsapp_api_configurada():
        st.success("✅ WhatsApp Cloud API configurada.")
    else:
        st.warning(
            "⚠️ WhatsApp Cloud API nao configurada. Voce ainda pode usar os links individuais abaixo."
        )

    qtd_validos = (
        int(df_msg["Telefone"].apply(_normalizar_tel_brasil).astype(bool).sum())
        if not df_msg.empty
        else 0
    )
    st.caption(f"📱 {qtd_validos} telefone(s) valido(s).")

    confirmar_envio = st.checkbox(
        f"Confirmo envio para {qtd_validos} destinatario(s) do grupo {grupo}",
        key=f"conf_envio_{int(evento['id_evento'])}_{grupo}",
        disabled=not _whatsapp_api_configurada() or qtd_validos == 0,
    )

    if st.button(
        "📤 Enviar mensagem em massa",
        type="primary",
        use_container_width=True,
        disabled=not confirmar_envio,
        key=f"btn_envio_{int(evento['id_evento'])}_{grupo}",
    ):
        resultados = []
        barra = st.progress(0)
        with st.spinner("Enviando..."):
            total_envios = max(1, len(df_msg))
            for _, row in df_msg.iterrows():
                ok, detalhe = _enviar_whatsapp_texto_api(row["Telefone"], row["Mensagem"])
                resultados.append({
                    "Nome": row["Nome"],
                    "Telefone": row["Telefone"],
                    "Status": "Enviado" if ok else "Erro",
                    "Detalhe": detalhe,
                })
                barra.progress(min(1.0, len(resultados) / total_envios))

        df_res = pd.DataFrame(resultados)
        enviados = int((df_res["Status"] == "Enviado").sum()) if not df_res.empty else 0
        erros = int((df_res["Status"] == "Erro").sum()) if not df_res.empty else 0
        st.success(f"✅ Concluido. Enviados: {enviados}. Erros: {erros}.")
        st.dataframe(df_res, use_container_width=True, hide_index=True)

    st.markdown("#### 🔗 Links individuais")
    if df_msg.empty:
        st.info("Nenhum destinatario.")
    else:
        for _, row in df_msg.iterrows():
            if row["Link WhatsApp"]:
                st.markdown(f'- [{row["Nome"]} - enviar pelo WhatsApp]({row["Link WhatsApp"]})')
            else:
                st.caption(f"- {row['Nome']} - sem telefone valido")


# ═══════════════════════════════════════════════════════════════════════
# Funcao principal
# ═══════════════════════════════════════════════════════════════════════

def render():
    slug = slug_da_sessao()

    st.title("📍 Monitoramento por Localizacao")
    st.caption(
        "Controle de presenca por georreferenciamento usando o GPS do celular. "
        "Envio de mensagens automatizadas para presentes e ausentes."
    )

    if not GEO_LIB_OK:
        st.error(
            "⚠️ **Biblioteca streamlit-geolocation nao instalada!**\n\n"
            "Adicione `streamlit-geolocation>=0.0.10` ao seu `requirements.txt` "
            "e faca o redeploy."
        )
        return

    st.info(
        "💡 **Importante:** a captura de localizacao depende da permissao do "
        "navegador/celular. Use somente com ciencia e consentimento dos "
        "participantes (LGPD)."
    )

    # ═══ CAPTURA UNICA NO TOPO ═══════════════════════════════════════
    # Esta e a UNICA chamada de streamlit_geolocation() em todo o modulo.
    # O resultado fica em st.session_state e e usado por todas as abas.
    st.markdown("### 📍 Capturar localizacao")
    _captura_unica_topo()

    st.divider()

    # ═══ TABS ═════════════════════════════════════════════════════════
    aba_evento, aba_checkin, aba_freq, aba_msg = st.tabs([
        "📅 Eventos",
        "📲 Check-in",
        "📊 Presentes e ausentes",
        "💬 Mensagens",
    ])

    with aba_evento:
        _render_eventos(slug)

    with aba_checkin:
        _render_checkin(slug)

    with aba_freq:
        _render_frequencia(slug)

    with aba_msg:
        _render_mensagens(slug)