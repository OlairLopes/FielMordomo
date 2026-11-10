import datetime
import html

import streamlit as st

from data.repository import (
    buscar_igreja_por_slug, carregar_cadastros, confirmar_contribuicao_online,
    criar_contribuicao_online, listar_contribuicoes_online, obter_pix_igreja,
    rejeitar_contribuicao_online, salvar_pix_igreja,
)
from modules.pix_brcode import gerar_payload_pix, gerar_qr_png
from utils.helpers import formatar_moeda, slug_da_sessao

URL_BASE_APP = "https://fielmordomo.streamlit.app"
TIPOS = ("Dizimo", "Oferta", "Missao", "Campanha")
ROTULOS_TIPO = {"Dizimo": "Dízimo", "Oferta": "Oferta", "Missao": "Missão", "Campanha": "Campanha"}


def _rotulo(tipo):
    return ROTULOS_TIPO.get(tipo, tipo)


def _formatar_data_hora(iso):
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return iso or ""
VALOR_MINIMO = 1.0
VALOR_MAXIMO = 100_000.0


def _chave_gerado(slug):
    return f"contribuicao_gerada_{slug}"


def pagina_publica(slug):
    """Pagina publica de contribuicao (?contribuir=<slug>), sem login."""
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        st.error("Igreja não encontrada.")
        return

    pix = obter_pix_igreja(slug)
    if not pix["chave"]:
        st.info("A contribuição online ainda não está configurada nesta igreja.")
        return

    st.title(igreja["nome"])
    st.caption("Contribua por Pix. Escolha o tipo e o valor e pague pelo aplicativo do seu banco.")

    with st.form(f"form_contribuicao_{slug}", clear_on_submit=False):
        tipo = st.selectbox("Tipo de contribuição", TIPOS, format_func=_rotulo)
        valor = st.number_input(
            "Valor (R$)", min_value=VALOR_MINIMO, max_value=VALOR_MAXIMO,
            value=50.0, step=5.0, format="%.2f",
        )
        nome = st.text_input("Seu nome (opcional)", max_chars=80)
        contato = st.text_input("E-mail ou telefone para contato (opcional)", max_chars=120)
        enviar = st.form_submit_button("Gerar Pix", type="primary")

    chave_sessao = _chave_gerado(slug)
    if enviar:
        try:
            id_contribuicao = criar_contribuicao_online(slug, nome, tipo, valor, contato)
            payload = gerar_payload_pix(
                pix["chave"], pix["beneficiario"], pix["cidade"],
                valor=valor, txid=f"CO{id_contribuicao:08d}",
            )
        except ValueError as ex:
            st.error(str(ex))
            st.session_state.pop(chave_sessao, None)
            return
        st.session_state[chave_sessao] = {
            "payload": payload,
            "valor": valor,
            "tipo": tipo,
            "id": id_contribuicao,
        }

    gerado = st.session_state.get(chave_sessao)
    if not gerado:
        return

    st.success(
        f"Contribuição de {formatar_moeda(gerado['valor'])} ({_rotulo(gerado['tipo'])}) registrada. "
        "Pague pelo QR Code ou pelo copia e cola abaixo."
    )
    st.image(gerar_qr_png(gerado["payload"]), width=260)
    st.code(gerado["payload"], language=None)
    st.caption(
        "Depois do pagamento a tesouraria confere o recebimento. "
        f"Referência da contribuição: #{gerado['id']}."
    )


def _url_contribuicao(slug):
    return f"{URL_BASE_APP}/?contribuir={slug}"


def _secao_configuracao(slug):
    pix = obter_pix_igreja(slug)
    with st.expander("Configurar chave Pix da igreja", expanded=not pix["chave"]):
        with st.form(f"form_pix_{slug}"):
            chave = st.text_input("Chave Pix", value=pix["chave"],
                                  help="CPF, CNPJ, e-mail, telefone ou chave aleatoria.")
            beneficiario = st.text_input("Nome do beneficiário (até 25 caracteres)",
                                         value=pix["beneficiario"], max_chars=25)
            cidade = st.text_input("Cidade (até 15 caracteres)",
                                   value=pix["cidade"], max_chars=15)
            if st.form_submit_button("Salvar"):
                try:
                    salvar_pix_igreja(slug, chave, beneficiario, cidade)
                    st.success("Chave Pix salva.")
                except ValueError as ex:
                    st.error(str(ex))


def _secao_divulgacao(slug):
    url = _url_contribuicao(slug)
    st.markdown("**Link para divulgar**")
    st.code(url, language=None)
    st.image(gerar_qr_png(url), width=200)


def _membros_ativos(slug):
    df = carregar_cadastros(slug)
    if df.empty:
        return []
    mascara = (df["tipo_cadastro"].astype(str).str.upper() == "MEMBRO") & (
        df["situacao"].astype(str).str.upper() == "ATIVO"
    )
    return [(int(r["id_cadastro"]), r["nome"]) for _, r in df[mascara].iterrows()]


def _card_pendente(slug, item, membros):
    id_c = item["id_contribuicao"]
    st.markdown(
        f"**#{id_c} · {html.escape(_rotulo(item['tipo']))} · {formatar_moeda(item['valor'])}**  \n"
        f"{html.escape(item['nome_doador'] or 'Sem nome')} · "
        f"{html.escape(item['contato'] or 'sem contato')} · {_formatar_data_hora(item['criado_em'])}"
    )
    with st.form(f"form_conf_{slug}_{id_c}"):
        col1, col2 = st.columns(2)
        data_recebimento = col1.date_input("Data do recebimento",
                                           value=datetime.date.today(), key=f"dt_{id_c}")
        categoria = col2.selectbox("Categoria", TIPOS, index=TIPOS.index(item["tipo"]),
                                   format_func=_rotulo, key=f"cat_{id_c}")
        id_cadastro = None
        if item["tipo"] == "Dizimo":
            opcoes = [(None, "Selecione o membro...")] + membros
            escolha = st.selectbox("Membro (obrigatório para dízimo)", opcoes,
                                   format_func=lambda o: o[1], key=f"mem_{id_c}")
            id_cadastro = escolha[0]
        col_a, col_b = st.columns(2)
        confirmar = col_a.form_submit_button("Confirmar recebimento", type="primary")
        rejeitar = col_b.form_submit_button("Rejeitar")

    if confirmar:
        try:
            confirmar_contribuicao_online(slug, id_c, data_recebimento, categoria, id_cadastro)
            _invalida_financeiro()
            st.success(f"Contribuição #{id_c} lançada no financeiro.")
            st.rerun()
        except ValueError as ex:
            st.error(str(ex))
    elif rejeitar:
        try:
            rejeitar_contribuicao_online(slug, id_c)
            st.rerun()
        except ValueError as ex:
            st.error(str(ex))


def _invalida_financeiro():
    for chave in [k for k in st.session_state.keys() if k.startswith("df_")]:
        st.session_state.pop(chave, None)


def render():
    slug = slug_da_sessao()
    if not slug:
        st.error("Sessão inválida. Faça login novamente.")
        return

    st.subheader("Contribuições online")
    _secao_configuracao(slug)
    _secao_divulgacao(slug)

    st.divider()
    pendentes = listar_contribuicoes_online(slug, status="pendente")
    st.markdown(f"**Pendentes de conferência: {len(pendentes)}**")
    st.caption("Confira o recebimento no extrato do banco antes de confirmar.")

    membros = _membros_ativos(slug)
    if not pendentes:
        st.info("Nenhuma contribuição aguardando conferência.")
    for item in pendentes:
        _card_pendente(slug, item, membros)
        st.divider()

    with st.expander("Histórico"):
        historico = listar_contribuicoes_online(slug)
        if historico:
            st.dataframe(
                [
                    {
                        "Ref.": h["id_contribuicao"],
                        "Data": _formatar_data_hora(h["criado_em"]),
                        "Doador": h["nome_doador"],
                        "Tipo": _rotulo(h["tipo"]),
                        "Valor": formatar_moeda(h["valor"]),
                        "Status": h["status"],
                    }
                    for h in historico
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("Ainda não há contribuições online.")
