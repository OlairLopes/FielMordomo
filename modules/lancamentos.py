import datetime
import base64
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from data.models import Lancamento
from data.repository import (
    carregar_cadastros, carregar_lancamentos,
    inserir_lancamento, atualizar_lancamento, excluir_lancamento,
    obter_logo_igreja,
)
from utils.helpers import (
    formatar_moeda, preparar_df, obter_ativos, montar_opcoes,
    encontrar_chave, confirmar_exclusao, gerar_csv,
    slug_da_sessao, solicitar_autorizacao,
)

CATEGORIAS_ENTRADA = ["Campanha", "Dizimo", "Missao", "Oferta"]


def _ck(sufixo): return f"df_{sufixo}_{slug_da_sessao()}"
def _invalida():
    for s in ("cad", "lanc"):
        st.session_state.pop(_ck(s), None)
def _get_cad(slug):
    k = _ck("cad")
    if k not in st.session_state:
        st.session_state[k] = carregar_cadastros(slug)
    return st.session_state[k]
def _get_lanc(slug):
    k = _ck("lanc")
    if k not in st.session_state:
        st.session_state[k] = carregar_lancamentos(slug)
    return st.session_state[k]


def _logo_base64(slug: str) -> str | None:
    """Retorna o logo da igreja em base64 para embutir no HTML."""
    resultado = obter_logo_igreja(slug)
    if resultado:
        dados, ext = resultado
        b64 = base64.b64encode(dados).decode()
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        return f"data:{mime};base64,{b64}"
    return None


def _gerar_html_comprovante(lancamento: dict, igreja: dict, slug: str) -> str:
    """Gera HTML completo do comprovante para impressao."""

    nome_igreja  = igreja.get("nome", "Igreja")
    data_fmt     = pd.to_datetime(lancamento.get("data"), errors="coerce")
    data_str     = data_fmt.strftime("%d/%m/%Y") if pd.notna(data_fmt) else "-"
    data_emissao = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    id_lanc      = lancamento.get("id_lancamento", "-")
    tipo         = lancamento.get("tipo", "-")
    categoria    = lancamento.get("categoria", "-")
    descricao    = lancamento.get("descricao", "-") or "-"
    valor        = formatar_moeda(lancamento.get("valor", 0))
    nome_vinc    = lancamento.get("nome_cadastro", "") or "Nao vinculado"
    tipo_vinc    = lancamento.get("tipo_cadastro", "") or ""

    cor_tipo = "#1D9E75" if tipo == "Entrada" else "#D85A30"

    logo_b64 = _logo_base64(slug)
    if logo_b64:
        logo_tag = f'<img src="{logo_b64}" style="max-height:80px;max-width:200px;object-fit:contain"/>'
    else:
        logo_tag = f'<span style="font-size:1.4rem;font-weight:700;color:#1D9E75">FielMordomo</span>'

    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <title>Comprovante #{id_lanc}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: Arial, sans-serif;
      font-size: 13px;
      color: #1a1a1a;
      background: #fff;
      padding: 20px;
    }}
    .comprovante {{
      max-width: 680px;
      margin: 0 auto;
      border: 1px solid #ddd;
      border-radius: 8px;
      overflow: hidden;
    }}
    .cabecalho {{
      background: #f8f9fa;
      border-bottom: 2px solid #1D9E75;
      padding: 20px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .cabecalho-dir {{
      text-align: right;
    }}
    .cabecalho-dir h1 {{
      font-size: 1rem;
      font-weight: 700;
      color: #1a1a1a;
      margin-bottom: 4px;
    }}
    .cabecalho-dir p {{
      font-size: 0.75rem;
      color: #666;
    }}
    .titulo-comprovante {{
      background: {cor_tipo};
      color: white;
      text-align: center;
      padding: 10px;
      font-size: 0.85rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .corpo {{
      padding: 24px;
    }}
    .numero {{
      text-align: center;
      font-size: 0.75rem;
      color: #888;
      margin-bottom: 20px;
    }}
    .numero span {{
      font-weight: 700;
      color: #1a1a1a;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 20px;
    }}
    table tr {{
      border-bottom: 1px solid #f0f0f0;
    }}
    table tr:last-child {{
      border-bottom: none;
    }}
    table td {{
      padding: 10px 8px;
      vertical-align: top;
    }}
    table td:first-child {{
      width: 38%;
      font-weight: 600;
      color: #555;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    table td:last-child {{
      color: #1a1a1a;
      font-size: 0.9rem;
    }}
    .valor-destaque {{
      font-size: 1.3rem;
      font-weight: 700;
      color: {cor_tipo};
    }}
    .assinatura {{
      margin-top: 30px;
      display: flex;
      gap: 40px;
    }}
    .campo-assinatura {{
      flex: 1;
      text-align: center;
    }}
    .linha-assinatura {{
      border-top: 1px solid #1a1a1a;
      padding-top: 6px;
      margin-top: 48px;
      font-size: 0.75rem;
      color: #555;
    }}
    .rodape {{
      background: #f8f9fa;
      border-top: 1px solid #ddd;
      padding: 12px 24px;
      text-align: center;
      font-size: 0.7rem;
      color: #888;
    }}
    @media print {{
      body {{ padding: 0; }}
      .comprovante {{ border: none; border-radius: 0; }}
      .btn-imprimir {{ display: none !important; }}
    }}
  </style>
</head>
<body>

<div style="text-align:center;margin-bottom:16px">
  <button class="btn-imprimir"
    onclick="window.print()"
    style="background:#1D9E75;color:white;border:none;padding:10px 28px;
           border-radius:6px;font-size:14px;cursor:pointer;font-weight:600">
    Imprimir comprovante
  </button>
</div>

<div class="comprovante">

  <div class="cabecalho">
    <div>{logo_tag}</div>
    <div class="cabecalho-dir">
      <h1>{nome_igreja}</h1>
      <p>Comprovante de lancamento</p>
      <p>Emitido em: {data_emissao}</p>
    </div>
  </div>

  <div class="titulo-comprovante">
    {tipo} — {categoria}
  </div>

  <div class="corpo">
    <p class="numero">Comprovante N° <span>#{id_lanc:04d}</span></p>

    <table>
      <tr>
        <td>Data do lancamento</td>
        <td>{data_str}</td>
      </tr>
      <tr>
        <td>Tipo</td>
        <td>{tipo}</td>
      </tr>
      <tr>
        <td>Categoria</td>
        <td>{categoria}</td>
      </tr>
      <tr>
        <td>Descricao</td>
        <td>{descricao}</td>
      </tr>
      <tr>
        <td>Vinculado a</td>
        <td>{nome_vinc}{f" ({tipo_vinc})" if tipo_vinc else ""}</td>
      </tr>
      <tr>
        <td>Valor</td>
        <td><span class="valor-destaque">{valor}</span></td>
      </tr>
    </table>

    <div class="assinatura">
      <div class="campo-assinatura">
        <div class="linha-assinatura">
          Responsavel pelo lancamento
        </div>
      </div>
      <div class="campo-assinatura">
        <div class="linha-assinatura">
          {nome_vinc if nome_vinc != "Nao vinculado" else "Assinatura"}
        </div>
      </div>
    </div>
  </div>

  <div class="rodape">
    FielMordomo — Sistema de Gestao Financeira para Igrejas &nbsp;|&nbsp;
    Documento gerado em {data_emissao}
  </div>

</div>

<script>
  window.onload = function() {{
    setTimeout(function() {{ window.print(); }}, 800);
  }};
</script>

</body>
</html>
"""
    return html


def render():
    slug    = slug_da_sessao()
    df_cad  = _get_cad(slug)
    df_lanc = _get_lanc(slug)
    membros = obter_ativos(df_cad, "MEMBRO")
    fornec  = obter_ativos(df_cad, "FORNECEDOR")
    igreja  = st.session_state.get("igreja", {})

    # ── Novo lancamento ──────────────────────────────────────────────────
    with st.expander("Novo lancamento", expanded=False):
        with st.form("form_lanc", clear_on_submit=True):
            data_l = st.date_input("Data", value=datetime.date.today(), format="DD/MM/YYYY")
            tipo   = st.selectbox("Tipo", ["Entrada", "Saida"])
            cat    = st.selectbox("Categoria", CATEGORIAS_ENTRADA) if tipo == "Entrada" else "Despesa"
            if tipo == "Saida":
                st.text_input("Categoria", value="Despesa", disabled=True)

            vinc_pad = "Membro" if (tipo == "Entrada" and cat == "Dizimo") else "Fornecedor" if tipo == "Saida" else "Nenhum"
            vincular = st.selectbox("Vincular a", ["Nenhum", "Membro", "Fornecedor"],
                                    index=["Nenhum", "Membro", "Fornecedor"].index(vinc_pad))

            id_cad, nome_cad, tipo_cad = None, "", ""
            if vincular == "Membro" and not membros.empty:
                opc = montar_opcoes(membros)
                esc = st.selectbox("Membro", list(opc.keys()))
                l = opc[esc]; id_cad, nome_cad, tipo_cad = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
            elif vincular == "Fornecedor" and not fornec.empty:
                opc = montar_opcoes(fornec)
                esc = st.selectbox("Fornecedor", list(opc.keys()))
                l = opc[esc]; id_cad, nome_cad, tipo_cad = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]

            desc  = st.text_input("Descricao")
            valor = st.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f")

            if st.form_submit_button("Salvar lancamento", type="primary"):
                lanc = Lancamento(data=data_l, tipo=tipo, categoria=cat,
                                  valor=valor, descricao=de
