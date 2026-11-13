import pandas as pd
import pytest

from utils.helpers import formatar_data, formatar_moeda, normalizar_data_digitada, preparar_df


@pytest.mark.parametrize("entrada, esperado", [
    ("26061979", "26/06/1979"),   # 8 digitos
    ("260679", "26/06/1979"),     # 6 digitos, ano 19xx
    ("031125", "03/11/2025"),     # 6 digitos, ano 20xx
    ("26/06/1979", "26/06/1979"), # ja formatada: sem alteracao
    ("abc", "abc"),               # nao numerica: sem alteracao
    ("", ""),
])
def test_normalizar_data_digitada(entrada, esperado):
    assert normalizar_data_digitada(entrada) == esperado


def test_formatar_moeda_padrao_brasileiro():
    assert formatar_moeda(150.5) == "R$ 150,50"
    assert formatar_moeda(1234.56) == "R$ 1.234,56"


def test_formatar_data_iso_para_brasileiro():
    assert formatar_data("2026-11-03") == "03/11/2026"


def test_formatar_data_invalida_devolve_texto():
    assert formatar_data("nao-e-data") == "nao-e-data"


def test_preparar_df_formata_data_e_valor():
    df = pd.DataFrame({"data": ["2026-11-03"], "valor": [150.5]})
    resultado = preparar_df(df)
    assert resultado.loc[0, "data"] == "03/11/2026"
    assert resultado.loc[0, "valor"] == "R$ 150,50"
    assert df.loc[0, "valor"] == 150.5  # a entrada nao e alterada


@pytest.mark.parametrize("entrada", ["abc", None, [1, 2], {"a": 1}])
def test_formatar_percentual_com_entrada_invalida(entrada):
    from utils.helpers import formatar_percentual
    assert formatar_percentual(entrada) == "0.0%"


def test_formatar_percentual_valido():
    from utils.helpers import formatar_percentual
    assert formatar_percentual("12.345") == "12.3%"


def test_cadastros_formatar_data_e_foto():
    from modules.cadastros import _formatar_data, _foto_para_bytes
    assert _formatar_data("2026-11-03") == "03/11/2026"
    assert _formatar_data("lixo") == "lixo"
    assert _foto_para_bytes("data:image/png;base64,AAAA") == b"\x00\x00\x00"
    assert _foto_para_bytes("sem-virgula") is None
    # base64 nao validado: entrada corrompida vira bytes vazios (ponto a revisar), nunca erro.
    assert not _foto_para_bytes("data:x,@@@@")


def test_ebd_conversoes_seguras():
    from modules.ebd import _int_seguro, _float_seguro, _moeda
    assert _int_seguro("12", 0) == 12
    assert _int_seguro("x", 7) == 7
    assert _int_seguro(float("inf"), 3) == 3
    assert _float_seguro("1,5", 0.0) == 1.5
    assert _float_seguro(None, 2.0) == 2.0
    assert _moeda("abc") is not None
