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
FORMAS_PAGAMENTO   = ["Pix", "Dinheiro", "Transferencia", "Boleto", "Cheque", "Cartao Debito", "Cartao Credito"]


def _ck(sufixo): return f"df_{sufixo}_{slug_da_sessao()}"


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


def _logo_base64(slug: str):
    resultado = obter_logo_igreja(slug)
    if resultado:
        dados, ext = resultado
        b64 = base64.b64encode(dados).decode()
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        return f"data:{mime};base64,{b64}"
    return None


def _gerar_html_comprovante(lancamento: dict, igreja: dict, slug: str) -> str:
    nome_igreja  = igreja.get("nome", "Igreja")
    data_fmt     = pd.to_datetime(lancamento.get("data"), errors="coerce")
    data_str     = data_fmt.strftime("%d/%m/%Y") if pd.notna(data_fmt) else "-"
    data_emissao = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    id_lanc      = lancamento.get("id_lancamento", 0)
    tipo         = lancamento.get("tipo", "-")
    categoria    = lancamento.get("categoria", "-")
    descricao    = lancamento.get("descricao", "") or ""
    valor        = formatar_moeda(lancamento.get("valor", 0))
    nome_vinc    = lancamento.get("nome_cadastro", "") or "Nao vinculado"
    tipo_vinc    = lancamento.get("tipo_cadastro", "") or ""
    forma_pag    = lancamento.get("forma_pagamento", "Dinheiro") or "Dinheiro"

    logo_b64 = _logo_base64(slug)
    if logo_b64:
        logo_html = (
            '<div style="text-align:center;margin-bottom:6px">'
            '<img src="' + logo_b64 + '" style="max-height:60px;max-width:160px;'
            'object-fit:contain"/></div>'
        )
    else:
        logo_html = ""

    sep  = "-" * 40
    sep2 = "=" * 40

    vinc_str = nome_vinc
    if tipo_vinc:
        vinc_str = nome_vinc + " (" + tipo_vinc + ")"

    nome_assinatura = ("Pr. " + nome_vinc) if nome_vinc != "Nao vinculado" else "Assinatura"

    html = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <title>Cupom #""" + str(id_lanc).zfill(6) + """</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #f0f0f0; display: flex; justify-content: center; padding: 20px; }
    .cupom { background: white; width: 320px; padding: 16px 14px;
             font-family: 'Courier New', Courier, monospace; font-size: 12px; color: #111;
             box-shadow: 2px 2px 8px rgba(0,0,0,0.15); }
    .cupom::before, .cupom::after { content: ''; display: block; height: 10px;
      background: radial-gradient(circle at 50% 0%, white 6px, #f0f0f0 6px) 0 0 / 16px 10px repeat-x; }
    .cupom::after { background: radial-gradient(circle at 50% 100%, white 6px, #f0f0f0 6px) 0 100% / 16px 10px repeat-x; margin-top: 8px; }
    .centro { text-align: center; }
    .nome-igreja { font-size: 14px; font-weight: bold; text-align: center;
                   text-transform: uppercase; letter-spacing: 0.05em; margin: 6px 0 2px; }
    .subtitulo { text-align: center; font-size: 10px; color: #555; margin-bottom: 4px; }
    .sep  { color: #aaa; margin: 6px 0; letter-spacing: -1px; }
    .sep2 { color: #333; margin: 6px 0; letter-spacing: -1px; }
    .linha { display: flex; justify-content: space-between; margin: 3px 0; font-size: 11px; }
    .linha .label { color: #555; }
    .linha .valor { font-weight: 600; text-align: right; max-width: 55%; word-break: break-word; }
    .tipo-badge { text-align: center; font-size: 13px; font-weight: bold;
                  letter-spacing: 0.1em; padding: 4px 0; margin: 4px 0; }
    .valor-total { text-align: center; font-size: 20px; font-weight: bold;
                   margin: 8px 0 4px; letter-spacing: 0.02em; }
    .cupom-num { text-align: center; font-size: 10px; color: #777; margin-bottom: 4px; }
    .assinatura-bloco { margin-top: 12px; display: flex; justify-content: center; gap: 20px; }
    .assinatura-item { flex: 1; max-width: 45%; }
    .assinatura-linha { border-top: 1px dashed #aaa; margin-top: 28px; padding-top: 4px;
                        text-align: center; font-size: 10px; color: #555;
                        width: 80%; margin-left: auto; margin-right: auto; }
    .rodape { text-align: center; font-size: 9px; color: #888; margin-top: 8px; }
    @media print {
      body { background: white; padding: 0; }
      .cupom { box-shadow: none; width: 100%; max-width: 320px; margin: 0 auto; }
      .btn-imprimir { display: none !important; }
    }
  </style>
</head>
<body>

<div style="text-align:center;margin-bottom:12px">
  <button class="btn-imprimir" onclick="window.print()"
    style="background:#0F6E56;color:white;border:none;padding:8px 24px;
           border-radius:6px;font-size:13px;cursor:pointer;font-weight:600">
    Imprimir cupom
  </button>
</div>

<div class="cupom">
  """ + logo_html + """
  <div class="nome-igreja">""" + nome_igreja + """</div>
  <div class="subtitulo">Comprovante de Lancamento</div>
  <div class="sep centro">""" + sep + """</div>
  <div class="cupom-num">CUPOM N: """ + str(id_lanc).zfill(6) + """</div>
  <div class="cupom-num">Emitido: """ + data_emissao + """</div>
  <div class="sep centro">""" + sep + """</div>
  <div class="tipo-badge">*** """ + tipo.upper() + """ - """ + categoria.upper() + """ ***</div>
  <div class="sep centro">""" + sep + """</div>
  <div class="linha"><span class="label">Data</span><span class="valor">""" + data_str + """</span></div>
  <div class="linha"><span class="label">Categoria</span><span class="valor">""" + categoria + """</span></div>
  <div class="linha"><span class="label">Vinculado</span><span class="valor">""" + vinc_str + """</span></div>
  <div class="linha"><span class="label">Descricao</span><span class="valor">""" + (descricao if descricao else "-") + """</span></div>
  <div class="linha"><span class="label">Pagamento</span><span class="valor">""" + forma_pag + """</span></div>
  <div class="sep2 centro">""" + sep2 + """</div>
  <div class="subtitulo">VALOR TOTAL</div>
  <div class="valor-total">""" + valor + """</div>
  <div class="sep2 centro">""" + sep2 + """</div>
  <div class="assinatura-bloco">
    <div class="assinatura-item"><div class="assinatura-linha">Tesoureiro</div></div>
    <div class="assinatura-item"><div class="assinatura-linha">""" + nome_assinatura + """</div></div>
  </div>
  <div class="sep centro">""" + sep + """</div>
  <div class="rodape">FielMordomo - Sistema de Gestao Financeira</div>
  <div class="rodape">para Igrejas</div>
</div>

<script>
  window.onload = function() {
    setTimeout(function() { window.print(); }, 800);
  };
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
        data_l = st.date_input("Data", value=datetime.date.today(),
                               format="DD/MM/YYYY", key="nl_data")
        tipo   = st.selectbox("Tipo", ["Entrada", "Saida"], key="nl_tipo")

        if tipo == "Entrada":
            cat = st.selectbox("Categoria", CATEGORIAS_ENTRADA, key="nl_cat")
        else:
            cat = "Despesa"
            st.text_input("Categoria", value="Despesa", disabled=True, key="nl_cat_d")

        if tipo == "Entrada" and cat == "Dizimo":
            vinc_pad = "Membro"
        elif tipo == "Saida":
            vinc_pad = "Fornecedor"
        else:
            vinc_pad = "Nenhum"

        vincular = st.selectbox(
            "Vincular a",
            ["Nenhum", "Membro", "Fornecedor"],
            index=["Nenhum", "Membro", "Fornecedor"].index(vinc_pad),
            key="nl_vincular",
        )

        id_cad, nome_cad, tipo_cad = None, "", ""

        if vincular == "Membro":
            if membros.empty:
                st.warning("Nenhum membro ativo cadastrado.")
            else:
                opc = montar_opcoes(membros)
                esc = st.selectbox("Membro", list(opc.keys()), key="nl_membro")
                l = opc[esc]
                id_cad, nome_cad, tipo_cad = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
        elif vincular == "Fornecedor":
            if fornec.empty:
                st.warning("Nenhum fornecedor ativo cadastrado.")
            else:
                opc = montar_opcoes(fornec)
                esc = st.selectbox("Fornecedor", list(opc.keys()), key="nl_fornecedor")
                l = opc[esc]
                id_cad, nome_cad, tipo_cad = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]

        desc      = st.text_input("Descricao", key="nl_desc")
        forma_pag = st.selectbox("Forma de pagamento", FORMAS_PAGAMENTO, key="nl_forma_pag")
        valor     = st.number_input("Valor (R$)", min_value=0.0,
                                    step=0.01, format="%.2f", key="nl_valor")

        if st.button("Salvar lancamento", type="primary", key="nl_salvar"):
            lanc = Lancamento(
                data=data_l, tipo=tipo, categoria=cat,
                valor=valor, descricao=desc, forma_pagamento=forma_pag,
                id_cadastro=id_cad, nome_cadastro=nome_cad, tipo_cadastro=tipo_cad,
            )
            erros = lanc.validar()
            if vincular == "Membro" and membros.empty:
                erros.append("Nenhum membro ativo disponivel.")
            if vincular == "Fornecedor" and fornec.empty:
                erros.append("Nenhum fornecedor ativo disponivel.")
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
            rotulo_imp = st.selectbox("Selecione o lancamento para imprimir",
                                      df_p["rotulo"].tolist(), key="sel_imp")
            sel_imp = df_p[df_p["rotulo"] == rotulo_imp].iloc[0]
            if st.button("Gerar cupom", type="primary", key="btn_imprimir"):
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

        # CHAVE DINAMICA — quando muda a selecao, todos os widgets sao recriados
        kp = f"_edit_{id_lanc}_"

        data_base = pd.to_datetime(sel["data"], errors="coerce")
        data_edit = st.date_input("Data",
                                  value=data_base.date() if pd.notna(data_base) else datetime.date.today(),
                                  format="DD/MM/YYYY", key=kp + "data")

        tipo_opc = ["Entrada", "Saida"]
        tipo_e   = st.selectbox("Tipo", tipo_opc,
                                index=tipo_opc.index(sel["tipo"]) if sel["tipo"] in tipo_opc else 0,
                                key=kp + "tipo")

        if tipo_e == "Entrada":
            cat_atual = sel["categoria"] if sel["categoria"] in CATEGORIAS_ENTRADA else CATEGORIAS_ENTRADA[0]
            cat_e = st.selectbox("Categoria", CATEGORIAS_ENTRADA,
                                 index=CATEGORIAS_ENTRADA.index(cat_atual),
                                 key=kp + "cat")
        else:
            cat_e = "Despesa"
            st.text_input("Categoria", value="Despesa", disabled=True, key=kp + "cat_d")

        vinc_str   = str(sel["tipo_cadastro"]).strip().upper()
        vinc_pad_e = ("Membro" if (tipo_e == "Entrada" and cat_e == "Dizimo")
                      else "Fornecedor" if vinc_str == "FORNECEDOR"
                      else "Membro" if vinc_str == "MEMBRO"
                      else "Nenhum")
        vincular_e = st.selectbox("Vincular a", ["Nenhum", "Membro", "Fornecedor"],
                                  index=["Nenhum", "Membro", "Fornecedor"].index(vinc_pad_e),
                                  key=kp + "vinc")

        id_e, nome_e, tipo_e2 = None, "", ""
        if vincular_e == "Membro" and not membros.empty:
            opc    = montar_opcoes(membros)
            chave  = encontrar_chave(opc, sel["id_cadastro"])
            chaves = list(opc.keys())
            esc    = st.selectbox("Membro", chaves,
                                  index=chaves.index(chave) if chave in chaves else 0,
                                  key=kp + "mem")
            l = opc[esc]
            id_e, nome_e, tipo_e2 = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
        elif vincular_e == "Fornecedor" and not fornec.empty:
            opc    = montar_opcoes(fornec)
            chave  = encontrar_chave(opc, sel["id_cadastro"])
            chaves = list(opc.keys())
            esc    = st.selectbox("Fornecedor", chaves,
                                  index=chaves.index(chave) if chave in chaves else 0,
                                  key=kp + "forn")
            l = opc[esc]
            id_e, nome_e, tipo_e2 = int(l["id_cadastro"]), l["nome"], l["tipo_cadastro"]
        else:
            st.text_input("Nome", value="", disabled=True, key=kp + "nome_vazio")

        desc_e = st.text_input("Descricao", value=str(sel["descricao"]), key=kp + "desc")

        forma_pag_atual = str(sel.get("forma_pagamento", "Dinheiro")) if "forma_pagamento" in sel.index else "Dinheiro"
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
                                  id_cadastro=id_e, nome_cadastro=nome_e,
                                  tipo_cadastro=tipo_e2, id_lancamento=id_lanc)
                erros = lanc.validar()
                if erros:
                    for e in erros: st.error(e)
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
