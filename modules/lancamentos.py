import datetime
import base64
import html
import logging
import re
import urllib.parse

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

from data.models import Lancamento
from data.repository import (
    carregar_cadastros, carregar_lancamentos,
    inserir_lancamento, inserir_lancamentos_lote, atualizar_lancamento, excluir_lancamento,
    obter_logo_igreja, listar_subcategorias_despesa, obter_config_igreja,
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
TIPOS_VINCULO = ["Nenhum", "Membro", "Fornecedor"]

LOGGER = logging.getLogger(__name__)
API_VERSION_RE = re.compile(r"^v\d+\.\d+$")
PHONE_NUMBER_ID_RE = re.compile(r"^\d+$")


def _rotulo_vinculo(tipo):
    return "Fornecedor (empresa)" if tipo == "Fornecedor" else tipo


def _ck(sufixo, slug):
    return f"df_{sufixo}_{slug}"


def _sk(sufixo, slug):
    return f"{sufixo}_{slug}"


def _html(valor):
    return html.escape(str(valor if valor is not None else ""), quote=True)


def _invalida():
    keys_to_remove = [k for k in list(st.session_state.keys()) if k.startswith("df_")]
    for k in keys_to_remove:
        st.session_state.pop(k, None)


def _get_cad(slug):
    k = _ck("cad", slug)
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


def _limpar_tel(tel):
    return "".join(c for c in str(tel) if c.isdigit())


def _normalizar_tel_brasil(tel):
    tel_limpo = _limpar_tel(tel)

    if not tel_limpo:
        return ""

    while tel_limpo.startswith("0"):
        tel_limpo = tel_limpo[1:]

    if len(tel_limpo) in (10, 11):
        tel_limpo = "55" + tel_limpo

    return tel_limpo if len(tel_limpo) in (12, 13) and tel_limpo.startswith("55") else ""


def _assinatura_igreja(slug):
    return obter_config_igreja(slug, "nome_assinatura_comprovante", "Responsavel")


def _valor_texto(valor):
    return "" if pd.isna(valor) else str(valor or "")


def _link_whatsapp(tel, mensagem):
    tel_limpo = _normalizar_tel_brasil(tel)

    if not tel_limpo:
        return ""

    msg_enc = urllib.parse.quote(mensagem)
    return f"https://wa.me/{tel_limpo}?text={msg_enc}"


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
        return False, "Telefone invalido ou vazio."

    if not cfg["access_token"] or not cfg["phone_number_id"]:
        return False, "WhatsApp Cloud API nao configurada no st.secrets."

    url = (
        f"https://graph.facebook.com/"
        f"{cfg['api_version']}/{cfg['phone_number_id']}/messages"
    )

    headers = {
        "Authorization": f"Bearer {cfg['access_token']}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": mensagem,
        },
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=25)

        if 200 <= resp.status_code < 300:
            return True, "Comprovante enviado com sucesso."

        LOGGER.warning("WhatsApp Cloud API retornou HTTP %s: %s", resp.status_code, resp.text[:1000])
        return False, f"Nao foi possivel enviar o comprovante (HTTP {resp.status_code})."

    except requests.RequestException:
        LOGGER.exception("Falha ao enviar comprovante pela WhatsApp Cloud API.")
        return False, "Falha de comunicacao com o WhatsApp. Tente novamente."


def _telefone_do_lancamento(df_cad, lancamento):
    id_cadastro = lancamento.get("id_cadastro")

    if pd.isna(id_cadastro):
        return ""

    try:
        id_cadastro = int(id_cadastro)
    except Exception:
        return ""

    if df_cad.empty or "id_cadastro" not in df_cad.columns:
        return ""

    ids = pd.to_numeric(df_cad["id_cadastro"], errors="coerce")
    linha = df_cad[ids == id_cadastro]

    if linha.empty or "telefone" not in linha.columns:
        return ""

    return str(linha.iloc[0].get("telefone", "") or "")


def _montar_mensagem_comprovante(lancamento, igreja, slug):
    nome_igreja = igreja.get("nome", "Igreja")
    data_fmt = pd.to_datetime(lancamento.get("data"), errors="coerce")
    data_str = data_fmt.strftime("%d/%m/%Y") if pd.notna(data_fmt) else "-"

    id_lanc = lancamento.get("id_lancamento", 0)
    tipo = lancamento.get("tipo", "-")
    categoria = lancamento.get("categoria", "-")
    subcategoria = lancamento.get("subcategoria", "") or ""
    descricao = lancamento.get("descricao", "") or "-"
    forma_pag = lancamento.get("forma_pagamento", "Dinheiro") or "Dinheiro"
    valor = formatar_moeda(lancamento.get("valor", 0))
    nome_vinc = lancamento.get("nome_cadastro", "") or "Nao vinculado"

    linhas = [
        f"Comprovante de lancamento - {nome_igreja}",
        "",
        f"Cupom: #{str(id_lanc).zfill(6)}",
        f"Data: {data_str}",
        f"Tipo: {tipo}",
        f"Categoria: {categoria}",
    ]

    if subcategoria:
        linhas.append(f"Subcategoria: {subcategoria}")

    linhas.extend([
        f"Vinculado: {nome_vinc}",
        f"Descricao: {descricao}",
        f"Pagamento: {forma_pag}",
        f"Valor: {valor}",
        "",
        "Mensagem enviada pelo sistema FielMordomo.",
        _assinatura_igreja(slug),
    ])

    return "\n".join(linhas)


def _render_whatsapp_comprovante(df_cad, lancamento, igreja, slug, key_prefix):
    telefone = _telefone_do_lancamento(df_cad, lancamento)
    mensagem = _montar_mensagem_comprovante(lancamento, igreja, slug)
    link = _link_whatsapp(telefone, mensagem)

    if link:
        st.markdown(
        f'<a href="{_html(link)}" target="_blank" rel="noopener noreferrer" '
            f'style="display:inline-block;background:#25D366;color:white;'
            f'padding:8px 16px;border-radius:6px;text-decoration:none;'
            f'font-weight:600;margin-top:10px;margin-bottom:8px">'
            f'Enviar comprovante pelo WhatsApp</a>',
            unsafe_allow_html=True,
        )
    else:
        st.warning("Este lancamento nao possui telefone vinculado.")

    if _whatsapp_api_configurada():
        if st.button(
            "Enviar pela WhatsApp Cloud API",
            key=f"{key_prefix}_enviar_cupom_api",
            use_container_width=True,
        ):
            ok, detalhe = _enviar_whatsapp_texto_api(telefone, mensagem)
            if ok:
                st.success(detalhe)
            else:
                st.error(detalhe)


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
    if logo_b64:
        logo_html = (
            '<div style="text-align:center;margin-bottom:6px">'
            f'<img src="{logo_b64}" style="max-height:60px;max-width:160px;object-fit:contain"/>'
            '</div>'
        )

    sep = "-" * 40
    sep2 = "=" * 40
    vinc_str = nome_vinc + (f" ({tipo_vinc})" if tipo_vinc else "")
    nome_assinatura = _html(_assinatura_igreja(slug))

    subcat_html = ""
    if subcategoria:
        subcat_html = (
            '<div class="linha"><span class="label">Subcategoria</span>'
            f'<span class="valor">{subcategoria}</span></div>'
        )

    descricao_html = descricao if descricao else "-"

    return f"""
<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"/>
<title>Cupom #{str(id_lanc).zfill(6)}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #f0f0f0; display: flex; justify-content: center; padding: 20px; }}
.cupom {{ background: white; width: 320px; padding: 16px 14px;
         font-family: 'Courier New', Courier, monospace; font-size: 12px; color: #111;
         box-shadow: 2px 2px 8px rgba(0,0,0,0.15); }}
.centro {{ text-align: center; }}
.nome-igreja {{ font-size: 14px; font-weight: bold; text-align: center;
               text-transform: uppercase; letter-spacing: 0.05em; margin: 6px 0 2px; }}
.subtitulo {{ text-align: center; font-size: 10px; color: #555; margin-bottom: 4px; }}
.sep {{ color: #aaa; margin: 6px 0; letter-spacing: -1px; }}
.sep2 {{ color: #333; margin: 6px 0; letter-spacing: -1px; }}
.linha {{ display: flex; justify-content: space-between; margin: 3px 0; font-size: 11px; }}
.linha .label {{ color: #555; }}
.linha .valor {{ font-weight: 600; text-align: right; max-width: 55%; word-break: break-word; }}
.tipo-badge {{ text-align: center; font-size: 13px; font-weight: bold;
              letter-spacing: 0.1em; padding: 4px 0; margin: 4px 0; }}
.valor-total {{ text-align: center; font-size: 20px; font-weight: bold;
               margin: 8px 0 4px; letter-spacing: 0.02em; }}
.cupom-num {{ text-align: center; font-size: 10px; color: #777; margin-bottom: 4px; }}
.assinatura-bloco {{ margin-top: 12px; display: flex; justify-content: center; gap: 20px; }}
.assinatura-item {{ flex: 1; max-width: 45%; }}
.assinatura-linha {{ border-top: 1px dashed #aaa; margin-top: 28px; padding-top: 4px;
                    text-align: center; font-size: 10px; color: #555;
                    width: 80%; margin-left: auto; margin-right: auto; }}
.rodape {{ text-align: center; font-size: 9px; color: #888; margin-top: 8px; }}
@media print {{
  body {{ background: white; padding: 0; }}
  .cupom {{ box-shadow: none; width: 100%; max-width: 320px; margin: 0 auto; }}
  .btn-imprimir {{ display: none !important; }}
}}
</style></head><body>

<div style="text-align:center;margin-bottom:12px">
  <button class="btn-imprimir" onclick="window.print()"
    style="background:#0F6E56;color:white;border:none;padding:8px 24px;
           border-radius:6px;font-size:13px;cursor:pointer;font-weight:600">
    Imprimir cupom
  </button>
</div>

<div class="cupom">
  {logo_html}
  <div class="nome-igreja">{nome_igreja}</div>
  <div class="subtitulo">Comprovante de Lancamento</div>
  <div class="sep centro">{sep}</div>
  <div class="cupom-num">CUPOM N: {str(id_lanc).zfill(6)}</div>
  <div class="cupom-num">Emitido: {data_emissao}</div>
  <div class="sep centro">{sep}</div>
  <div class="tipo-badge">*** {tipo.upper()} - {categoria.upper()} ***</div>
  <div class="sep centro">{sep}</div>
  <div class="linha"><span class="label">Data</span><span class="valor">{data_str}</span></div>
  <div class="linha"><span class="label">Categoria</span><span class="valor">{categoria}</span></div>
  {subcat_html}
  <div class="linha"><span class="label">Vinculado</span><span class="valor">{vinc_str}</span></div>
  <div class="linha"><span class="label">Descricao</span><span class="valor">{descricao_html}</span></div>
  <div class="linha"><span class="label">Pagamento</span><span class="valor">{forma_pag}</span></div>
  <div class="sep2 centro">{sep2}</div>
  <div class="subtitulo">VALOR TOTAL</div>
  <div class="valor-total">{valor}</div>
  <div class="sep2 centro">{sep2}</div>
  <div class="assinatura-bloco">
    <div class="assinatura-item"><div class="assinatura-linha">Tesoureiro</div></div>
    <div class="assinatura-item"><div class="assinatura-linha">{nome_assinatura}</div></div>
  </div>
  <div class="sep centro">{sep}</div>
  <div class="rodape">FielMordomo - Sistema de Gestao Financeira</div>
  <div class="rodape">para Igrejas</div>
</div>

<script>window.onload = function() {{ setTimeout(function(){{ window.print(); }}, 800); }};</script>
</body></html>"""


def _gerar_html_comprovante_lote(itens, igreja, slug, data_str, vinc_str,
                                  forma_pag, numero_lote):
    nome_igreja = _html(igreja.get("nome", "Igreja"))
    data_emissao = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    total = sum(item["valor"] for item in itens)

    logo_b64 = _logo_base64(slug)
    logo_html = ""
    if logo_b64:
        logo_html = (
            '<div style="text-align:center;margin-bottom:6px">'
            f'<img src="{logo_b64}" style="max-height:60px;max-width:160px;object-fit:contain"/>'
            '</div>'
        )

    sep = "-" * 40
    sep2 = "=" * 40
    nome_assinatura = _html(_assinatura_igreja(slug))

    itens_html = ""
    for it in itens:
        rotulo = _html(it["categoria"])
        if it.get("subcategoria"):
            rotulo += " (" + _html(it["subcategoria"]) + ")"
        desc_extra = " - " + _html(it["descricao"]) if it.get("descricao") else ""
        itens_html += (
            '<div class="linha">'
            f'<span class="label">{rotulo}{desc_extra}</span>'
            f'<span class="valor">{_html(formatar_moeda(it["valor"]))}</span>'
            '</div>'
        )

    return f"""
<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"/>
<title>Cupom Lote #{_html(numero_lote)}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #f0f0f0; display: flex; justify-content: center; padding: 20px; }}
.cupom {{ background: white; width: 340px; padding: 16px 14px;
         font-family: 'Courier New', Courier, monospace; font-size: 12px; color: #111;
         box-shadow: 2px 2px 8px rgba(0,0,0,0.15); }}
.centro {{ text-align: center; }}
.nome-igreja {{ font-size: 14px; font-weight: bold; text-align: center;
               text-transform: uppercase; letter-spacing: 0.05em; margin: 6px 0 2px; }}
.subtitulo {{ text-align: center; font-size: 10px; color: #555; margin-bottom: 4px; }}
.sep {{ color: #aaa; margin: 6px 0; letter-spacing: -1px; }}
.sep2 {{ color: #333; margin: 6px 0; letter-spacing: -1px; }}
.linha {{ display: flex; justify-content: space-between; margin: 3px 0; font-size: 11px; }}
.linha .label {{ color: #555; flex: 1; padding-right: 8px; }}
.linha .valor {{ font-weight: 600; text-align: right; white-space: nowrap; }}
.tipo-badge {{ text-align: center; font-size: 12px; font-weight: bold;
              letter-spacing: 0.1em; padding: 4px 0; margin: 4px 0; }}
.valor-total {{ text-align: center; font-size: 20px; font-weight: bold;
               margin: 8px 0 4px; letter-spacing: 0.02em; }}
.cupom-num {{ text-align: center; font-size: 10px; color: #777; margin-bottom: 4px; }}
.info-bloco {{ font-size: 11px; margin: 4px 0; }}
.assinatura-bloco {{ margin-top: 12px; display: flex; justify-content: center; gap: 20px; }}
.assinatura-item {{ flex: 1; max-width: 45%; }}
.assinatura-linha {{ border-top: 1px dashed #aaa; margin-top: 28px; padding-top: 4px;
                    text-align: center; font-size: 10px; color: #555;
                    width: 80%; margin-left: auto; margin-right: auto; }}
.rodape {{ text-align: center; font-size: 9px; color: #888; margin-top: 8px; }}
@media print {{
  body {{ background: white; padding: 0; }}
  .cupom {{ box-shadow: none; width: 100%; max-width: 340px; margin: 0 auto; }}
  .btn-imprimir {{ display: none !important; }}
}}
</style></head><body>

<div style="text-align:center;margin-bottom:12px">
  <button class="btn-imprimir" onclick="window.print()"
    style="background:#0F6E56;color:white;border:none;padding:8px 24px;
           border-radius:6px;font-size:13px;cursor:pointer;font-weight:600">
    Imprimir cupom
  </button>
</div>

<div class="cupom">
  {logo_html}
  <div class="nome-igreja">{nome_igreja}</div>
  <div class="subtitulo">Comprovante Consolidado</div>
  <div class="sep centro">{sep}</div>
  <div class="cupom-num">LOTE: {_html(numero_lote)}</div>
  <div class="cupom-num">Emitido: {data_emissao}</div>
  <div class="sep centro">{sep}</div>
  <div class="info-bloco">
    <div class="linha"><span class="label">Data</span><span class="valor">{_html(data_str)}</span></div>
    <div class="linha"><span class="label">Vinculado</span><span class="valor">{_html(vinc_str)}</span></div>
    <div class="linha"><span class="label">Pagamento</span><span class="valor">{_html(forma_pag)}</span></div>
    <div class="linha"><span class="label">Itens</span><span class="valor">{len(itens)}</span></div>
  </div>
  <div class="sep centro">{sep}</div>
  <div class="tipo-badge">*** DETALHAMENTO ***</div>
  <div class="sep centro">{sep}</div>
  {itens_html}
  <div class="sep2 centro">{sep2}</div>
  <div class="subtitulo">VALOR TOTAL</div>
  <div class="valor-total">{_html(formatar_moeda(total))}</div>
  <div class="sep2 centro">{sep2}</div>
  <div class="assinatura-bloco">
    <div class="assinatura-item"><div class="assinatura-linha">Tesoureiro</div></div>
    <div class="assinatura-item"><div class="assinatura-linha">{nome_assinatura}</div></div>
  </div>
  <div class="sep centro">{sep}</div>
  <div class="rodape">FielMordomo - Sistema de Gestao Financeira</div>
</div>

<script>window.onload = function() {{ setTimeout(function(){{ window.print(); }}, 800); }};</script>
</body></html>"""


def _gerar_html_fechamento_caixa(lancamentos, igreja, slug, data_inicio, data_fim,
                                 forma_pagamento="Todas"):
    nome_igreja = _html(igreja.get("nome", "Igreja"))
    data_emissao = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    periodo = (
        data_inicio.strftime("%d/%m/%Y")
        if data_inicio == data_fim
        else f"{data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"
    )

    df = lancamentos.copy()
    if df.empty:
        entradas = saidas = saldo = 0.0
        qtd = 0
    else:
        df["tipo_norm"] = df["tipo"].fillna("").astype(str).str.upper().str.strip()
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
        entradas = float(df[df["tipo_norm"] == "ENTRADA"]["valor"].sum())
        saidas = float(df[df["tipo_norm"] == "SAIDA"]["valor"].sum())
        saldo = entradas - saidas
        qtd = len(df)

    logo_b64 = _logo_base64(slug)
    logo_html = ""
    if logo_b64:
        logo_html = (
            '<div style="text-align:center;margin-bottom:6px">'
            f'<img src="{logo_b64}" style="max-height:60px;max-width:160px;object-fit:contain"/>'
            '</div>'
        )

    sep = "-" * 42
    sep2 = "=" * 42

    resumo_pag_html = ""
    if not df.empty and "forma_pagamento" in df.columns:
        resumo_pag = (
            df.assign(forma_pagamento=df["forma_pagamento"].fillna("").astype(str).str.strip().replace("", "Nao informado"))
            .groupby("forma_pagamento", as_index=False)["valor"]
            .sum()
            .sort_values("valor", ascending=False)
        )
        for _, row in resumo_pag.iterrows():
            resumo_pag_html += (
                '<div class="linha">'
                f'<span class="label">{_html(row["forma_pagamento"])}</span>'
                f'<span class="valor">{_html(formatar_moeda(row["valor"]))}</span>'
                '</div>'
            )
    else:
        resumo_pag_html = '<div class="linha"><span class="label">Sem movimento</span><span class="valor">R$ 0,00</span></div>'

    itens_html = ""
    if df.empty:
        itens_html = '<div class="vazio">Sem lancamentos para os filtros selecionados.</div>'
    else:
        ordenado = df.copy()
        ordenado["data_dt"] = pd.to_datetime(ordenado["data"], errors="coerce")
        ordenado = ordenado.sort_values(["data_dt", "id_lancamento"], na_position="last")
        for _, row in ordenado.iterrows():
            data_row = row.get("data_dt")
            data_txt = data_row.strftime("%d/%m") if pd.notna(data_row) else "--/--"
            id_txt = str(int(row["id_lancamento"])).zfill(6) if pd.notna(row.get("id_lancamento")) else "------"
            tipo = _html(row.get("tipo", "-"))
            categoria = _html(row.get("categoria", "-"))
            subcategoria = _html(row.get("subcategoria", "") or "")
            nome_vinc = _html(row.get("nome_cadastro", "") or "Sem vinculo")
            tipo_vinc = _html(row.get("tipo_cadastro", "") or "")
            vinculo = nome_vinc + (f" ({tipo_vinc})" if tipo_vinc else "")
            forma = _html(row.get("forma_pagamento", "") or "-")
            valor = _html(formatar_moeda(row.get("valor", 0)))
            desc = _html(row.get("descricao", "") or "")
            complemento = f" / {subcategoria}" if subcategoria else ""
            if desc:
                complemento += f" - {desc}"
            itens_html += (
                '<div class="item">'
                f'<div><strong>#{id_txt}</strong> {data_txt} - {tipo}</div>'
                f'<div>{categoria}{complemento}</div>'
                f'<div class="vinculo">Vinculado: {vinculo}</div>'
                f'<div class="linha"><span class="label">{forma}</span><span class="valor">{valor}</span></div>'
                '</div>'
            )

    responsavel = _html(_assinatura_igreja(slug))
    return f"""
<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"/>
<title>Fechamento de Caixa - 2a Via</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #f0f0f0; display: flex; justify-content: center; padding: 20px; }}
.cupom {{ background: white; width: 360px; padding: 16px 14px;
         font-family: 'Courier New', Courier, monospace; font-size: 12px; color: #111;
         box-shadow: 2px 2px 8px rgba(0,0,0,0.15); }}
.centro {{ text-align: center; }}
.nome-igreja {{ font-size: 14px; font-weight: bold; text-align: center;
               text-transform: uppercase; letter-spacing: 0.05em; margin: 6px 0 2px; }}
.subtitulo {{ text-align: center; font-size: 10px; color: #555; margin-bottom: 4px; }}
.sep {{ color: #aaa; margin: 6px 0; letter-spacing: -1px; }}
.sep2 {{ color: #333; margin: 6px 0; letter-spacing: -1px; }}
.badge {{ text-align: center; font-size: 13px; font-weight: bold;
          letter-spacing: 0.08em; padding: 4px 0; margin: 4px 0; }}
.linha {{ display: flex; justify-content: space-between; gap: 8px; margin: 3px 0; font-size: 11px; }}
.linha .label {{ color: #555; }}
.linha .valor {{ font-weight: 700; text-align: right; }}
.valor-total {{ text-align: center; font-size: 20px; font-weight: bold; margin: 8px 0 4px; }}
.item {{ border-top: 1px dashed #bbb; padding: 6px 0; font-size: 10px; }}
.item strong {{ font-size: 10px; }}
.vinculo {{ color: #333; font-size: 10px; font-weight: 700; margin-top: 2px; word-break: break-word; }}
.vazio {{ text-align: center; color: #666; font-size: 10px; padding: 10px 0; }}
.assinatura-bloco {{ margin-top: 12px; display: flex; justify-content: center; gap: 18px; }}
.assinatura-item {{ flex: 1; max-width: 46%; }}
.assinatura-linha {{ border-top: 1px dashed #aaa; margin-top: 28px; padding-top: 4px;
                    text-align: center; font-size: 10px; color: #555; }}
.rodape {{ text-align: center; font-size: 9px; color: #888; margin-top: 8px; }}
@media print {{
  body {{ background: white; padding: 0; }}
  .cupom {{ box-shadow: none; width: 100%; max-width: 360px; margin: 0 auto; }}
  .btn-imprimir {{ display: none !important; }}
}}
</style></head><body>

<div style="text-align:center;margin-bottom:12px">
  <button class="btn-imprimir" onclick="window.print()"
    style="background:#0F6E56;color:white;border:none;padding:8px 24px;
           border-radius:6px;font-size:13px;cursor:pointer;font-weight:600">
    Imprimir 2a via
  </button>
</div>

<div class="cupom">
  {logo_html}
  <div class="nome-igreja">{nome_igreja}</div>
  <div class="subtitulo">Fechamento de Caixa</div>
  <div class="badge">*** 2a VIA ***</div>
  <div class="sep centro">{sep}</div>
  <div class="linha"><span class="label">Periodo</span><span class="valor">{_html(periodo)}</span></div>
  <div class="linha"><span class="label">Filtro pagamento</span><span class="valor">{_html(forma_pagamento)}</span></div>
  <div class="linha"><span class="label">Emitido</span><span class="valor">{_html(data_emissao)}</span></div>
  <div class="linha"><span class="label">Lancamentos</span><span class="valor">{qtd}</span></div>
  <div class="sep2 centro">{sep2}</div>
  <div class="linha"><span class="label">Entradas</span><span class="valor">{_html(formatar_moeda(entradas))}</span></div>
  <div class="linha"><span class="label">Saidas</span><span class="valor">{_html(formatar_moeda(saidas))}</span></div>
  <div class="subtitulo">SALDO DO FECHAMENTO</div>
  <div class="valor-total">{_html(formatar_moeda(saldo))}</div>
  <div class="sep2 centro">{sep2}</div>
  <div class="badge">FORMAS DE PAGAMENTO</div>
  {resumo_pag_html}
  <div class="sep centro">{sep}</div>
  <div class="badge">DETALHAMENTO</div>
  {itens_html}
  <div class="sep centro">{sep}</div>
  <div class="assinatura-bloco">
    <div class="assinatura-item"><div class="assinatura-linha">Tesoureiro</div></div>
    <div class="assinatura-item"><div class="assinatura-linha">{responsavel}</div></div>
  </div>
  <div class="rodape">FielMordomo - Sistema de Gestao Financeira para Igrejas</div>
</div>

<script>window.onload = function() {{ setTimeout(function(){{ window.print(); }}, 800); }};</script>
</body></html>"""


def render():
    slug = slug_da_sessao()
    df_cad = _get_cad(slug)
    df_lanc = _get_lanc(slug)
    membros = obter_ativos(df_cad, "MEMBRO")
    fornec = obter_ativos(df_cad, "FORNECEDOR")
    igreja = st.session_state.get("igreja", {})
    plano_igreja = igreja.get("plano", "basico")

    # Contador para forcar recriacao dos widgets do "Novo lancamento" apos salvar.
    # Cada vez que um lancamento e salvo, o contador incrementa e todas as keys
    # mudam (nl_data_0 -> nl_data_1), o que faz o Streamlit criar widgets novos
    # do zero, com valores padrao (vazios). Essa e a forma confiavel de "limpar"
    # campos no Streamlit, especialmente para number_input com value=None.
    nl_counter_key = _sk("nl_counter", slug)
    lote_itens_key = _sk("lote_itens", slug)
    lote_comprovante_key = _sk("lote_comprovante_html", slug)
    if nl_counter_key not in st.session_state:
        st.session_state[nl_counter_key] = 0

    cnt = st.session_state[nl_counter_key]

    with st.expander("Novo lancamento", expanded=False):
        data_l = st.date_input("Data", value=datetime.date.today(),
                               format="DD/MM/YYYY", key=f"nl_data_{cnt}")
        tipo = st.selectbox("Tipo", ["Entrada", "Saida"], key=f"nl_tipo_{cnt}")

        subcategoria_nl = ""

        if tipo == "Entrada":
            cat = st.selectbox("Categoria", CATEGORIAS_ENTRADA, key=f"nl_cat_{cnt}")
        else:
            cat = "Despesa"
            st.text_input("Categoria", value="Despesa", disabled=True, key=f"nl_cat_d_{cnt}")

            subcategorias = listar_subcategorias_despesa()
            if subcategorias:
                subcategoria_nl = st.selectbox(
                    "Subcategoria",
                    [""] + subcategorias,
                    key=f"nl_subcat_{cnt}",
                    help="Selecione a categoria detalhada da despesa.",
                )
            else:
                st.caption(
                    "⚠️ Nenhuma subcategoria de despesa cadastrada. "
                    "Peca ao administrador para adicionar."
                )

        if tipo == "Entrada" and cat == "Dizimo":
            vinc_pad = "Membro"
        elif tipo == "Saida":
            vinc_pad = "Fornecedor"
        else:
            vinc_pad = "Nenhum"

        vincular = st.selectbox(
            "Vincular a", TIPOS_VINCULO,
            index=TIPOS_VINCULO.index(vinc_pad),
            format_func=_rotulo_vinculo,
            key=f"nl_vincular_{cnt}",
        )

        id_cad, nome_cad, tipo_cad = None, "", ""

        if vincular == "Membro":
            if membros.empty:
                st.warning("Nenhum membro ativo cadastrado.")
            else:
                opc = montar_opcoes(membros)
                esc = st.selectbox("Membro", list(opc.keys()), key=f"nl_membro_{cnt}")
                l = opc[esc]
                id_cad, nome_cad, tipo_cad = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
        elif vincular == "Fornecedor":
            if fornec.empty:
                st.warning("Nenhum fornecedor ativo cadastrado.")
            else:
                opc = montar_opcoes(fornec)
                esc = st.selectbox("Fornecedor (empresa)", list(opc.keys()), key=f"nl_fornecedor_{cnt}")
                l = opc[esc]
                id_cad, nome_cad, tipo_cad = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]

        desc = st.text_input("Descricao", key=f"nl_desc_{cnt}")
        forma_pag = st.selectbox("Forma de pagamento", FORMAS_PAGAMENTO, key=f"nl_forma_pag_{cnt}")
        valor = st.number_input(
            "Valor (R$)",
            min_value=0.0,
            value=None,
            step=0.01,
            format="%.2f",
            placeholder="0,00",
            key=f"nl_valor_{cnt}",
        )

        if st.button("Salvar lancamento", type="primary", key=f"nl_salvar_{cnt}"):
            lanc = Lancamento(
                data=data_l, tipo=tipo, categoria=cat,
                valor=valor if valor is not None else 0.0,
                descricao=desc, forma_pagamento=forma_pag,
                subcategoria=subcategoria_nl,
                id_cadastro=id_cad, nome_cadastro=nome_cad, tipo_cadastro=tipo_cad,
            )
            erros = lanc.validar()
            if vincular == "Membro" and membros.empty:
                erros.append("Nenhum membro ativo disponivel.")
            if vincular == "Fornecedor" and fornec.empty:
                erros.append("Nenhum fornecedor ativo disponivel.")
            if valor is None or valor <= 0:
                erros.append("Informe um valor maior que zero.")
            if erros:
                for e in erros:
                    st.error(e)
            else:
                inserir_lancamento(slug, lanc)
                _invalida()
                # Incrementa contador para forcar recriacao dos widgets (limpa campos)
                st.session_state[nl_counter_key] += 1
                st.toast("Lancamento salvo!")
                st.rerun()

    if tem_lancamento_lote(plano_igreja):
        with st.expander("Lancamento em lote (multiplos itens)", expanded=False):
            st.caption("Lance varios itens (dizimo + oferta + missao etc) "
                       "compartilhando data, membro/fornecedor e forma de pagamento.")

            if lote_itens_key not in st.session_state:
                st.session_state[lote_itens_key] = []

            st.markdown("**Dados compartilhados**")
            data_lote = st.date_input("Data", value=datetime.date.today(),
                                       format="DD/MM/YYYY", key="lote_data")
            tipo_lote = st.selectbox(
                "Tipo", ["Entrada", "Saida"], key=_sk("lote_tipo", slug),
                disabled=bool(st.session_state[lote_itens_key]),
                help="Limpe os itens para alterar o tipo do lote.",
            )

            vinc_pad_l = "Membro" if tipo_lote == "Entrada" else "Fornecedor"
            vincular_lote = st.selectbox(
                "Vincular a", TIPOS_VINCULO,
                index=TIPOS_VINCULO.index(vinc_pad_l),
                format_func=_rotulo_vinculo,
                key="lote_vincular",
            )

            id_cad_l, nome_cad_l, tipo_cad_l = None, "", ""

            if vincular_lote == "Membro":
                if membros.empty:
                    st.warning("Nenhum membro ativo cadastrado.")
                else:
                    opc = montar_opcoes(membros)
                    esc = st.selectbox("Membro", list(opc.keys()), key="lote_membro")
                    l = opc[esc]
                    id_cad_l, nome_cad_l, tipo_cad_l = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
            elif vincular_lote == "Fornecedor":
                if fornec.empty:
                    st.warning("Nenhum fornecedor ativo cadastrado.")
                else:
                    opc = montar_opcoes(fornec)
                    esc = st.selectbox("Fornecedor (empresa)", list(opc.keys()), key="lote_fornecedor")
                    l = opc[esc]
                    id_cad_l, nome_cad_l, tipo_cad_l = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]

            forma_pag_lote = st.selectbox("Forma de pagamento", FORMAS_PAGAMENTO, key="lote_forma_pag")

            st.divider()
            st.markdown("**Adicionar item**")

            subcategoria_lote_item = ""

            if tipo_lote == "Entrada":
                cat_lote_item = st.selectbox("Categoria", CATEGORIAS_ENTRADA, key="lote_cat_item")
            else:
                cat_lote_item = "Despesa"
                st.text_input("Categoria", value="Despesa", disabled=True, key="lote_cat_d_item")

                subcategorias_lote = listar_subcategorias_despesa()
                if subcategorias_lote:
                    subcategoria_lote_item = st.selectbox(
                        "Subcategoria",
                        [""] + subcategorias_lote,
                        key="lote_subcat_item",
                    )

            desc_lote_item = st.text_input("Descricao", key="lote_desc_item")
            valor_lote_item = st.number_input("Valor (R$)", min_value=0.0,
                                              step=0.01, format="%.2f", key="lote_valor_item")

            if st.button("Adicionar item ao lote", key="lote_add_item"):
                if valor_lote_item <= 0:
                    st.error("Informe um valor maior que zero.")
                else:
                    st.session_state[lote_itens_key].append({
                        "tipo": tipo_lote,
                        "categoria": cat_lote_item,
                        "subcategoria": subcategoria_lote_item,
                        "descricao": desc_lote_item,
                        "valor": float(valor_lote_item),
                    })
                    st.toast("Item adicionado!")
                    st.rerun()

            if st.session_state[lote_itens_key]:
                st.divider()
                st.markdown("**Itens do lote**")

                total_lote = sum(it["valor"] for it in st.session_state[lote_itens_key])

                for i, item in enumerate(st.session_state[lote_itens_key]):
                    col1, col2, col3, col4 = st.columns([3, 4, 2, 1])
                    with col1:
                        rotulo_item = item["categoria"]
                        if item.get("subcategoria"):
                            rotulo_item += f" / {item['subcategoria']}"
                        st.write(f"**{rotulo_item}**")
                    with col2:
                        st.write(item["descricao"] or "—")
                    with col3:
                        st.write(formatar_moeda(item["valor"]))
                    with col4:
                        if st.button("X", key=f"lote_del_{i}", help="Remover item"):
                            st.session_state[lote_itens_key].pop(i)
                            st.rerun()

                st.markdown(f"### Total: {formatar_moeda(total_lote)}")
                st.caption(f"{len(st.session_state[lote_itens_key])} item(ns) no lote")

                st.divider()
                c_salvar, c_limpar = st.columns(2)

                with c_salvar:
                    if st.button("Salvar todos os lancamentos", type="primary", key="lote_salvar"):
                        if vincular_lote == "Membro" and not id_cad_l:
                            st.error("Selecione um membro para vincular.")
                        elif vincular_lote == "Fornecedor" and not id_cad_l:
                            st.error("Selecione um fornecedor para vincular.")
                        else:
                            itens_salvos = []
                            lancamentos_lote = []
                            erros_lote = []

                            for idx, item in enumerate(st.session_state[lote_itens_key], start=1):
                                lanc = Lancamento(
                                    data=data_lote, tipo=item["tipo"],
                                    categoria=item["categoria"], valor=item["valor"],
                                    descricao=item["descricao"], forma_pagamento=forma_pag_lote,
                                    subcategoria=item.get("subcategoria", ""),
                                    id_cadastro=id_cad_l, nome_cadastro=nome_cad_l,
                                    tipo_cadastro=tipo_cad_l,
                                )
                                erros = lanc.validar()
                                if erros:
                                    erros_lote.extend([f"Item {idx}: {erro}" for erro in erros])
                                else:
                                    lancamentos_lote.append(lanc)
                                    itens_salvos.append(item)

                            if erros_lote:
                                for erro in erros_lote:
                                    st.error(erro)

                            if itens_salvos and not erros_lote:
                                try:
                                    numero_lote, _ = inserir_lancamentos_lote(
                                        slug, lancamentos_lote
                                    )
                                except ValueError as ex:
                                    st.error(str(ex))
                                    return

                                vinc_str = nome_cad_l + (" (" + tipo_cad_l + ")" if tipo_cad_l else "")
                                if not vinc_str:
                                    vinc_str = "Nao vinculado"

                                html_comp = _gerar_html_comprovante_lote(
                                    itens=itens_salvos, igreja=igreja, slug=slug,
                                    data_str=data_lote.strftime("%d/%m/%Y"),
                                    vinc_str=vinc_str, forma_pag=forma_pag_lote,
                                    numero_lote=numero_lote,
                                )
                                st.session_state[lote_comprovante_key] = html_comp
                                st.session_state[lote_itens_key] = []
                                _invalida()
                                st.toast(f"{len(itens_salvos)} lancamentos salvos!")
                                st.rerun()

                with c_limpar:
                    if st.button("Limpar lote", key="lote_limpar"):
                        st.session_state[lote_itens_key] = []
                        st.toast("Lote limpo.")
                        st.rerun()

            if lote_comprovante_key in st.session_state:
                st.divider()
                st.success("Lancamentos salvos! Comprovante consolidado:")
                components.html(st.session_state[lote_comprovante_key], height=700, scrolling=True)
                st.download_button(
                    "Baixar comprovante consolidado",
                    data=st.session_state[lote_comprovante_key],
                    file_name="comprovante_lote.html",
                    mime="text/html",
                    use_container_width=True,
                )
                if st.button("Fechar comprovante", key="lote_fechar_comp"):
                    st.session_state.pop(lote_comprovante_key, None)
                    st.rerun()
    else:
        p_info_l = obter_plano(plano_igreja)
        with st.expander("🔒 Lancamento em lote (apenas Profissional e Premium)", expanded=False):
            st.warning(
                f"O lancamento em lote esta disponivel apenas nos planos "
                f"**Profissional** e **Premium**. Seu plano atual: **{p_info_l['nome']}**."
            )
            st.info(
                f"Faca upgrade para **{proximo_plano(plano_igreja).capitalize()}** "
                f"e ganhe a possibilidade de lancar dizimo + oferta + missao em um unico documento."
            )

    total = len(df_lanc)
    with st.expander(f"Ver lancamentos ({total} registros)", expanded=False):
        if df_lanc.empty:
            st.info("Nenhum lancamento ainda.")
        else:
            st.dataframe(preparar_df(df_lanc), use_container_width=True)
            st.download_button("Exportar CSV", gerar_csv(preparar_df(df_lanc)),
                               "lancamentos.csv", "text/csv")

    with st.expander("Imprimir comprovante", expanded=False):
        if df_lanc.empty:
            st.info("Nenhum lancamento ainda.")
        else:
            df_p = df_lanc.copy()
            df_p["data_fmt"] = pd.to_datetime(df_p["data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
            df_p["rotulo"] = df_p.apply(
                lambda r: (f'{int(r["id_lancamento"])} | {r["data_fmt"]} | '
                           f'{r["tipo"]} | {r["categoria"]} | '
                           f'{r["nome_cadastro"] or "Sem vinculo"} | '
                           f'{formatar_moeda(r["valor"])}'),
                axis=1,
            )
            rotulo_imp = st.selectbox("Selecione o lancamento para imprimir",
                                      df_p["rotulo"].tolist(), key="sel_imp")
            sel_imp = df_p[df_p["rotulo"] == rotulo_imp].iloc[0]
            if st.button("Gerar cupom", type="primary", key="btn_imprimir"):
                html_comp = _gerar_html_comprovante(dict(sel_imp), igreja, slug)
                components.html(html_comp, height=700, scrolling=True)
                id_lanc = int(sel_imp["id_lancamento"])
                _render_whatsapp_comprovante(
                    df_cad=df_cad,
                    lancamento=dict(sel_imp),
                    igreja=igreja,
                    slug=slug,
                    key_prefix=f"cupom_{id_lanc}",
                )
                st.download_button(
                    "Baixar comprovante",
                    data=html_comp,
                    file_name=f"comprovante_{id_lanc}.html",
                    mime="text/html",
                    use_container_width=True,
                )

    with st.expander("2a via do cupom / fechamento de caixa", expanded=False):
        if df_lanc.empty:
            st.info("Nenhum lancamento ainda.")
        else:
            st.caption(
                "Gere uma segunda via consolidada para conferencia e assinatura "
                "do fechamento de caixa."
            )
            df_caixa_base = df_lanc.copy()
            df_caixa_base["data_dt"] = pd.to_datetime(df_caixa_base["data"], errors="coerce")
            datas_validas = df_caixa_base["data_dt"].dropna()
            hoje = datetime.date.today()
            data_min = datas_validas.min().date() if not datas_validas.empty else hoje
            data_max = datas_validas.max().date() if not datas_validas.empty else hoje
            inicio_default = min(max(hoje, data_min), data_max)
            fim_default = inicio_default

            c1, c2, c3 = st.columns(3)
            with c1:
                inicio_caixa = st.date_input(
                    "Data inicial",
                    value=inicio_default,
                    min_value=data_min,
                    max_value=data_max,
                    format="DD/MM/YYYY",
                    key=_sk("caixa_inicio", slug),
                )
            with c2:
                fim_caixa = st.date_input(
                    "Data final",
                    value=fim_default,
                    min_value=data_min,
                    max_value=data_max,
                    format="DD/MM/YYYY",
                    key=_sk("caixa_fim", slug),
                )
            with c3:
                forma_caixa = st.selectbox(
                    "Forma de pagamento",
                    ["Todas"] + FORMAS_PAGAMENTO,
                    key=_sk("caixa_forma", slug),
                )

            if inicio_caixa > fim_caixa:
                st.error("A data inicial nao pode ser posterior a data final.")
            else:
                df_caixa = df_caixa_base[
                    df_caixa_base["data_dt"].between(
                        pd.Timestamp(inicio_caixa),
                        pd.Timestamp(fim_caixa),
                        inclusive="both",
                    )
                ].copy()
                if forma_caixa != "Todas":
                    df_caixa = df_caixa[
                        df_caixa["forma_pagamento"].fillna("").astype(str) == forma_caixa
                    ].copy()

                df_caixa["valor"] = pd.to_numeric(df_caixa["valor"], errors="coerce").fillna(0.0)
                df_caixa["tipo_norm"] = df_caixa["tipo"].fillna("").astype(str).str.upper().str.strip()
                entradas_caixa = float(df_caixa[df_caixa["tipo_norm"] == "ENTRADA"]["valor"].sum())
                saidas_caixa = float(df_caixa[df_caixa["tipo_norm"] == "SAIDA"]["valor"].sum())
                saldo_caixa = entradas_caixa - saidas_caixa

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Entradas", formatar_moeda(entradas_caixa))
                m2.metric("Saidas", formatar_moeda(saidas_caixa))
                m3.metric("Saldo", formatar_moeda(saldo_caixa))
                m4.metric("Lancamentos", len(df_caixa))

                if df_caixa.empty:
                    st.warning("Nenhum lancamento encontrado para os filtros selecionados.")
                else:
                    if st.button(
                        "Gerar 2a via do fechamento",
                        type="primary",
                        key=_sk("caixa_gerar", slug),
                    ):
                        html_caixa = _gerar_html_fechamento_caixa(
                            df_caixa,
                            igreja,
                            slug,
                            inicio_caixa,
                            fim_caixa,
                            forma_pagamento=forma_caixa,
                        )
                        components.html(html_caixa, height=760, scrolling=True)
                        sufixo_periodo = (
                            f"{inicio_caixa:%Y%m%d}"
                            if inicio_caixa == fim_caixa
                            else f"{inicio_caixa:%Y%m%d}_{fim_caixa:%Y%m%d}"
                        )
                        st.download_button(
                            "Baixar 2a via do fechamento",
                            data=html_caixa,
                            file_name=f"fechamento_caixa_2a_via_{sufixo_periodo}.html",
                            mime="text/html",
                            use_container_width=True,
                        )

    with st.expander("Editar ou excluir lancamento", expanded=False):
        if df_lanc.empty:
            st.info("Nenhum lancamento ainda.")
            return

        df_e = df_lanc.copy()
        df_e["data_fmt"] = pd.to_datetime(df_e["data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
        df_e["rotulo"] = df_e.apply(
            lambda r: (f'{int(r["id_lancamento"])} | {r["data_fmt"]} | '
                       f'{r["tipo"]} | {r["categoria"]} | '
                       f'{r["nome_cadastro"] or "Sem vinculo"} | '
                       f'{formatar_moeda(r["valor"])}'),
            axis=1,
        )

        rotulo = st.selectbox("Selecione o lancamento", df_e["rotulo"].tolist(), key="sel_lanc_edit")
        sel = df_e[df_e["rotulo"] == rotulo].iloc[0]
        id_lanc = int(sel["id_lancamento"])

        kp = f"_edit_{id_lanc}_"

        data_base = pd.to_datetime(sel["data"], errors="coerce")
        data_edit = st.date_input("Data",
                                  value=data_base.date() if pd.notna(data_base) else datetime.date.today(),
                                  format="DD/MM/YYYY", key=kp + "data")

        tipo_opc = ["Entrada", "Saida"]
        tipo_e = st.selectbox("Tipo", tipo_opc,
                              index=tipo_opc.index(sel["tipo"]) if sel["tipo"] in tipo_opc else 0,
                              key=kp + "tipo")

        subcategoria_edit = ""

        if tipo_e == "Entrada":
            cat_atual = sel["categoria"] if sel["categoria"] in CATEGORIAS_ENTRADA else CATEGORIAS_ENTRADA[0]
            cat_e = st.selectbox("Categoria", CATEGORIAS_ENTRADA,
                                 index=CATEGORIAS_ENTRADA.index(cat_atual),
                                 key=kp + "cat")
        else:
            cat_e = "Despesa"
            st.text_input("Categoria", value="Despesa", disabled=True, key=kp + "cat_d")

            subcategorias_edit = listar_subcategorias_despesa()
            subcat_atual = _valor_texto(sel.get("subcategoria", "")) if "subcategoria" in sel.index else ""
            if subcategorias_edit:
                opcoes_sub = [""] + subcategorias_edit
                if subcat_atual and subcat_atual not in opcoes_sub:
                    opcoes_sub = [""] + [subcat_atual] + subcategorias_edit
                idx_sub = opcoes_sub.index(subcat_atual) if subcat_atual in opcoes_sub else 0
                subcategoria_edit = st.selectbox(
                    "Subcategoria",
                    opcoes_sub,
                    index=idx_sub,
                    key=kp + "subcat",
                )
            else:
                subcategoria_edit = subcat_atual
                if subcat_atual:
                    st.text_input("Subcategoria", value=subcat_atual, disabled=True, key=kp + "subcat_d")

        vinc_str = _valor_texto(sel["tipo_cadastro"]).strip().upper()
        vinc_pad_e = ("Membro" if (tipo_e == "Entrada" and cat_e == "Dizimo")
                      else "Fornecedor" if vinc_str == "FORNECEDOR"
                      else "Membro" if vinc_str == "MEMBRO"
                      else "Nenhum")
        vincular_e = st.selectbox("Vincular a", TIPOS_VINCULO,
                                  index=TIPOS_VINCULO.index(vinc_pad_e),
                                  format_func=_rotulo_vinculo,
                                  key=kp + "vinc")

        id_e, nome_e, tipo_e2 = None, "", ""
        if vincular_e == "Membro":
            opc, chave = _opcoes_com_registro_atual(
                membros, sel["id_cadastro"], sel["nome_cadastro"], sel["tipo_cadastro"]
            )
            if opc:
                chaves = list(opc.keys())
                esc = st.selectbox("Membro", chaves,
                                   index=chaves.index(chave) if chave in chaves else 0,
                                   key=kp + "mem")
                l = opc[esc]
                id_e, nome_e, tipo_e2 = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
            else:
                st.warning("Nenhum membro ativo cadastrado.")
        elif vincular_e == "Fornecedor":
            opc, chave = _opcoes_com_registro_atual(
                fornec, sel["id_cadastro"], sel["nome_cadastro"], sel["tipo_cadastro"]
            )
            if opc:
                chaves = list(opc.keys())
                esc = st.selectbox("Fornecedor (empresa)", chaves,
                                   index=chaves.index(chave) if chave in chaves else 0,
                                   key=kp + "forn")
                l = opc[esc]
                id_e, nome_e, tipo_e2 = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
            else:
                st.warning("Nenhum fornecedor ativo cadastrado.")
        else:
            st.text_input("Nome", value="", disabled=True, key=kp + "nome_vazio")

        desc_e = st.text_input("Descricao", value=_valor_texto(sel["descricao"]), key=kp + "desc")

        forma_pag_atual = _valor_texto(sel.get("forma_pagamento", "Dinheiro")) if "forma_pagamento" in sel.index else "Dinheiro"
        idx_fp = FORMAS_PAGAMENTO.index(forma_pag_atual) if forma_pag_atual in FORMAS_PAGAMENTO else 1
        forma_pag_e = st.selectbox("Forma de pagamento", FORMAS_PAGAMENTO,
                                   index=idx_fp, key=kp + "forma_pag")

        valor_e = st.number_input("Valor (R$)", min_value=0.0, value=float(sel["valor"]),
                                  step=0.01, format="%.2f", key=kp + "val")

        st.divider()
        c1, c2 = st.columns(2)

        with c1:
            st.caption("Editar lancamento")
            if solicitar_autorizacao("salvar_lanc", "editar"):
                lanc = Lancamento(data=data_edit, tipo=tipo_e, categoria=cat_e,
                                  valor=valor_e, descricao=desc_e,
                                  forma_pagamento=forma_pag_e,
                                  subcategoria=subcategoria_edit,
                                  id_cadastro=id_e, nome_cadastro=nome_e,
                                  tipo_cadastro=tipo_e2, id_lancamento=id_lanc)
                erros = lanc.validar()
                if erros:
                    for e in erros:
                        st.error(e)
                else:
                    atualizar_lancamento(slug, lanc)
                    _invalida()
                    for k in list(st.session_state.keys()):
                        if k.startswith("_auth_") or k.startswith("_edit_"):
                            st.session_state.pop(k, None)
                    st.toast("Lancamento alterado!")
                    st.rerun()

        with c2:
            st.caption("Excluir lancamento")
            if solicitar_autorizacao("excluir_lanc", "excluir"):
                if confirmar_exclusao("del_lanc_final", "Confirmar exclusao"):
                    excluir_lancamento(slug, id_lanc)
                    _invalida()
                    for k in list(st.session_state.keys()):
                        if (k.startswith("_auth_") or k.startswith("_del_")
                            or k.startswith("_edit_") or k == "sel_lanc_edit"):
                            st.session_state.pop(k, None)
                    st.toast("Lancamento excluido!")
                    st.rerun()
