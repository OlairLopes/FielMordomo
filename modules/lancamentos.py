import datetime
import base64
import html

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from data.models import Lancamento
from data.repository import (
    carregar_cadastros, carregar_lancamentos,
    inserir_lancamento, atualizar_lancamento, excluir_lancamento,
    obter_logo_igreja, listar_subcategorias_despesa,
)
from utils.helpers import (
    formatar_moeda, preparar_df, obter_ativos, montar_opcoes,
    encontrar_chave, confirmar_exclusao, gerar_csv,
    slug_da_sessao, solicitar_autorizacao,
)
from utils.planos import tem_lancamento_lote, obter_plano, proximo_plano

CATEGORIAS_ENTRADA = ["Campanha", "Dizimo", "Missao", "Oferta", "Revista EBD"]
FORMAS_PAGAMENTO = [
    "Pix", "Dinheiro", "Transferencia", "Boleto", "Cheque",
    "Cartao Debito", "Cartao Credito",
]

NOME_PASTOR = "Pr. Olair Pereira Lopes"


def _ck(sufixo):
    return f"df_{sufixo}_{slug_da_sessao()}"


def _html(valor):
    return html.escape(str(valor if valor is not None else ""), quote=True)


def _invalida():
    keys_to_remove = [k for k in list(st.session_state.keys()) if k.startswith("df_")]
    for k in keys_to_remove:
        st.session_state.pop(k, None)


def _get_cad(slug):
    k = _ck("cad")
    if k not in st.session_state:
        st.session_state[k] = carregar_cadastros(slug)
    return st.session_state[k]


def _get_lanc(slug):
    return carregar_lancamentos(slug)


def _logo_base64(slug):
    resultado = obter_logo_igreja(slug)
    if resultado:
        dados, ext = resultado
        b64 = base64.b64encode(dados).decode()
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        return f"data:{mime};base64,{b64}"
    return None


def _opcoes_com_registro_atual(df_ativos, id_atual, nome_atual, tipo_atual):
    opcoes = montar_opcoes(df_ativos) if not df_ativos.empty else {}
    chave_atual = encontrar_chave(opcoes, id_atual)

    if chave_atual:
        return opcoes, chave_atual

    if pd.notna(id_atual) and str(nome_atual or "").strip():
        chave_atual = f"{nome_atual} (cadastro atual/inativo)"
        opcoes[chave_atual] = {
            "id_cadastro": int(id_atual),
            "nome": nome_atual,
            "tipo_cadastro": tipo_atual,
        }

    return opcoes, chave_atual


def _gerar_html_comprovante(lancamento, igreja, slug):
    nome_igreja = _html(igreja.get("nome", "Igreja"))
    data_fmt = pd.to_datetime(lancamento.get("data"), errors="coerce")
    data_str = data_fmt.strftime("%d/%m/%Y") if pd.notna(data_fmt) else "-"
    data_emissao = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    id_lanc = lancamento.get("id_lancamento", 0)
    tipo = _html(lancamento.get("tipo", "-"))
    categoria = _html(lancamento.get("categoria", "-"))
    subcategoria = _html(lancamento.get("subcategoria", "") or "")
    descricao = _html(lancamento.get("descricao", "") or "")
    valor = _html(formatar_moeda(lancamento.get("valor", 0)))
    nome_vinc = _html(lancamento.get("nome_cadastro", "") or "Nao vinculado")
    tipo_vinc = _html(lancamento.get("tipo_cadastro", "") or "")
    forma_pag = _html(lancamento.get("forma_pagamento", "Dinheiro") or "Dinheiro")

    logo_b64 = _logo_base64(slug)
    logo_html = ""
