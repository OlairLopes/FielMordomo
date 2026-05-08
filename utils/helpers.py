import hashlib
import pandas as pd
import streamlit as st

from data.repository import autenticar_igreja


def formatar_moeda(valor) -> str:
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def preparar_df(df: pd.DataFrame) -> pd.DataFrame:
    v = df.copy()
    if "data" in v.columns:
        v["data"] = pd.to_datetime(v["data"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
    if "valor" in v.columns:
        v["valor"] = pd.to_numeric(v["valor"], errors="coerce").fillna(0.0).apply(formatar_moeda)
    return v


def obter_ativos(df_cad: pd.DataFrame, tipo: str) -> pd.DataFrame:
    return (
        df_cad[
            (df_cad["tipo_cadastro"].str.strip().str.upper() == tipo.upper()) &
            (df_cad["situacao"].str.strip().str.upper() == "ATIVO")
        ]
        .drop_duplicates("id_cadastro")
        .sort_values("nome")
    )


def montar_opcoes(df: pd.DataFrame) -> dict:
    return {
        f'{int(r["id_cadastro"])} - {r["nome"]}': r
        for _, r in df.iterrows()
        if pd.notna(r["id_cadastro"])
    }


def encontrar_chave(opcoes: dict, id_cad) -> str | None:
    try:
        target = int(id_cad)
    except (ValueError, TypeError):
        return None
    for chave, row in opcoes.items():
        try:
            if int(row["id_cadastro"]) == target:
                return chave
        except (ValueError, TypeError):
            continue
    return None


def gerar_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def slug_da_sessao() -> str:
    return st.session_state.get("igreja", {}).get("slug", "")


def confirmar_exclusao(key: str, label: str) -> bool:
    flag = f"_del_{key}"
    if st.button(label, key=key, type="secondary"):
        st.session_state[flag] = True
    if st.session_state.get(flag):
        st.warning("Tem certeza? Esta acao nao pode ser desfeita.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Sim, excluir", key=f"{key}_sim", type="primary"):
                st.session_state[flag] = False
                return True
        with c2:
            if st.button("Cancelar", key=f"{key}_nao"):
                st.session_state[flag] = False
    return False


def solicitar_autorizacao(key: str, acao: str = "continuar") -> bool:
    """
    Exibe campo de senha e valida contra o login da igreja.
    Retorna True apenas quando a senha for confirmada corretamente.
    """
    flag_mostrar = f"_auth_mostrar_{key}"
    flag_ok      = f"_auth_ok_{key}"

    if st.session_state.get(flag_ok):
        st.session_state[flag_ok] = False
        return True

    if not st.session_state.get(flag_mostrar):
        if st.button(f"Autorizar para {acao}", key=f"btn_auth_{key}", type="primary"):
            st.session_state[flag_mostrar] = True
            st.rerun()
        return False

    st.info("Digite a senha da igreja para autorizar esta acao.")
    senha = st.text_input(
        "Senha de autorizacao",
        type="password",
        key=f"senha_auth_{key}",
        placeholder="Digite sua senha...",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Confirmar", key=f"confirmar_auth_{key}", type="primary"):
            slug = slug_da_sessao()
            if autenticar_igreja(slug, senha):
                st.session_state[flag_mostrar] = False
                st.session_state[flag_ok] = True
                st.rerun()
            else:
                st.error("Senha incorreta. Tente novamente.")
    with c2:
        if st.button("Cancelar", key=f"cancelar_auth_{key}"):
            st.session_state[flag_mostrar] = False
            st.rerun()

    return False
