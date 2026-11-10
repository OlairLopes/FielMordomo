"""Gera o BR Code (copia e cola) do Pix estatico e o QR Code correspondente.

Especificacao: manual do BR Code do Banco Central (EMV MPM). O campo 63
e um CRC16-CCITT (poly 0x1021, init 0xFFFF) calculado sobre todo o payload
ate o proprio identificador "6304".
"""

import io
import re
import unicodedata

VALOR_MAXIMO = 100_000.00


def _crc16(texto: str) -> str:
    crc = 0xFFFF
    for byte in texto.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _campo(identificador: str, valor: str) -> str:
    return f"{identificador}{len(valor):02d}{valor}"


def _ascii_maiusculo(texto: str, limite: int) -> str:
    """Remove acentos e caracteres fora de A-Z/0-9/espaco, como pede o BR Code."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acento = sem_acento.encode("ascii", "ignore").decode("ascii")
    limpo = re.sub(r"[^A-Za-z0-9 ]", "", sem_acento).strip().upper()
    return re.sub(r" +", " ", limpo)[:limite]


def _txid_valido(txid: str) -> str:
    """TXID aceita ate 25 caracteres alfanumericos. Sem txid usa o padrao '***'."""
    limpo = re.sub(r"[^A-Za-z0-9]", "", str(txid or ""))[:25]
    return limpo or "***"


def gerar_payload_pix(chave: str, beneficiario: str, cidade: str,
                      valor: float | None = None, txid: str = "") -> str:
    """Monta o copia e cola de um Pix estatico.

    chave: chave Pix da igreja (CPF, CNPJ, e-mail, telefone ou aleatoria).
    beneficiario: nome que aparece para quem paga (ate 25 caracteres).
    cidade: cidade do beneficiario (ate 15 caracteres).
    valor: se informado, o app de banco ja preenche o valor.
    txid: identificador da contribuicao, quando o banco o devolver.
    """
    chave = str(chave or "").strip()
    if not chave:
        raise ValueError("Chave Pix não configurada.")

    beneficiario_limpo = _ascii_maiusculo(beneficiario, 25)
    cidade_limpa = _ascii_maiusculo(cidade, 15)
    if not beneficiario_limpo or not cidade_limpa:
        raise ValueError("Nome do beneficiário e cidade são obrigatórios.")

    partes = [
        _campo("00", "01"),
        _campo("26", _campo("00", "br.gov.bcb.pix") + _campo("01", chave)),
        _campo("52", "0000"),
        _campo("53", "986"),
    ]

    if valor is not None:
        valor_float = float(valor)
        if not (0 < valor_float <= VALOR_MAXIMO):
            raise ValueError("Valor fora do limite do Pix.")
        partes.append(_campo("54", f"{valor_float:.2f}"))

    partes.append(_campo("58", "BR"))
    partes.append(_campo("59", beneficiario_limpo))
    partes.append(_campo("60", cidade_limpa))
    partes.append(_campo("62", _campo("05", _txid_valido(txid))))

    sem_crc = "".join(partes) + "6304"
    return sem_crc + _crc16(sem_crc)


def gerar_qr_png(payload: str) -> bytes:
    """Devolve o QR Code do payload como PNG."""
    import qrcode

    imagem = qrcode.make(payload, box_size=8, border=2)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()
