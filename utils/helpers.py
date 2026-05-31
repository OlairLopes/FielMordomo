<<<<<<< HEAD
import time

=======
import hashlib
>>>>>>> 260a16ed078d5ed38360fa871afe8ae8dac6cacc
import pandas as pd
import streamlit as st

from data.repository import autenticar_igreja


<<<<<<< HEAD
AUTORIZACAO_TTL_SEGUNDOS = 5 * 60


=======
>>>>>>> 260a16ed078d5ed38360fa871afe8ae8dac6cacc
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
<<<<<<< HEAD
    colunas = {"tipo_cadastro", "situacao", "id_cadastro", "nome"}
    if df_cad.empty or not colunas.issubset(df_cad.columns):
        return pd.DataFrame(columns=df_cad.columns)
    tipos = df_cad["tipo_cadastro"].fillna("").astype(str).str.strip().str.upper()
    situacoes = df_cad["situacao"].fillna("").astype(str).str.strip().str.upper()
    return (
        df_cad[(tipos == str(tipo).upper()) & (situacoes == "ATIVO")]
=======
    return (
        df_cad[
            (df_cad["tipo_cadastro"].str.strip().str.upper() == tipo.upper()) &
            (df_cad["situacao"].str.strip().str.upper() == "ATIVO")
        ]
>>>>>>> 260a16ed078d5ed38360fa871afe8ae8dac6cacc
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


<<<<<<< HEAD
def _sanitizar_csv(valor):
    if isinstance(valor, str) and valor.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + valor
    return valor


def gerar_csv(df: pd.DataFrame) -> bytes:
    seguro = df.copy()
    for coluna in seguro.select_dtypes(include=["object", "string"]).columns:
        seguro[coluna] = seguro[coluna].map(_sanitizar_csv)
    return seguro.to_csv(index=False).encode("utf-8-sig")


def slug_da_sessao() -> str:
    igreja = st.session_state.get("igreja", {})
    if not isinstance(igreja, dict):
        return ""
    return str(igreja.get("slug", "") or "").strip().lower()
=======
def gerar_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def slug_da_sessao() -> str:
    return st.session_state.get("igreja", {}).get("slug", "")
>>>>>>> 260a16ed078d5ed38360fa871afe8ae8dac6cacc


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
<<<<<<< HEAD
    """Solicita a senha da igreja e mantem autorizacao por cinco minutos."""
    flag_mostrar = f"_auth_mostrar_{key}"
    flag_ate = f"_auth_ate_{key}"
    agora = time.monotonic()

    if st.session_state.get(flag_ate, 0) > agora:
        return True
    st.session_state.pop(flag_ate, None)
=======
    """
    Exibe campo de senha e valida contra o login da igreja.
    A autorizacao persiste ate ser explicitamente revogada,
    permitindo encadear com outras confirmacoes.
    """
    flag_mostrar = f"_auth_mostrar_{key}"
    flag_ok      = f"_auth_ok_{key}"

    # Ja autorizado anteriormente — mantem True para fluxos encadeados
    if st.session_state.get(flag_ok):
        return True
>>>>>>> 260a16ed078d5ed38360fa871afe8ae8dac6cacc

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
<<<<<<< HEAD
            if slug and autenticar_igreja(slug, senha):
                st.session_state[flag_mostrar] = False
                st.session_state[flag_ate] = agora + AUTORIZACAO_TTL_SEGUNDOS
=======
            if autenticar_igreja(slug, senha):
                st.session_state[flag_mostrar] = False
                st.session_state[flag_ok]      = True
>>>>>>> 260a16ed078d5ed38360fa871afe8ae8dac6cacc
                st.rerun()
            else:
                st.error("Senha incorreta. Tente novamente.")
    with c2:
        if st.button("Cancelar", key=f"cancelar_auth_{key}"):
            st.session_state[flag_mostrar] = False
            st.rerun()

    return False
