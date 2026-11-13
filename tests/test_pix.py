import pytest

from modules.pix_brcode import _crc16, gerar_payload_pix


def _campos(payload: str) -> dict:
    """Le o copia e cola em pares ID/tamanho/valor (somente nivel superior)."""
    campos, i = {}, 0
    while i < len(payload):
        ident, tamanho = payload[i:i + 2], int(payload[i + 2:i + 4])
        campos[ident] = payload[i + 4:i + 4 + tamanho]
        i += 4 + tamanho
    return campos


def test_payload_tem_crc_valido():
    payload = gerar_payload_pix("teste@exemplo.com", "IGREJA TESTE", "MINACU", valor=50.0)
    assert payload[-8:-4] == "6304"
    assert payload[-4:] == _crc16(payload[:-4])


def test_payload_contem_chave_valor_e_moeda():
    payload = gerar_payload_pix("teste@exemplo.com", "IGREJA TESTE", "MINACU", valor=50.0)
    campos = _campos(payload)
    assert campos["54"] == "50.00"          # valor
    assert campos["58"] == "BR"             # pais
    assert campos["53"] == "986"            # moeda BRL
    assert "teste@exemplo.com" in campos["26"]


def test_valor_omitido_nao_gera_campo_54():
    payload = gerar_payload_pix("teste@exemplo.com", "IGREJA", "MINACU")
    assert "54" not in _campos(payload)


def test_nome_e_cidade_sao_limitados_e_maiusculos():
    payload = gerar_payload_pix("teste@exemplo.com", "a" * 40, "b" * 30)
    campos = _campos(payload)
    assert campos["59"] == "A" * 25
    assert campos["60"] == "B" * 15


def test_chave_vazia_levanta_erro():
    with pytest.raises(ValueError):
        gerar_payload_pix("   ", "IGREJA", "MINACU")
