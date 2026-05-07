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
                                  valor=valor, descricao=desc,
                                  id_cadastro=id_cad, nome_cadastro=nome_cad, tipo_cadastro=tipo_cad)
                erros = lanc.validar()
                if erros:
                    for e in erros: st.error(e)
                else:
                    inserir_lancamento(slug, lanc)
                    _invalida()
                    st.toast("Lancamento salvo!")
                    st.rerun()

    # ── Tabela ────────────────────────────────────────────────────────────
    total = len(df_lanc)
    with st.expander(f"Ver lancamentos ({total} registros)", expanded=False):
        if df_lanc.empty:
            st.info("Nenhum lancamento ainda.")
        else:
            st.dataframe(preparar_df(df_lanc), use_container_width=True)
            st.download_button("Exportar CSV", gerar_csv(preparar_df(df_lanc)),
                               "lancamentos.csv", "text/csv")

    # ── Imprimir comprovante ──────────────────────────────────────────────
    with st.expander("Imprimir comprovante", expanded=False):
        if df_lanc.empty:
            st.info("Nenhum lancamento ainda.")
        else:
            df_p = df_lanc.copy()
            df_p["data_fmt"] = pd.to_datetime(df_p["data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
            df_p["rotulo"] = df_p.apply(
                lambda r: (
                    f'{int(r["id_lancamento"])} | {r["data_fmt"]} | '
                    f'{r["tipo"]} | {r["categoria"]} | '
                    f'{r["nome_cadastro"] or "Sem vinculo"} | '
                    f'{formatar_moeda(r["valor"])}'
                ),
                axis=1,
            )

            rotulo_imp = st.selectbox(
                "Selecione o lancamento para imprimir",
                df_p["rotulo"].tolist(),
                key="sel_imp",
            )
            sel_imp = df_p[df_p["rotulo"] == rotulo_imp].iloc[0]

            if st.button("Gerar comprovante", type="primary", key="btn_imprimir"):
                html = _gerar_html_comprovante(dict(sel_imp), igreja, slug)
                components.html(html, height=700, scrolling=True)

    # ── Editar / Excluir ──────────────────────────────────────────────────
    with st.expander("Editar ou excluir lancamento", expanded=False):
        if df_lanc.empty:
            st.info("Nenhum lancamento ainda.")
            return

        df_e = df_lanc.copy()
        df_e["data_fmt"] = pd.to_datetime(df_e["data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
        df_e["rotulo"] = df_e.apply(
            lambda r: (
                f'{int(r["id_lancamento"])} | {r["data_fmt"]} | '
                f'{r["tipo"]} | {r["categoria"]} | '
                f'{r["nome_cadastro"] or "Sem vinculo"} | '
                f'{formatar_moeda(r["valor"])}'
            ),
            axis=1,
        )

        rotulo  = st.selectbox("Selecione o lancamento", df_e["rotulo"].tolist(), key="sel_lanc_edit")
        sel     = df_e[df_e["rotulo"] == rotulo].iloc[0]
        id_lanc = int(sel["id_lancamento"])

        data_base = pd.to_datetime(sel["data"], errors="coerce")
        data_edit = st.date_input("Data",
                                  value=data_base.date() if pd.notna(data_base) else datetime.date.today(),
                                  format="DD/MM/YYYY", key="edit_data")

        tipo_opc = ["Entrada", "Saida"]
        tipo_e   = st.selectbox("Tipo", tipo_opc,
                                index=tipo_opc.index(sel["tipo"]) if sel["tipo"] in tipo_opc else 0,
                                key="edit_tipo")
        cat_e    = st.selectbox("Categoria", CATEGORIAS_ENTRADA,
                                index=CATEGORIAS_ENTRADA.index(sel["categoria"]) if sel["categoria"] in CATEGORIAS_ENTRADA else 0,
                                key="edit_cat") if tipo_e == "Entrada" else "Despesa"
        if tipo_e == "Saida":
            st.text_input("Categoria", value="Despesa", disabled=True, key="edit_cat_d")

        vinc_str   = str(sel["tipo_cadastro"]).strip().upper()
        vinc_pad_e = ("Membro" if (tipo_e == "Entrada" and cat_e == "Dizimo")
                      else "Fornecedor" if vinc_str == "FORNECEDOR"
                      else "Membro" if vinc_str == "MEMBRO"
                      else "Nenhum")
        vincular_e = st.selectbox("Vincular a", ["Nenhum", "Membro", "Fornecedor"],
                                  index=["Nenhum", "Membro", "Fornecedor"].index(vinc_pad_e),
                                  key="edit_vinc")

        id_e, nome_e, tipo_e2 = None, "", ""
        if vincular_e == "Membro" and not membros.empty:
            opc    = montar_opcoes(membros)
            chave  = encontrar_chave(opc, sel["id_cadastro"])
            chaves = list(opc.keys())
            esc    = st.selectbox("Membro", chaves,
                                  index=chaves.index(chave) if chave in chaves else 0,
                                  key="edit_mem")
            l = opc[esc]; id_e, nome_e, tipo_e2 = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
        elif vincular_e == "Fornecedor" and not fornec.empty:
            opc    = montar_opcoes(fornec)
            chave  = encontrar_chave(opc, sel["id_cadastro"])
            chaves = list(opc.keys())
            esc    = st.selectbox("Fornecedor", chaves,
                                  index=chaves.index(chave) if chave in chaves else 0,
                                  key="edit_forn")
            l = opc[esc]; id_e, nome_e, tipo_e2 = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
        else:
            st.text_input("Nome", value="", disabled=True, key="edit_nome_vazio")

        desc_e  = st.text_input("Descricao", value=str(sel["descricao"]), key="edit_desc")
        valor_e = st.number_input("Valor (R$)", min_value=0.0, value=float(sel["valor"]),
                                  step=0.01, format="%.2f", key="edit_val")

        st.divider()
        c1, c2 = st.columns(2)

        with c1:
            st.caption("Editar lancamento")
            if solicitar_autorizacao("salvar_lanc", "editar"):
                lanc = Lancamento(data=data_edit, tipo=tipo_e, categoria=cat_e,
                                  valor=valor_e, descricao=desc_e,
                                  id_cadastro=id_e, nome_cadastro=nome_e,
                                  tipo_cadastro=tipo_e2, id_lancamento=id_lanc)
                erros = lanc.validar()
                if erros:
                    for e in erros: st.error(e)
                else:
                    atualizar_lancamento(slug, lanc)
                    _invalida()
                    st.toast("Lancamento alterado!")
                    st.rerun()

        with c2:
            st.caption("Excluir lancamento")
            if solicitar_autorizacao("excluir_lanc", "excluir"):
                if confirmar_exclusao("del_lanc_final", "Confirmar exclusao"):
                    excluir_lancamento(slug, id_lanc)
                    _invalida()
                    st.toast("Excluido.")
                    st.rerun()
