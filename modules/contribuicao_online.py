import datetime
import html

import streamlit as st

from data.repository import (
    anexar_comprovante_online, buscar_igreja_por_slug, carregar_cadastros,
    COMPROVANTE_EXTENSOES, confirmar_contribuicao_online, criar_contribuicao_online,
    listar_contribuicoes_online, obter_comprovante_online, obter_pix_igreja,
    PIX_QR_EXTENSOES, obter_pix_qr_igreja, remover_pix_qr_igreja,
    rejeitar_contribuicao_online, salvar_pix_igreja, salvar_pix_qr_igreja,
)
from modules.institucional import render_barra_publica
from modules.lancamentos import CATEGORIAS_ENTRADA
from modules.pix_brcode import gerar_payload_pix, gerar_qr_png
from utils.helpers import formatar_moeda, slug_da_sessao

URL_BASE_APP = "https://fielmordomo.com.br"
TIPOS = list(CATEGORIAS_ENTRADA)


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
    render_barra_publica()
    igreja = buscar_igreja_por_slug(slug)
    if not igreja:
        st.error("Igreja não encontrada.")
        return

    pix = obter_pix_igreja(slug)
    qr_igreja = obter_pix_qr_igreja(slug)
    if not pix["chave"] and not qr_igreja:
        st.info("A contribuição online ainda não está configurada nesta igreja.")
        return

    st.title(igreja["nome"])
    st.caption("Contribua por Pix. Escolha o tipo e o valor e pague pelo aplicativo do seu banco.")
    if qr_igreja:
        st.markdown("**QR Code da igreja**")
        st.image(qr_igreja, width=260)
        st.caption("Escaneie com o app do seu banco e informe o valor da contribuição.")
    if not pix["chave"]:
        return

    with st.form(f"form_contribuicao_{slug}", clear_on_submit=False):
        tipo = st.selectbox("Tipo de contribuição", TIPOS)
        valor = st.number_input(
            "Valor (R$)", min_value=VALOR_MINIMO, max_value=VALOR_MAXIMO,
            value=50.0, step=5.0, format="%.2f",
        )
        nome = st.text_input("Seu nome (obrigatório)", max_chars=80)
        contato = st.text_input("Telefone com DDD (obrigatório)", max_chars=20, placeholder="(00) 00000-0000")
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
        else:
            st.session_state[chave_sessao] = {
                "payload": payload,
                "valor": valor,
                "tipo": tipo,
                "id": id_contribuicao,
            }
            # Preenche a seção "Já paguei" com a referência e o telefone recém-informados.
            st.session_state[f"comp_ref_{slug}"] = str(id_contribuicao)
            st.session_state[f"comp_tel_{slug}"] = contato

    gerado = st.session_state.get(chave_sessao)
    if not gerado:
        # Sem Pix gerado nesta sessão: o envio "Já paguei" é a única forma de anexar o comprovante.
        _secao_comprovante_posterior(slug)
        return

    st.success(
        f"Contribuição de {formatar_moeda(gerado['valor'])} ({gerado['tipo']}) registrada. "
        "Pague pelo QR Code ou pelo copia e cola abaixo."
    )
    st.image(gerar_qr_png(gerado["payload"]), width=260)
    st.code(gerado["payload"], language=None)
    st.caption(
        "Depois do pagamento a tesouraria confere o recebimento. "
        f"Referência da contribuição: #{gerado['id']}."
    )
    st.markdown("**Envie o comprovante do Pix**")
    _envio_comprovante(slug, gerado["id"], contato=None, chave=f"gerado_{gerado['id']}")


def _envio_comprovante(slug, id_contribuicao, contato, chave):
    arquivo = st.file_uploader(
        "Comprovante do Pix (PNG, JPG, WEBP ou PDF, até 5 MB)",
        type=list(COMPROVANTE_EXTENSOES), key=f"comprovante_upload_{chave}",
    )
    if arquivo is not None and st.button("Enviar comprovante", key=f"comprovante_enviar_{chave}"):
        try:
            anexar_comprovante_online(
                slug, id_contribuicao, arquivo.getvalue(),
                arquivo.name.rsplit(".", 1)[-1].lower(), arquivo.name, contato,
            )
            st.success("Comprovante recebido. Obrigado! Ele fica guardado por 30 dias.")
        except ValueError as ex:
            st.error(str(ex))


def _secao_comprovante_posterior(slug):
    with st.expander("Já paguei: enviar comprovante"):
        st.caption(
            "Informe o número da referência e o telefone usados na contribuição. "
            "O comprovante fica guardado por 30 dias."
        )
        referencia = st.text_input("Número da referência (#)", max_chars=10, key=f"comp_ref_{slug}")
        telefone = st.text_input("Telefone com DDD usado na contribuição", max_chars=20,
                                 key=f"comp_tel_{slug}")
        arquivo = st.file_uploader(
            "Comprovante do Pix (PNG, JPG, WEBP ou PDF, até 5 MB)",
            type=list(COMPROVANTE_EXTENSOES), key=f"comp_arquivo_{slug}",
        )
        if st.button("Enviar comprovante", key=f"comp_enviar_{slug}"):
            if arquivo is None:
                st.error("Escolha o arquivo do comprovante.")
            elif not referencia.strip().lstrip("#").isdigit():
                st.error("Informe o número da referência.")
            else:
                try:
                    anexar_comprovante_online(
                        slug, int(referencia.strip().lstrip("#")), arquivo.getvalue(),
                        arquivo.name.rsplit(".", 1)[-1].lower(), arquivo.name, telefone,
                    )
                    st.success("Comprovante recebido. Obrigado!")
                except ValueError as ex:
                    st.error(str(ex))


def _url_contribuicao(slug):
    return f"{URL_BASE_APP}/?contribuir={slug}"


def _secao_configuracao(slug):
    pix = obter_pix_igreja(slug)
    with st.expander("Chave Pix da igreja", expanded=True):
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

        st.markdown("**QR Code da igreja**")
        qr_atual = obter_pix_qr_igreja(slug)
        if qr_atual:
            st.image(qr_atual, width=180)
        arquivo = st.file_uploader(
            "Enviar imagem do QR Code (PNG, JPG ou WEBP, até 2 MB)",
            type=list(PIX_QR_EXTENSOES), key=f"pix_qr_upload_{slug}",
        )
        col_salvar, col_remover = st.columns(2)
        if arquivo is not None and col_salvar.button("Salvar QR Code", key=f"pix_qr_salvar_{slug}"):
            try:
                salvar_pix_qr_igreja(slug, arquivo.getvalue(), arquivo.name.rsplit(".", 1)[-1].lower())
                st.success("QR Code salvo.")
                st.rerun()
            except ValueError as ex:
                st.error(str(ex))
        if qr_atual and col_remover.button("Remover QR Code", key=f"pix_qr_remover_{slug}"):
            remover_pix_qr_igreja(slug)
            st.rerun()


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


def _mostrar_comprovante(slug, item):
    if not item["tem_comprovante"]:
        st.warning("Sem comprovante anexado. Peça ao doador o envio antes de confirmar.")
        return
    comprovante = obter_comprovante_online(slug, item["id_contribuicao"])
    if comprovante is None:
        st.warning("Comprovante expirado (guardado por 30 dias).")
    elif comprovante["nome"].lower().endswith(".pdf"):
        st.download_button("Baixar comprovante (PDF)", comprovante["dados"],
                           file_name=comprovante["nome"], key=f"comp_baixar_{item['id_contribuicao']}")
    else:
        st.image(comprovante["dados"], width=260)


def _card_pendente(slug, item, membros):
    id_c = item["id_contribuicao"]
    st.markdown(
        f"**#{id_c} · {html.escape(item['tipo'])} · {formatar_moeda(item['valor'])}**  \n"
        f"{html.escape(item['nome_doador'] or 'Sem nome')} · "
        f"{html.escape(item['contato'] or 'sem contato')} · {_formatar_data_hora(item['criado_em'])}"
    )
    _mostrar_comprovante(slug, item)
    with st.form(f"form_conf_{slug}_{id_c}"):
        col1, col2 = st.columns(2)
        data_recebimento = col1.date_input("Data do recebimento",
                                           value=datetime.date.today(), key=f"dt_{id_c}")
        categoria = col2.selectbox("Categoria", TIPOS, index=TIPOS.index(item["tipo"]),
                                   key=f"cat_{id_c}")
        opcoes = [(None, "Nenhum (obrigatório para dízimo)")] + membros
        escolha = st.selectbox("Membro", opcoes, format_func=lambda o: o[1], key=f"mem_{id_c}")
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
                        "Tipo": h["tipo"],
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
