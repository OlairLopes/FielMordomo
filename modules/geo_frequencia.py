import datetime
import math
import re
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
        st.session_state["geo_lat_evento"] = float(evento_atual.get("latitude", 0) or 0)
        st.session_state["geo_lon_evento"] = float(evento_atual.get("longitude", 0) or 0)
        st.session_state["geo_lat_evento_input"] = st.session_state["geo_lat_evento"]
        st.session_state["geo_lon_evento_input"] = st.session_state["geo_lon_evento"]

    st.markdown("#### Localiza\xe7\xe3o do evento")
    busca_maps = st.text_input(
        "Buscar local no Google Maps",
        key="geo_busca_maps",
        placeholder="Digite o nome do local, igreja ou endere\xe7o",
    )
    if str(busca_maps or "").strip():
        busca_texto = str(busca_maps).strip()
        if busca_texto.lower().startswith(("http://", "https://")):
            link_busca = busca_texto
            st.markdown(f"[Abrir link no Google Maps]({link_busca})")
        else:
            link_busca = (
                "https://www.google.com/maps/search/?api=1&query="
                + urllib.parse.quote_plus(busca_texto)
            )
            st.markdown(f"[Abrir busca no Google Maps]({link_busca})")

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
            if link_expandido:
                st.session_state["geo_link_maps"] = link_expandido
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
                "id_evento", "data", "nome", "latitude", "longitude",
                "raio_metros", "captura_habilitada", "ativo",
            ]].rename(columns={
                "id_evento": "ID",
                "data": "Data",
                "nome": "Evento",
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
