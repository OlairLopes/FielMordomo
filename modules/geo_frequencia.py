import datetime
import html
import math
import re
import json
import urllib.parse
import urllib.request

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from data.repository import (
    carregar_cadastros,
    formatar_telefone,
    listar_geo_eventos,
    salvar_geo_evento,
    excluir_geo_evento,
    obter_geo_evento,
    registrar_geo_presenca,
    listar_geo_presencas,
)
from utils.helpers import gerar_csv, slug_da_sessao


TIPOS_SITUACAO = {
    True: "Presente",
    False: "Ausente",
}


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
            if 200 <= resp.status < 300:
                return True, "Mensagem enviada."
            return False, f"Erro {resp.status}: {resp.read().decode('utf-8', errors='ignore')}"
    except Exception as exc:
        return False, f"Falha no envio: {exc}"


def _html_captura_local_evento():
    components.html(
        """
        <div style="font-family:Arial,sans-serif">
          <button onclick="capturarLocalEvento()" style="
            background:#334155;color:white;border:0;border-radius:8px;
            padding:9px 16px;font-size:14px;font-weight:700;cursor:pointer">
            Usar minha localiza\xe7\xe3o atual
          </button>
          <div id="geo_evento_msg" style="margin-top:8px;color:#475569;font-size:13px"></div>
        </div>
        <script>
        function capturarLocalEvento() {
          const msg = document.getElementById("geo_evento_msg");
          if (!navigator.geolocation) {
            msg.innerText = "Este navegador n\xe3o oferece geolocaliza\xe7\xe3o.";
            return;
          }
          msg.innerText = "Solicitando permiss\xe3o de localiza\xe7\xe3o...";
          navigator.geolocation.getCurrentPosition(
            function(pos) {
              const params = new URLSearchParams(window.parent.location.search);
              params.set("geo_evento_lat", pos.coords.latitude.toFixed(8));
              params.set("geo_evento_lon", pos.coords.longitude.toFixed(8));
              params.set("geo_evento_ts", Date.now().toString());
              window.parent.location.search = params.toString();
            },
            function(err) {
              msg.innerText = "N\xe3o foi poss\xedvel capturar a localiza\xe7\xe3o: " + err.message;
            },
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
          );
        }
        </script>
        """,
        height=84,
    )


def _extrair_coordenadas_google_maps(texto):
    texto = urllib.parse.unquote(str(texto or "").strip())
    if not texto:
        return None

    padroes = [
        r"@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)",
        r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)",
        r"[?&]q=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)",
        r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$",
    ]

    for padrao in padroes:
        match = re.search(padrao, texto)
        if not match:
            continue

        lat = float(match.group(1))
        lon = float(match.group(2))
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
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "FielMordomo/1.0 contato@fielmordomo.com.br"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
        if not dados:
            return None
        item = dados[0]
        display = str(item.get("display_name", endereco))
        return float(item["lat"]), float(item["lon"]), display
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
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "FielMordomo/1.0 contato@fielmordomo.com.br"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
        return str(dados.get("display_name", "") or "")
    except Exception:
        return ""


def _distancia_metros(lat1, lon1, lat2, lon2):
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


def _valor_query(chave, padrao=""):
    valor = st.query_params.get(chave, padrao)
    if isinstance(valor, list):
        return valor[0] if valor else padrao
    return valor


def _limpar_query_geo():
    for chave in ["geo_id_evento", "geo_id_cadastro", "geo_lat", "geo_lon", "geo_ts"]:
        if chave in st.query_params:
            del st.query_params[chave]


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


def _rotulo_evento(row):
    data_fmt = pd.to_datetime(row.get("data"), errors="coerce")
    data_txt = data_fmt.strftime("%d/%m/%Y") if pd.notna(data_fmt) else str(row.get("data", ""))
    status = "habilitado" if int(row.get("captura_habilitada", 0) or 0) else "desabilitado"
    return f'{int(row["id_evento"])} - {data_txt} - {row["nome"]} ({status})'


def _rotulo_membro(row):
    tel = row.get("telefone", "")
    return f'{int(row["id_cadastro"])} - {row["nome"]}' + (f" - {tel}" if tel else "")


def _html_captura_localizacao(id_evento, id_cadastro):
    components.html(
        f"""
        <div style="font-family:Arial,sans-serif">
          <button onclick="capturarGeo()" style="
            background:#0F6E56;color:white;border:0;border-radius:8px;
            padding:10px 18px;font-size:14px;font-weight:700;cursor:pointer">
            Capturar minha localiza\xe7\xe3o
          </button>
          <div id="geo_msg" style="margin-top:8px;color:#475569;font-size:13px"></div>
        </div>
        <script>
        function capturarGeo() {{
          const msg = document.getElementById("geo_msg");
          if (!navigator.geolocation) {{
            msg.innerText = "Este navegador n\xe3o oferece geolocaliza\xe7\xe3o.";
            return;
          }}
          msg.innerText = "Solicitando permiss\xe3o de localiza\xe7\xe3o...";
          navigator.geolocation.getCurrentPosition(
            function(pos) {{
              const params = new URLSearchParams(window.parent.location.search);
              params.set("geo_id_evento", "{int(id_evento)}");
              params.set("geo_id_cadastro", "{int(id_cadastro)}");
              params.set("geo_lat", pos.coords.latitude.toFixed(8));
              params.set("geo_lon", pos.coords.longitude.toFixed(8));
              params.set("geo_ts", Date.now().toString());
              window.parent.location.search = params.toString();
            }},
            function(err) {{
              msg.innerText = "N\xe3o foi poss\xedvel capturar a localiza\xe7\xe3o: " + err.message;
            }},
            {{ enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }}
          );
        }}
        </script>
        """,
        height=82,
    )


def _html_captura_localizacao_massa(id_evento):
    components.html(
        f"""
        <div style="font-family:Arial,sans-serif">
          <button onclick="capturarGeoMassa()" style="
            background:#0F6E56;color:white;border:0;border-radius:8px;
            padding:10px 18px;font-size:14px;font-weight:700;cursor:pointer">
            Capturar local do evento para check-in em massa
          </button>
          <div id="geo_massa_msg" style="margin-top:8px;color:#475569;font-size:13px"></div>
        </div>
        <script>
        function capturarGeoMassa() {{
          const msg = document.getElementById("geo_massa_msg");
          if (!navigator.geolocation) {{
            msg.innerText = "Este navegador n\xe3o oferece geolocaliza\xe7\xe3o.";
            return;
          }}
          msg.innerText = "Solicitando permiss\xe3o de localiza\xe7\xe3o...";
          navigator.geolocation.getCurrentPosition(
            function(pos) {{
              const params = new URLSearchParams(window.parent.location.search);
              params.set("geo_massa_id_evento", "{int(id_evento)}");
              params.set("geo_massa_lat", pos.coords.latitude.toFixed(8));
              params.set("geo_massa_lon", pos.coords.longitude.toFixed(8));
              params.set("geo_massa_ts", Date.now().toString());
              window.parent.location.search = params.toString();
            }},
            function(err) {{
              msg.innerText = "N\xe3o foi poss\xedvel capturar a localiza\xe7\xe3o: " + err.message;
            }},
            {{ enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }}
          );
        }}
        </script>
        """,
        height=84,
    )


def _processar_captura_query(slug):
    id_evento = _valor_query("geo_id_evento")
    id_cadastro = _valor_query("geo_id_cadastro")
    lat = _valor_query("geo_lat")
    lon = _valor_query("geo_lon")

    if not (id_evento and id_cadastro and lat and lon):
        return

    evento = obter_geo_evento(slug, id_evento)
    if not evento:
        st.error("Evento de localiza\xe7\xe3o n\xe3o encontrado.")
        _limpar_query_geo()
        return

    distancia = _distancia_metros(evento["latitude"], evento["longitude"], lat, lon)
    dentro = distancia <= float(evento.get("raio_metros", 30) or 30)
    habilitado = bool(int(evento.get("captura_habilitada", 0) or 0))
    ativo = bool(int(evento.get("ativo", 0) or 0))
    presente = dentro and habilitado and ativo

    if not ativo:
        status = "Evento inativo"
    elif not habilitado:
        status = "Captura desabilitada"
    elif dentro:
        status = "Presente por localiza\xe7\xe3o"
    else:
        status = "Fora do raio configurado"

    try:
        registrar_geo_presenca(
            slug=slug,
            id_evento=id_evento,
            id_cadastro=id_cadastro,
            latitude=lat,
            longitude=lon,
            distancia_m=distancia,
            dentro_raio=dentro,
            presente=presente,
            status=status,
        )
        if presente:
            st.success(f"Presen\xe7a registrada. Dist\xe2ncia aproximada: {distancia:.0f} m.")
        else:
            st.warning(f"Localiza\xe7\xe3o registrada como ausente. Motivo: {status}. Dist\xe2ncia: {distancia:.0f} m.")
    except Exception as exc:
        st.error(f"N\xe3o foi poss\xedvel registrar a presen\xe7a: {exc}")

    _limpar_query_geo()


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
    data_fmt = pd.to_datetime(evento.get("data"), errors="coerce")
    data_txt = data_fmt.strftime("%d/%m/%Y") if pd.notna(data_fmt) else str(evento.get("data", ""))
    if grupo == "Presentes":
        msg = str(evento.get("mensagem_presentes") or "").strip()
        if msg:
            return msg
        return "Paz do Senhor, {nome}! Sua presen\xe7a foi registrada em {evento}, no dia {data}. Deus aben\xe7oe."

    msg = str(evento.get("mensagem_ausentes") or "").strip()
    if msg:
        return msg
    return "Paz do Senhor, {nome}! Sentimos sua falta em {evento}, no dia {data}. Deus aben\xe7oe."


def _render_eventos(slug):
    st.subheader("Evento e local de refer\xeancia")
    st.caption("Cadastre o culto/reuni\xe3o, defina o ponto central e habilite a captura quando desejar.")

    eventos = listar_geo_eventos(slug, incluir_inativos=True)
    opcoes = ["Novo evento"]
    mapa_eventos = {}
    if not eventos.empty:
        for _, row in eventos.iterrows():
            rotulo = _rotulo_evento(row)
            opcoes.append(rotulo)
            mapa_eventos[rotulo] = row.to_dict()

    escolhido = st.selectbox("Evento", opcoes, key="geo_evento_editar")
    evento_atual = mapa_eventos.get(escolhido, {})

    data_default = pd.to_datetime(evento_atual.get("data"), errors="coerce")
    if pd.isna(data_default):
        data_default = pd.Timestamp(datetime.date.today())

    evento_ref = str(evento_atual.get("id_evento", "novo"))
    if st.session_state.get("geo_evento_ref") != evento_ref:
        st.session_state["geo_evento_ref"] = evento_ref
        st.session_state["geo_endereco_evento"] = str(evento_atual.get("endereco", "") or "")
        st.session_state["geo_lat_evento"] = float(evento_atual.get("latitude", 0) or 0)
        st.session_state["geo_lon_evento"] = float(evento_atual.get("longitude", 0) or 0)
        st.session_state["geo_endereco_evento_input"] = st.session_state["geo_endereco_evento"]
        st.session_state["geo_lat_evento_input"] = st.session_state["geo_lat_evento"]
        st.session_state["geo_lon_evento_input"] = st.session_state["geo_lon_evento"]

    st.markdown("#### Localiza\xe7\xe3o do evento")
    lat_evento_query = _valor_query("geo_evento_lat")
    lon_evento_query = _valor_query("geo_evento_lon")
    if lat_evento_query and lon_evento_query:
        try:
            st.session_state["geo_lat_evento"] = float(lat_evento_query)
            st.session_state["geo_lon_evento"] = float(lon_evento_query)
            st.session_state["geo_lat_evento_input"] = float(lat_evento_query)
            st.session_state["geo_lon_evento_input"] = float(lon_evento_query)
            endereco_capturado = _buscar_endereco_por_coordenadas(
                lat_evento_query,
                lon_evento_query,
            )
            if endereco_capturado:
                st.session_state["geo_endereco_evento"] = endereco_capturado
                st.session_state["geo_endereco_evento_input"] = endereco_capturado
            for chave in ["geo_evento_lat", "geo_evento_lon", "geo_evento_ts"]:
                if chave in st.query_params:
                    del st.query_params[chave]
            st.success("Localiza\xe7\xe3o atual carregada para o evento.")
            st.rerun()
        except ValueError:
            pass

    st.caption(
        "Modo mais r\xe1pido: estando no local do culto, clique em "
        "'Usar minha localiza\xe7\xe3o atual'. Para local distante, busque no Maps "
        "e cole o link ou as coordenadas."
    )
    _html_captura_local_evento()

    if "geo_endereco_evento_pendente" in st.session_state:
        st.session_state["geo_endereco_evento_input"] = st.session_state.pop(
            "geo_endereco_evento_pendente"
        )

    col_end_1, col_end_2 = st.columns([3, 1])
    with col_end_1:
        endereco_evento = st.text_input(
            "Endere\xe7o do evento",
            value=str(st.session_state.get("geo_endereco_evento", "") or ""),
            key="geo_endereco_evento_input",
            placeholder="Ex.: Assembleia de Deus Central, Mina\xe7u GO",
        )
    with col_end_2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        buscar_endereco = st.button("Buscar coordenadas", use_container_width=True)

    if buscar_endereco:
        resultado = _buscar_coordenadas_por_endereco(endereco_evento)
        if resultado:
            lat_busca, lon_busca, endereco_formatado = resultado
            st.session_state["geo_endereco_evento"] = endereco_formatado
            st.session_state["geo_endereco_evento_pendente"] = endereco_formatado
            st.session_state["geo_lat_evento"] = lat_busca
            st.session_state["geo_lon_evento"] = lon_busca
            st.session_state["geo_lat_evento_input"] = lat_busca
            st.session_state["geo_lon_evento_input"] = lon_busca
            st.success("Coordenadas encontradas pelo endere\xe7o.")
            st.rerun()
        else:
            st.error("N\xe3o encontrei coordenadas para esse endere\xe7o. Tente complementar com cidade e estado.")

    busca_maps = st.text_input(
        "Buscar local no Google Maps",
        key="geo_busca_maps",
        placeholder="Digite o nome do local, igreja ou endere\xe7o",
    )
    if str(busca_maps or "").strip():
        busca_texto = str(busca_maps).strip()
        if busca_texto.lower().startswith(("http://", "https://")):
            link_busca = busca_texto
            _botao_abrir_google_maps(link_busca, "Abrir link no Google Maps")
        else:
            link_busca = (
                "https://www.google.com/maps/search/?api=1&query="
                + urllib.parse.quote_plus(busca_texto)
            )
            _botao_abrir_google_maps(link_busca, "Abrir busca no Google Maps")

    col_maps_1, col_maps_2 = st.columns([3, 1])
    with col_maps_1:
        texto_maps = st.text_input(
            "Cole aqui o link ou as coordenadas do Google Maps",
            key="geo_link_maps",
            placeholder="-13.533000, -48.220000 ou link completo do Google Maps",
        )
    with col_maps_2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        usar_maps = st.button("Usar coordenadas", use_container_width=True)

    if usar_maps:
        coords, link_expandido = _obter_coordenadas_de_texto_ou_link(texto_maps)
        if coords:
            st.session_state["geo_lat_evento"] = coords[0]
            st.session_state["geo_lon_evento"] = coords[1]
            st.session_state["geo_lat_evento_input"] = coords[0]
            st.session_state["geo_lon_evento_input"] = coords[1]
            endereco_maps = _buscar_endereco_por_coordenadas(coords[0], coords[1])
            if endereco_maps:
                st.session_state["geo_endereco_evento"] = endereco_maps
                st.session_state["geo_endereco_evento_pendente"] = endereco_maps
            st.success("Coordenadas carregadas do Google Maps.")
            st.rerun()
        else:
            st.error(
                "N\xe3o consegui encontrar coordenadas nesse link/texto. "
                "Abra o local no Google Maps, clique com o bot\xe3o direito no ponto do mapa "
                "e copie latitude,longitude."
            )
            if link_expandido:
                st.caption(f"Link expandido analisado: {link_expandido}")

    with st.form("form_geo_evento"):
        c1, c2 = st.columns([2, 1])
        with c1:
            nome = st.text_input(
                "Nome do evento",
                value=str(evento_atual.get("nome", "Culto") or "Culto"),
            )
        with c2:
            data = st.date_input(
                "Data",
                value=data_default.date(),
                format="DD/MM/YYYY",
            )

        c3, c4, c5 = st.columns(3)
        with c3:
            latitude = st.number_input(
                "Latitude do local",
                value=float(st.session_state.get("geo_lat_evento", 0) or 0),
                format="%.8f",
                key="geo_lat_evento_input",
            )
        with c4:
            longitude = st.number_input(
                "Longitude do local",
                value=float(st.session_state.get("geo_lon_evento", 0) or 0),
                format="%.8f",
                key="geo_lon_evento_input",
            )
        with c5:
            raio = st.number_input(
                "Raio permitido (metros)",
                min_value=5,
                max_value=1000,
                value=int(evento_atual.get("raio_metros", 30) or 30),
                step=5,
            )

        c6, c7 = st.columns(2)
        with c6:
            captura = st.checkbox(
                "Habilitar captura de localiza\xe7\xe3o",
                value=bool(int(evento_atual.get("captura_habilitada", 0) or 0)),
            )
        with c7:
            ativo = st.checkbox(
                "Evento ativo",
                value=bool(int(evento_atual.get("ativo", 1) or 1)),
            )

        mensagem_presentes = st.text_area(
            "Mensagem padr\xe3o para presentes",
            value=str(evento_atual.get("mensagem_presentes", "") or ""),
            height=90,
        )
        mensagem_ausentes = st.text_area(
            "Mensagem padr\xe3o para ausentes",
            value=str(evento_atual.get("mensagem_ausentes", "") or ""),
            height=90,
        )
        observacoes = st.text_area(
            "Observa\xe7\xf5es",
            value=str(evento_atual.get("observacoes", "") or ""),
            height=80,
        )

        salvar = st.form_submit_button("Salvar evento", type="primary")

    if salvar:
        try:
            id_evento = evento_atual.get("id_evento")
            salvar_geo_evento(
                slug=slug,
                id_evento=id_evento,
                nome=nome,
                data=data.isoformat(),
                endereco=endereco_evento,
                latitude=latitude,
                longitude=longitude,
                raio_metros=raio,
                captura_habilitada=captura,
                ativo=ativo,
                mensagem_presentes=mensagem_presentes,
                mensagem_ausentes=mensagem_ausentes,
                observacoes=observacoes,
            )
            st.success("Evento salvo com sucesso.")
            st.rerun()
        except Exception as exc:
            st.error(f"N\xe3o foi poss\xedvel salvar o evento: {exc}")

    if evento_atual.get("id_evento"):
        st.markdown("#### Editar, cancelar ou excluir")
        st.caption(
            "Cancelar mant\xe9m o evento no hist\xf3rico, mas desativa a captura. "
            "Excluir remove o evento e os registros de presen\xe7a vinculados."
        )
        acao_c1, acao_c2 = st.columns(2)
        with acao_c1:
            if st.button("Cancelar/desativar evento", use_container_width=True):
                try:
                    salvar_geo_evento(
                        slug=slug,
                        id_evento=evento_atual.get("id_evento"),
                        nome=evento_atual.get("nome", ""),
                        data=evento_atual.get("data", ""),
                        endereco=evento_atual.get("endereco", ""),
                        latitude=evento_atual.get("latitude", 0),
                        longitude=evento_atual.get("longitude", 0),
                        raio_metros=evento_atual.get("raio_metros", 30),
                        captura_habilitada=False,
                        ativo=False,
                        mensagem_presentes=evento_atual.get("mensagem_presentes", ""),
                        mensagem_ausentes=evento_atual.get("mensagem_ausentes", ""),
                        observacoes=(
                            str(evento_atual.get("observacoes", "") or "")
                            + "\nEvento cancelado/desativado."
                        ).strip(),
                    )
                    st.success("Evento cancelado/desativado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"N\xe3o foi poss\xedvel cancelar o evento: {exc}")

        with acao_c2:
            confirmar_exclusao = st.checkbox(
                "Confirmo que desejo excluir definitivamente",
                key=f"geo_conf_excluir_{int(evento_atual['id_evento'])}",
            )
            if st.button(
                "Excluir evento",
                use_container_width=True,
                disabled=not confirmar_exclusao,
            ):
                try:
                    excluir_geo_evento(slug, evento_atual["id_evento"])
                    st.success("Evento exclu\xeddo.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"N\xe3o foi poss\xedvel excluir o evento: {exc}")

    st.divider()
    if eventos.empty:
        st.info("Nenhum evento cadastrado ainda.")
    else:
        df_view = eventos.copy()
        df_view["data"] = pd.to_datetime(df_view["data"], errors="coerce").dt.strftime("%d/%m/%Y")
        df_view["captura_habilitada"] = df_view["captura_habilitada"].map({1: "Sim", 0: "N\xe3o"})
        df_view["ativo"] = df_view["ativo"].map({1: "Sim", 0: "N\xe3o"})
        st.dataframe(
            df_view[[
                "id_evento", "data", "nome", "endereco", "latitude", "longitude",
                "raio_metros", "captura_habilitada", "ativo",
            ]].rename(columns={
                "id_evento": "ID",
                "data": "Data",
                "nome": "Evento",
                "endereco": "Endere\xe7o",
                "latitude": "Latitude",
                "longitude": "Longitude",
                "raio_metros": "Raio (m)",
                "captura_habilitada": "Captura",
                "ativo": "Ativo",
            }),
            use_container_width=True,
            hide_index=True,
        )


def _selecionar_evento(slug, apenas_ativos=False, apenas_habilitados=False, key="geo_evento"):
    eventos = listar_geo_eventos(slug, incluir_inativos=not apenas_ativos)
    if eventos.empty:
        st.info("Cadastre um evento primeiro.")
        return None

    if apenas_ativos:
        eventos = eventos[eventos["ativo"].astype(int) == 1]
    if apenas_habilitados:
        eventos = eventos[eventos["captura_habilitada"].astype(int) == 1]

    if eventos.empty:
        st.warning("Nenhum evento dispon\xedvel para este filtro.")
        return None

    mapa = {}
    opcoes = []
    for _, row in eventos.iterrows():
        rotulo = _rotulo_evento(row)
        mapa[rotulo] = row.to_dict()
        opcoes.append(rotulo)

    escolhido = st.selectbox("Evento", opcoes, key=key)
    return mapa[escolhido]


def _render_checkin(slug):
    st.subheader("Check-in por localiza\xe7\xe3o")
    st.caption("O navegador do celular pedir\xe1 permiss\xe3o para acessar a localiza\xe7\xe3o.")

    _processar_captura_query(slug)

    evento = _selecionar_evento(
        slug,
        apenas_ativos=True,
        apenas_habilitados=False,
        key="geo_evento_checkin",
    )
    if not evento:
        return

    if not bool(int(evento.get("captura_habilitada", 0) or 0)):
        st.warning("A captura de localiza\xe7\xe3o est\xe1 desabilitada para este evento.")

    membros = _membros_ativos(slug)
    if membros.empty:
        st.info("Nenhum membro ativo encontrado.")
        return

    evento_massa_ref = str(int(evento["id_evento"]))
    if st.session_state.get("geo_massa_evento_ref") != evento_massa_ref:
        st.session_state["geo_massa_evento_ref"] = evento_massa_ref
        st.session_state["geo_massa_lat"] = float(evento.get("latitude", 0) or 0)
        st.session_state["geo_massa_lon"] = float(evento.get("longitude", 0) or 0)
        st.session_state["geo_massa_lat_input"] = st.session_state["geo_massa_lat"]
        st.session_state["geo_massa_lon_input"] = st.session_state["geo_massa_lon"]
        st.session_state["geo_massa_membros_sel"] = []

    id_massa = _valor_query("geo_massa_id_evento")
    lat_massa = _valor_query("geo_massa_lat")
    lon_massa = _valor_query("geo_massa_lon")
    if id_massa and lat_massa and lon_massa and str(id_massa) == str(int(evento["id_evento"])):
        try:
            st.session_state["geo_massa_lat"] = float(lat_massa)
            st.session_state["geo_massa_lon"] = float(lon_massa)
            st.session_state["geo_massa_lat_input"] = float(lat_massa)
            st.session_state["geo_massa_lon_input"] = float(lon_massa)
            for chave in ["geo_massa_id_evento", "geo_massa_lat", "geo_massa_lon", "geo_massa_ts"]:
                if chave in st.query_params:
                    del st.query_params[chave]
            st.success("Local do evento capturado para check-in em massa.")
            st.rerun()
        except ValueError:
            pass

    mapa_membros = {}
    opcoes = []
    for _, row in membros.iterrows():
        rotulo = _rotulo_membro(row)
        mapa_membros[rotulo] = row.to_dict()
        opcoes.append(rotulo)

    membro_label = st.selectbox("Membro", opcoes, key="geo_membro_checkin")
    membro = mapa_membros[membro_label]
    st.caption(f"Telefone no cadastro: {membro.get('telefone') or 'sem telefone'}")

    _html_captura_localizacao(evento["id_evento"], membro["id_cadastro"])

    with st.expander("Registrar localiza\xe7\xe3o manualmente"):
        c1, c2 = st.columns(2)
        lat = c1.number_input("Latitude", value=0.0, format="%.8f", key="geo_lat_manual")
        lon = c2.number_input("Longitude", value=0.0, format="%.8f", key="geo_lon_manual")
        if st.button("Registrar localiza\xe7\xe3o informada", type="primary"):
            distancia = _distancia_metros(evento["latitude"], evento["longitude"], lat, lon)
            dentro = distancia <= float(evento.get("raio_metros", 30) or 30)
            habilitado = bool(int(evento.get("captura_habilitada", 0) or 0))
            presente = dentro and habilitado
            status = "Presente por localiza\xe7\xe3o" if presente else "Fora do raio ou captura desabilitada"
            try:
                registrar_geo_presenca(
                    slug,
                    evento["id_evento"],
                    membro["id_cadastro"],
                    lat,
                    lon,
                    distancia,
                    dentro,
                    presente,
                    status,
                )
                st.success("Registro salvo.")
            except Exception as exc:
                st.error(f"N\xe3o foi poss\xedvel registrar: {exc}")

    st.divider()
    st.markdown("### Check-in em massa no local")
    st.caption(
        "Use quando a secretaria ou lideran\xe7a est\xe1 no local do evento. "
        "O sistema captura a localiza\xe7\xe3o deste aparelho uma vez e registra os membros selecionados."
    )

    _html_captura_localizacao_massa(evento["id_evento"])

    lat_padrao = float(st.session_state.get("geo_massa_lat", evento.get("latitude", 0)) or 0)
    lon_padrao = float(st.session_state.get("geo_massa_lon", evento.get("longitude", 0)) or 0)
    mlat, mlon, mdist = st.columns(3)
    with mlat:
        lat_massa_input = st.number_input(
            "Latitude do check-in em massa",
            value=lat_padrao,
            format="%.8f",
            key="geo_massa_lat_input",
        )
    with mlon:
        lon_massa_input = st.number_input(
            "Longitude do check-in em massa",
            value=lon_padrao,
            format="%.8f",
            key="geo_massa_lon_input",
        )
    with mdist:
        distancia_massa = _distancia_metros(
            evento["latitude"],
            evento["longitude"],
            lat_massa_input,
            lon_massa_input,
        )
        st.metric("Dist\xe2ncia do evento", f"{distancia_massa:.0f} m")

    dentro_massa = distancia_massa <= float(evento.get("raio_metros", 30) or 30)
    if dentro_massa:
        st.success("A localiza\xe7\xe3o informada est\xe1 dentro do raio permitido do evento.")
    else:
        st.warning("A localiza\xe7\xe3o informada est\xe1 fora do raio permitido do evento.")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Selecionar todos os membros", use_container_width=True):
            st.session_state["geo_massa_membros_sel"] = opcoes.copy()
            st.rerun()
    with b2:
        if st.button("Limpar sele\xe7\xe3o em massa", use_container_width=True):
            st.session_state["geo_massa_membros_sel"] = []
            st.rerun()

    selecionados = st.multiselect(
        "Membros presentes no local",
        opcoes,
        key="geo_massa_membros_sel",
    )

    confirmar_massa = st.checkbox(
        f"Confirmo o registro de {len(selecionados)} membro(s) selecionado(s)",
        key=f"geo_conf_massa_{int(evento['id_evento'])}",
    )

    if st.button(
        "Registrar check-in em massa",
        type="primary",
        use_container_width=True,
        disabled=not confirmar_massa or not selecionados,
    ):
        habilitado = bool(int(evento.get("captura_habilitada", 0) or 0))
        presente = bool(dentro_massa and habilitado)
        status = (
            "Presente por check-in em massa"
            if presente
            else "Check-in em massa fora do raio ou captura desabilitada"
        )
        registrados = 0
        erros = []
        for rotulo in selecionados:
            membro_massa = mapa_membros.get(rotulo)
            if not membro_massa:
                continue
            try:
                registrar_geo_presenca(
                    slug,
                    evento["id_evento"],
                    membro_massa["id_cadastro"],
                    lat_massa_input,
                    lon_massa_input,
                    distancia_massa,
                    dentro_massa,
                    presente,
                    status,
                )
                registrados += 1
            except Exception as exc:
                erros.append(f"{membro_massa.get('nome', rotulo)}: {exc}")

        if registrados:
            st.success(f"{registrados} check-in(s) registrados.")
        if erros:
            st.error("Alguns registros falharam: " + " | ".join(erros[:5]))

    st.divider()
    st.markdown("### Solicitar autoriza\xe7\xe3o de localiza\xe7\xe3o")
    st.caption(
        "Envia uma mensagem para os membros abrirem o check-in no pr\xf3prio celular. "
        "A permiss\xe3o de localiza\xe7\xe3o precisa ser autorizada individualmente por cada membro."
    )

    tabela_aut = _montar_tabela_frequencia(slug, evento["id_evento"])
    grupo_aut = st.radio(
        "Enviar solicita\xe7\xe3o para",
        ["Todos os membros ativos", "Somente quem ainda n\xe3o fez check-in"],
        horizontal=True,
        key=f"geo_grupo_aut_{int(evento['id_evento'])}",
    )
    if grupo_aut == "Somente quem ainda n\xe3o fez check-in":
        destinatarios_aut = tabela_aut[~tabela_aut["presente"]].copy()
    else:
        destinatarios_aut = tabela_aut.copy()

    data_fmt_aut = pd.to_datetime(evento.get("data"), errors="coerce")
    data_txt_aut = data_fmt_aut.strftime("%d/%m/%Y") if pd.notna(data_fmt_aut) else str(evento.get("data", ""))

    link_checkin = st.text_input(
        "Link para o membro abrir o check-in",
        value="",
        key=f"geo_link_checkin_{int(evento['id_evento'])}",
        placeholder="Cole aqui o link da p\xe1gina de check-in, se houver",
    )
    modelo_aut = st.text_area(
        "Mensagem de solicita\xe7\xe3o",
        value=(
            "Paz do Senhor, {nome}! Para registrar sua presen\xe7a em {evento}, "
            "no dia {data}, abra o link abaixo pelo seu celular e autorize a localiza\xe7\xe3o:\n\n"
            "{link}\n\n"
            "Caso j\xe1 esteja no local, fa\xe7a o check-in assim que poss\xedvel."
        ),
        height=140,
        key=f"geo_msg_aut_{int(evento['id_evento'])}",
        help="Use {nome}, {evento}, {data} e {link}.",
    )

    linhas_aut = []
    for _, row in destinatarios_aut.iterrows():
        nome_aut = str(row.get("nome", "")).strip()
        telefone_aut = str(row.get("telefone", "")).strip()
        mensagem_aut = (
            modelo_aut.replace("{nome}", nome_aut)
            .replace("{evento}", str(evento.get("nome", "")))
            .replace("{data}", data_txt_aut)
            .replace("{link}", str(link_checkin or "").strip())
        )
        linhas_aut.append({
            "Nome": nome_aut,
            "Telefone": telefone_aut,
            "Situa\xe7\xe3o": row.get("situacao", ""),
            "Mensagem": mensagem_aut,
            "Link WhatsApp": _link_whatsapp(telefone_aut, mensagem_aut),
        })

    df_aut = pd.DataFrame(linhas_aut)
    st.caption(f"{len(df_aut)} destinat\xe1rio(s) selecionado(s).")
    if not df_aut.empty:
        st.dataframe(
            df_aut[["Nome", "Telefone", "Situa\xe7\xe3o"]],
            use_container_width=True,
            hide_index=True,
        )

    qtd_validos_aut = (
        int(df_aut["Telefone"].apply(_normalizar_tel_brasil).astype(bool).sum())
        if not df_aut.empty
        else 0
    )
    if _whatsapp_api_configurada():
        st.success("WhatsApp Cloud API configurada para envio em massa.")
    else:
        st.warning(
            "WhatsApp Cloud API n\xe3o configurada. Voc\xea ainda pode usar os links individuais abaixo."
        )

    confirmar_aut = st.checkbox(
        f"Confirmo o envio da solicita\xe7\xe3o para {qtd_validos_aut} membro(s)",
        key=f"geo_conf_aut_{int(evento['id_evento'])}",
        disabled=not _whatsapp_api_configurada() or qtd_validos_aut == 0,
    )

    if st.button(
        "Enviar solicita\xe7\xe3o em massa",
        type="primary",
        use_container_width=True,
        disabled=not confirmar_aut,
        key=f"geo_btn_aut_{int(evento['id_evento'])}",
    ):
        resultados_aut = []
        barra_aut = st.progress(0)
        with st.spinner("Enviando solicita\xe7\xf5es..."):
            total_aut = max(1, len(df_aut))
            for _, row in df_aut.iterrows():
                ok, detalhe = _enviar_whatsapp_texto_api(row["Telefone"], row["Mensagem"])
                resultados_aut.append({
                    "Nome": row["Nome"],
                    "Telefone": row["Telefone"],
                    "Status": "Enviado" if ok else "Erro",
                    "Detalhe": detalhe,
                })
                barra_aut.progress(min(1.0, len(resultados_aut) / total_aut))

        df_result_aut = pd.DataFrame(resultados_aut)
        enviados_aut = int((df_result_aut["Status"] == "Enviado").sum()) if not df_result_aut.empty else 0
        erros_aut = int((df_result_aut["Status"] == "Erro").sum()) if not df_result_aut.empty else 0
        st.success(f"Solicita\xe7\xf5es processadas. Enviadas: {enviados_aut}. Erros: {erros_aut}.")
        st.dataframe(df_result_aut, use_container_width=True, hide_index=True)

    with st.expander("Links individuais de solicita\xe7\xe3o"):
        if df_aut.empty:
            st.info("Nenhum destinat\xe1rio para este filtro.")
        else:
            for _, row in df_aut.iterrows():
                if row["Link WhatsApp"]:
                    st.markdown(f'[{row["Nome"]} - enviar solicita\xe7\xe3o]({row["Link WhatsApp"]})')
                else:
                    st.caption(f"{row['Nome']} - sem telefone v\xe1lido no cadastro.")


def _render_frequencia(slug):
    st.subheader("Presentes e ausentes")
    evento = _selecionar_evento(slug, apenas_ativos=False, key="geo_evento_freq")
    if not evento:
        return

    tabela = _montar_tabela_frequencia(slug, evento["id_evento"])
    if tabela.empty:
        st.info("Nenhum membro ativo encontrado.")
        return

    qtd_presentes = int(tabela["presente"].sum())
    qtd_total = len(tabela)
    qtd_ausentes = qtd_total - qtd_presentes

    c1, c2, c3 = st.columns(3)
    c1.metric("Membros ativos", qtd_total)
    c2.metric("Presentes", qtd_presentes)
    c3.metric("Ausentes", qtd_ausentes)

    filtro = st.radio(
        "Filtro",
        ["Todos", "Presentes", "Ausentes"],
        horizontal=True,
        key="geo_filtro_freq",
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
        "situacao": "Situa\xe7\xe3o",
        "distancia_m": "Dist\xe2ncia (m)",
        "status": "Status",
        "registrado_em": "Registrado em",
    })

    st.dataframe(
        view[["Nome", "Telefone", "Situa\xe7\xe3o", "Dist\xe2ncia (m)", "Status", "Registrado em"]],
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Exportar CSV",
        gerar_csv(view),
        f"frequencia_geo_{int(evento['id_evento'])}.csv",
        "text/csv",
    )


def _render_mensagens(slug):
    st.subheader("Mensagens para presentes e ausentes")
    evento = _selecionar_evento(slug, apenas_ativos=False, key="geo_evento_msg")
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
        key="geo_grupo_msg",
    )

    if grupo == "Presentes":
        destinatarios = tabela[tabela["presente"]].copy()
    elif grupo == "Ausentes":
        destinatarios = tabela[~tabela["presente"]].copy()
    else:
        destinatarios = tabela.copy()

    modelo = st.text_area(
        "Mensagem",
        value=_mensagem_padrao(evento, grupo if grupo != "Todos" else "Ausentes"),
        height=130,
        help="Use {nome}, {evento} e {data} na mensagem.",
    )

    data_fmt = pd.to_datetime(evento.get("data"), errors="coerce")
    data_txt = data_fmt.strftime("%d/%m/%Y") if pd.notna(data_fmt) else str(evento.get("data", ""))

    st.caption(f"{len(destinatarios)} destinat\xe1rio(s) selecionado(s).")

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
            "Situa\xe7\xe3o": row.get("situacao", ""),
            "Mensagem": mensagem,
            "Link WhatsApp": link,
        })

    df_msg = pd.DataFrame(linhas)
    st.dataframe(
        df_msg[["Nome", "Telefone", "Situa\xe7\xe3o", "Mensagem"]],
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Exportar lista de mensagens",
        gerar_csv(df_msg),
        f"mensagens_geo_{grupo.lower()}.csv",
        "text/csv",
        use_container_width=True,
    )

    st.markdown("#### Envio em massa")
    if _whatsapp_api_configurada():
        st.success("WhatsApp Cloud API configurada. O envio em massa pode ser usado.")
    else:
        st.warning(
            "WhatsApp Cloud API n\xe3o configurada. Para envio em massa com um clique, "
            "configure `[whatsapp] access_token` e `phone_number_id` no st.secrets."
        )

    qtd_validos = int(df_msg["Telefone"].apply(_normalizar_tel_brasil).astype(bool).sum()) if not df_msg.empty else 0
    st.caption(f"{qtd_validos} telefone(s) v\xe1lido(s) para envio por API.")

    confirmar_envio = st.checkbox(
        f"Confirmo o envio da mensagem para {qtd_validos} destinat\xe1rio(s) do grupo {grupo}",
        key=f"geo_conf_envio_massa_{int(evento['id_evento'])}_{grupo}",
        disabled=not _whatsapp_api_configurada() or qtd_validos == 0,
    )

    if st.button(
        "Enviar mensagem em massa",
        type="primary",
        use_container_width=True,
        disabled=not confirmar_envio,
    ):
        resultados = []
        barra = st.progress(0)
        with st.spinner("Enviando mensagens..."):
            total_envios = max(1, len(df_msg))
            for idx, row in df_msg.iterrows():
                ok, detalhe = _enviar_whatsapp_texto_api(row["Telefone"], row["Mensagem"])
                resultados.append({
                    "Nome": row["Nome"],
                    "Telefone": row["Telefone"],
                    "Status": "Enviado" if ok else "Erro",
                    "Detalhe": detalhe,
                })
                barra.progress(min(1.0, (len(resultados)) / total_envios))

        df_resultados = pd.DataFrame(resultados)
        enviados = int((df_resultados["Status"] == "Enviado").sum()) if not df_resultados.empty else 0
        erros = int((df_resultados["Status"] == "Erro").sum()) if not df_resultados.empty else 0
        st.success(f"Envio conclu\xeddo. Enviados: {enviados}. Erros: {erros}.")
        st.dataframe(df_resultados, use_container_width=True, hide_index=True)

    st.markdown("#### Links de envio")
    if df_msg.empty:
        st.info("Nenhum destinat\xe1rio para este filtro.")
    else:
        for _, row in df_msg.iterrows():
            if row["Link WhatsApp"]:
                st.markdown(
                    f'[{row["Nome"]} - enviar pelo WhatsApp]({row["Link WhatsApp"]})'
                )
            else:
                st.caption(f"{row['Nome']} - sem telefone v\xe1lido no cadastro.")


def render():
    slug = slug_da_sessao()
    st.title("Monitoramento por Localiza\xe7\xe3o")
    st.caption(
        "Controle de presen\xe7a por georreferenciamento, usando o celular cadastrado "
        "do membro e envio posterior de mensagens para presentes ou ausentes."
    )

    st.info(
        "A captura de localiza\xe7\xe3o depende da permiss\xe3o do navegador/celular. "
        "Use esse recurso somente com ci\xeancia e consentimento dos participantes."
    )

    aba_evento, aba_checkin, aba_freq, aba_msg = st.tabs([
        "Eventos",
        "Check-in",
        "Presentes e ausentes",
        "Mensagens",
    ])

    with aba_evento:
        _render_eventos(slug)

    with aba_checkin:
        _render_checkin(slug)

    with aba_freq:
        _render_frequencia(slug)

    with aba_msg:
        _render_mensagens(slug)
