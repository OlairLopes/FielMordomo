import datetime as dt
import logging
import re
import urllib.parse

import pandas as pd
import requests
import streamlit as st

from data.repository import (
    atualizar_notificacao_pedido_oracao,
    atualizar_status_pedido_oracao,
    listar_horarios_visita_pastoral,
    listar_pastores_auxiliares,
    listar_pedidos_oracao,
    localizar_cadastro_publico,
    obter_config_igreja,
    registrar_pedido_oracao,
    salvar_horario_visita_pastoral,
    validar_codigo_atualizacao_cadastral,
    excluir_horario_visita_pastoral,
)
from utils.helpers import gerar_csv, slug_da_sessao


LOGGER = logging.getLogger(__name__)
PHONE_NUMBER_ID_RE = re.compile(r"^\d{5,30}$")
API_VERSION_RE = re.compile(r"^v\d{1,2}\.\d{1,2}$")
TIPOS_PEDIDO = [
    "Pedido de oracao",
    "Agradecimento",
    "Aconselhamento",
    "Solicitacao de visita pastoral",
    "Solicitacao de atendimento no gabinete",
]
PRIVACIDADE_OPCOES = ["Pastor", "Lideres", "Toda Igreja"]
STATUS_PEDIDO = ["Novo", "Em acompanhamento", "Orado", "Visitado", "Arquivado"]
MENSAGEM_ORACAO_PADRAO = """Paz do Senhor!

Novo pedido recebido pelo FielMordomo.

Congregacao: {congregacao}
Membro: {nome}
Tipo: {tipo}
Motivo: {motivo}
Privacidade: {privacidade}
Solicitou visita: {visita}
Horario da visita: {horario}

Pedido:
{pedido}
"""


def _hoje():
    return dt.date.today()


def _normalizar_tel_brasil(tel):
    digitos = "".join(c for c in str(tel or "") if c.isdigit())
    if not digitos:
        return ""
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if len(digitos) < 12 or len(digitos) > 15:
        return ""
    return digitos


def _link_whatsapp(tel, mensagem):
    numero = _normalizar_tel_brasil(tel)
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={urllib.parse.quote(mensagem)}"


def _config_whatsapp():
    try:
        cfg = st.secrets.get("whatsapp", {})
    except Exception:
        cfg = {}
    resultado = {
        "access_token": str(cfg.get("access_token", "")).strip(),
        "phone_number_id": str(cfg.get("phone_number_id", "")).strip(),
        "api_version": str(cfg.get("api_version", "v20.0")).strip(),
    }
    if not PHONE_NUMBER_ID_RE.fullmatch(resultado["phone_number_id"]):
        resultado["phone_number_id"] = ""
    if not API_VERSION_RE.fullmatch(resultado["api_version"]):
        resultado["api_version"] = "v20.0"
    return resultado


def _whatsapp_api_configurada():
    cfg = _config_whatsapp()
    return bool(cfg["access_token"] and cfg["phone_number_id"])


def _enviar_whatsapp_texto_api(telefone, mensagem):
    cfg = _config_whatsapp()
    numero = _normalizar_tel_brasil(telefone)
    if not numero:
        return False, "Telefone vazio ou invalido."
    if not cfg["access_token"] or not cfg["phone_number_id"]:
        return False, "WhatsApp Cloud API nao configurada."

    url = f"https://graph.facebook.com/{cfg['api_version']}/{cfg['phone_number_id']}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"preview_url": False, "body": mensagem},
    }
    headers = {
        "Authorization": f"Bearer {cfg['access_token']}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        if 200 <= resp.status_code < 300:
            return True, "Enviado."
        LOGGER.warning("WhatsApp Cloud API retornou HTTP %s: %s", resp.status_code, resp.text[:1000])
        return False, f"HTTP {resp.status_code}"
    except requests.RequestException:
        LOGGER.exception("Falha ao enviar pedido de oracao pelo WhatsApp.")
        return False, "Falha de comunicacao."


def _formatar_data(valor):
    try:
        return pd.to_datetime(valor).strftime("%d/%m/%Y")
    except Exception:
        return str(valor or "")


def _slot_label(row):
    data = _formatar_data(row.get("data"))
    local = str(row.get("local") or "").strip()
    trecho_local = f" - {local}" if local else ""
    return f'{data} das {row.get("hora_inicio")} as {row.get("hora_fim")}{trecho_local}'


def _contatos_pastorais(slug):
    contatos = []
    tel_pastor = obter_config_igreja(slug, "whatsapp_pastor_oracao", "")
    nome_pastor = obter_config_igreja(slug, "nome_pastor_oracao", "Pastor")
    if _normalizar_tel_brasil(tel_pastor):
        contatos.append({"nome": nome_pastor or "Pastor", "telefone": tel_pastor, "tipo": "Pastor"})
    try:
        pastores_aux = listar_pastores_auxiliares(slug, incluir_inativos=False)
    except Exception:
        LOGGER.exception("Nao foi possivel listar pastores auxiliares para notificacao.")
        pastores_aux = pd.DataFrame()
    if not pastores_aux.empty:
        for _, row in pastores_aux.iterrows():
            telefone = row.get("telefone", "")
            if _normalizar_tel_brasil(telefone):
                contatos.append({
                    "nome": row.get("nome", "Pastor auxiliar"),
                    "telefone": telefone,
                    "tipo": "Pastor auxiliar",
                })
    return contatos


def _montar_mensagem(
    slug,
    membro,
    tipo_pedido,
    pedido,
    privacidade,
    deseja_visita,
    slot_texto,
    congregacao="",
    motivo_oracao="",
):
    modelo = obter_config_igreja(slug, "mensagem_whatsapp_pedido_oracao", MENSAGEM_ORACAO_PADRAO)
    return str(modelo or MENSAGEM_ORACAO_PADRAO).format(
        nome=membro.get("nome", ""),
        congregacao=congregacao or membro.get("congregacao", "") or slug,
        tipo=tipo_pedido,
        motivo=motivo_oracao,
        privacidade=privacidade,
        confidencial="Sim" if privacidade == "Pastor" else "Nao",
        visita="Sim" if deseja_visita else "Nao",
        horario=slot_texto or "Nao agendada",
        pedido=pedido,
    )


def _notificar_pastores(
    slug,
    id_pedido,
    membro,
    tipo_pedido,
    pedido,
    privacidade,
    deseja_visita,
    slot_texto,
    congregacao="",
    motivo_oracao="",
):
    contatos = _contatos_pastorais(slug)
    if not contatos:
        atualizar_notificacao_pedido_oracao(slug, id_pedido, "Sem contatos pastorais configurados.")
        return "Pedido salvo. Configure o WhatsApp do pastor em Minha Conta para notificar automaticamente.", []

    mensagem = _montar_mensagem(
        slug, membro, tipo_pedido, pedido, privacidade, deseja_visita,
        slot_texto, congregacao=congregacao, motivo_oracao=motivo_oracao,
    )
    links = []
    enviados = 0
    falhas = []
    for contato in contatos:
        links.append((contato["nome"], _link_whatsapp(contato["telefone"], mensagem)))
        if _whatsapp_api_configurada():
            ok, detalhe = _enviar_whatsapp_texto_api(contato["telefone"], mensagem)
            if ok:
                enviados += 1
            else:
                falhas.append(f"{contato['nome']}: {detalhe}")

    if _whatsapp_api_configurada():
        status = f"Enviado via API para {enviados}/{len(contatos)} contato(s)."
        if falhas:
            status += " Falhas: " + "; ".join(falhas[:3])
    else:
        status = "WhatsApp Cloud API nao configurada. Links manuais disponiveis no painel interno."
    atualizar_notificacao_pedido_oracao(slug, id_pedido, status)
    return status, links


def _identificar_membro():
    with st.form("form_identificar_membro_oracao"):
        st.markdown("#### Identificacao do membro")
        c1, c2 = st.columns(2)
        slug = c1.text_input("Identificador da igreja", placeholder="ex: ad-serrinha")
        codigo = c2.text_input("Codigo de acesso", type="password")
        c3, c4 = st.columns(2)
        cpf = c3.text_input("CPF", placeholder="Somente numeros")
        nascimento = c4.text_input("Data de nascimento", placeholder="dd/mm/aaaa")
        localizar = st.form_submit_button("Continuar", type="primary")
    if not localizar:
        return None, None

    slug = str(slug or "").strip().lower()
    data_nascimento = str(nascimento or "").strip()
    try:
        if "/" in data_nascimento:
            data_nascimento = dt.datetime.strptime(data_nascimento, "%d/%m/%Y").date().isoformat()
        if not validar_codigo_atualizacao_cadastral(slug, codigo):
            st.error("Codigo de acesso invalido para esta igreja.")
            return None, None
        membro = localizar_cadastro_publico(slug, cpf, data_nascimento)
    except Exception:
        LOGGER.exception("Falha ao identificar membro para pedido de oracao.")
        st.error("Nao foi possivel validar seus dados. Confira as informacoes.")
        return None, None

    if not membro:
        st.error("Cadastro de membro nao localizado.")
        return None, None
    st.session_state["oracao_slug"] = slug
    st.session_state["oracao_membro"] = membro
    return slug, membro


def render_publico():
    st.markdown("## Pedidos de Oracao e Visita Pastoral")
    st.caption(
        "Este espaco e exclusivo para membros. Informe seus dados para registrar "
        "um pedido de oracao ou solicitar uma visita pastoral."
    )

    slug = st.session_state.get("oracao_slug")
    membro = st.session_state.get("oracao_membro")
    if not slug or not isinstance(membro, dict):
        slug, membro = _identificar_membro()
    if not slug or not isinstance(membro, dict):
        return

    st.success(f"Cadastro localizado: {membro.get('nome', '')}")
    if st.button("Usar outro cadastro", key="limpar_membro_oracao"):
        st.session_state.pop("oracao_slug", None)
        st.session_state.pop("oracao_membro", None)
        st.rerun()

    hoje = _hoje()
    fim = hoje + dt.timedelta(days=60)
    horarios = listar_horarios_visita_pastoral(
        slug, data_inicio=hoje.isoformat(), data_fim=fim.isoformat(), somente_disponiveis=True
    )
    op_horarios = {"Sem agendamento agora": None}
    if not horarios.empty:
        for _, row in horarios.iterrows():
            op_horarios[_slot_label(row)] = int(row["id_slot"])

    with st.form("form_pedido_oracao_publico"):
        op_congregacoes = []
        congregacao_membro = str(membro.get("congregacao") or "").strip()
        for item in (congregacao_membro, slug):
            if item and item not in op_congregacoes:
                op_congregacoes.append(item)
        if not op_congregacoes:
            op_congregacoes = [slug]
        congregacao = st.selectbox("Identificador da congregacao", op_congregacoes)

        op_membros = {
            f'Cadastro localizado: {membro.get("nome", "")}': int(membro["id_cadastro"]),
            "Informar nome manualmente": None,
        }
        membro_label = st.selectbox("Nome do membro", list(op_membros.keys()))
        nome_manual = ""
        telefone_manual = ""
        if op_membros[membro_label] is None:
            c_nome, c_tel = st.columns(2)
            nome_manual = c_nome.text_input("Nome do membro")
            telefone_manual = c_tel.text_input("Telefone / WhatsApp", value=str(membro.get("telefone") or ""))

        tipo_pedido = st.selectbox("Tipo de pedido", TIPOS_PEDIDO)
        motivo_oracao = st.text_input("Motivo da oracao", placeholder="Ex.: familia, saude, decisao, trabalho...")
        privacidade = st.selectbox("Privacidade", PRIVACIDADE_OPCOES)
        pedido = st.text_area("Descreva seu pedido", height=180)
        deseja_visita = tipo_pedido == "Solicitacao de visita pastoral" or st.checkbox("Desejo solicitar visita pastoral")
        slot_label = "Sem agendamento agora"
        if deseja_visita:
            if len(op_horarios) == 1:
                st.info("Nao ha horarios pastorais disponiveis no momento. O pedido sera enviado sem agendamento.")
            else:
                slot_label = st.selectbox("Horario disponivel para visita", list(op_horarios.keys()))
        enviar = st.form_submit_button("Enviar pedido", type="primary")

    if enviar:
        try:
            id_slot = op_horarios.get(slot_label)
            id_cadastro = op_membros[membro_label]
            membro_notificacao = dict(membro)
            if id_cadastro is None:
                membro_notificacao["nome"] = nome_manual
                membro_notificacao["telefone"] = telefone_manual
            id_pedido = registrar_pedido_oracao(
                slug,
                id_cadastro,
                pedido,
                tipo_pedido=tipo_pedido,
                confidencial=privacidade == "Pastor",
                deseja_visita=deseja_visita,
                id_slot=id_slot,
                congregacao=congregacao,
                nome_manual=nome_manual,
                telefone_manual=telefone_manual,
                motivo_oracao=motivo_oracao,
                privacidade=privacidade,
            )
            status, _links = _notificar_pastores(
                slug, id_pedido, membro_notificacao, tipo_pedido, pedido, privacidade,
                deseja_visita, slot_label if id_slot else "",
                congregacao=congregacao,
                motivo_oracao=motivo_oracao,
            )
        except Exception as ex:
            LOGGER.exception("Nao foi possivel registrar pedido de oracao.")
            st.error(str(ex))
        else:
            st.success("Pedido registrado com sucesso. A equipe pastoral sera notificada.")
            st.caption(status)


def _render_pedidos(slug):
    c1, c2, c3 = st.columns(3)
    inicio = c1.date_input("Data inicial", value=_hoje() - dt.timedelta(days=30))
    fim = c2.date_input("Data final", value=_hoje())
    status = c3.selectbox("Status", ["Todos"] + STATUS_PEDIDO)
    df = listar_pedidos_oracao(
        slug,
        data_inicio=inicio.isoformat(),
        data_fim=fim.isoformat(),
        status="" if status == "Todos" else status,
    )
    if df.empty:
        st.info("Nenhum pedido encontrado no periodo.")
        return

    st.metric("Pedidos no periodo", len(df))
    st.dataframe(
        df[[
            "id_pedido", "criado_em", "congregacao", "nome_membro", "tipo_pedido",
            "motivo_oracao", "privacidade", "deseja_visita", "data_visita",
            "hora_inicio", "status", "notificacao_status",
        ]],
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Baixar pedidos CSV",
        data=gerar_csv(df),
        file_name="pedidos_oracao.csv",
        mime="text/csv",
    )

    opcoes = {
        f'{int(row["id_pedido"])} - {row["nome_membro"]} - {row["tipo_pedido"]}': row
        for _, row in df.iterrows()
    }
    selecionado = st.selectbox("Abrir pedido", ["Selecione"] + list(opcoes.keys()))
    if selecionado == "Selecione":
        return
    row = opcoes[selecionado]
    st.markdown(f"#### Pedido de {row['nome_membro']}")
    st.caption(
        f"Congregacao: {row.get('congregacao') or '-'} | "
        f"Motivo: {row.get('motivo_oracao') or '-'} | "
        f"Privacidade: {row.get('privacidade') or 'Pastor'}"
    )
    st.info(str(row["pedido"]))
    if int(row.get("deseja_visita", 0) or 0):
        st.caption(
            f"Visita: {_formatar_data(row.get('data_visita'))} "
            f"{row.get('hora_inicio') or ''} - {row.get('hora_fim') or ''} "
            f"{row.get('local') or ''}"
        )
    novo_status = st.selectbox(
        "Atualizar status",
        STATUS_PEDIDO,
        index=STATUS_PEDIDO.index(row["status"]) if row["status"] in STATUS_PEDIDO else 0,
        key=f"status_pedido_{row['id_pedido']}",
    )
    if st.button("Salvar status", key=f"salvar_status_pedido_{row['id_pedido']}", type="primary"):
        atualizar_status_pedido_oracao(slug, int(row["id_pedido"]), novo_status)
        st.success("Status atualizado.")
        st.rerun()


def _render_agenda(slug):
    with st.form("form_agenda_pastoral"):
        st.markdown("#### Novo horario disponivel")
        c1, c2, c3 = st.columns(3)
        data = c1.date_input("Data", value=_hoje())
        hora_inicio = c2.time_input("Inicio", value=dt.time(19, 0))
        hora_fim = c3.time_input("Fim", value=dt.time(20, 0))
        local = st.text_input("Local", placeholder="Gabinete pastoral, residencia, igreja...")
        observacoes = st.text_area("Observacoes")
        if st.form_submit_button("Adicionar horario", type="primary"):
            try:
                salvar_horario_visita_pastoral(
                    slug,
                    data.isoformat(),
                    hora_inicio.strftime("%H:%M"),
                    hora_fim.strftime("%H:%M"),
                    local,
                    observacoes,
                    True,
                )
            except Exception as ex:
                st.error(str(ex))
            else:
                st.success("Horario cadastrado.")
                st.rerun()

    agenda = listar_horarios_visita_pastoral(
        slug,
        data_inicio=(_hoje() - dt.timedelta(days=7)).isoformat(),
        data_fim=(_hoje() + dt.timedelta(days=90)).isoformat(),
    )
    if agenda.empty:
        st.info("Nenhum horario cadastrado.")
        return
    st.dataframe(agenda, use_container_width=True, hide_index=True)
    opcoes = {
        f'{int(row["id_slot"])} - {_slot_label(row)}': int(row["id_slot"])
        for _, row in agenda.iterrows()
    }
    excluir = st.selectbox("Excluir/inativar horario", ["Selecione"] + list(opcoes.keys()))
    if excluir != "Selecione" and st.button("Excluir horario selecionado", type="secondary"):
        removido = excluir_horario_visita_pastoral(slug, opcoes[excluir])
        if removido:
            st.success("Horario removido.")
        else:
            st.warning("Horario ja vinculado a pedido. Ele foi apenas inativado.")
        st.rerun()


def render():
    st.subheader("Pedidos de Oracao")
    slug = slug_da_sessao()
    if not slug:
        st.error("Sessao invalida. Faca login novamente.")
        return
    modo = st.session_state.get("modo", "igreja")
    tabs = st.tabs(["Pedidos", "Agenda pastoral"] if modo != "pastor_auxiliar" else ["Pedidos"])
    with tabs[0]:
        _render_pedidos(slug)
    if modo != "pastor_auxiliar" and len(tabs) > 1:
        with tabs[1]:
            _render_agenda(slug)
