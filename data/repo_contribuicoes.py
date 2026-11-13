"""Dominio: contribuicoes."""
import base64
import io
import re
import datetime
from data.repo_base import (
    CATEGORIAS_ENTRADA, CONFIG_PIX_QR, PIX_QR_EXTENSOES, PIX_QR_MAX_BYTES, _conn,
    _garantir_tabela_contribuicoes_online, _tenant_db, inicializar_tenant, inserir_lancamento,
    obter_config_igreja, salvar_config_igreja, sanitizar
)


def obter_pix_igreja(slug: str) -> dict:
    return {
        "chave": obter_config_igreja(slug, "pix_chave", ""),
        "beneficiario": obter_config_igreja(slug, "pix_beneficiario", ""),
        "cidade": obter_config_igreja(slug, "pix_cidade", ""),
    }


def salvar_pix_igreja(slug: str, chave: str, beneficiario: str, cidade: str):
    chave = str(chave or "").strip()
    beneficiario = sanitizar(beneficiario).strip()
    cidade = sanitizar(cidade).strip()
    if not chave:
        raise ValueError("Informe a chave Pix.")
    if not beneficiario or len(beneficiario) > 25:
        raise ValueError("Beneficiário obrigatório, com até 25 caracteres.")
    if not cidade or len(cidade) > 15:
        raise ValueError("Cidade obrigatória, com até 15 caracteres.")
    salvar_config_igreja(slug, "pix_chave", chave)
    salvar_config_igreja(slug, "pix_beneficiario", beneficiario)
    salvar_config_igreja(slug, "pix_cidade", cidade)


def criar_contribuicao_online(slug: str, nome: str, tipo: str, valor: float, contato: str = "") -> int:
    if tipo not in CATEGORIAS_ENTRADA:
        raise ValueError("Tipo de contribuição inválido.")
    if not str(nome or "").strip():
        raise ValueError("Informe seu nome.")
    if len(re.sub(r"\D", "", str(contato or ""))) not in (10, 11):
        raise ValueError("Informe o telefone com DDD (10 ou 11 dígitos).")
    valor = float(valor)
    if not (1 <= valor <= 100_000):
        raise ValueError("Valor deve ficar entre R$ 1,00 e R$ 100.000,00.")
    db = _tenant_db(slug)
    if not db.exists():
        inicializar_tenant(slug)
    with _conn(db) as conn:
        _garantir_tabela_contribuicoes_online(conn)
        cur = conn.execute(
            """INSERT INTO contribuicoes_online (criado_em, nome_doador, contato, tipo, valor)
               VALUES (?,?,?,?,?)""",
            (datetime.datetime.now().isoformat(timespec="seconds"), sanitizar(nome)[:80],
             sanitizar(contato)[:120], tipo, round(valor, 2)),
        )
        return cur.lastrowid


def confirmar_contribuicao_online(slug: str, id_contribuicao: int, data_recebimento,
                                  categoria: str, id_cadastro: int | None = None) -> int:
    """Marca a contribuicao como confirmada e grava a receita no financeiro.

    Reserva a contribuicao com um UPDATE condicional antes de inserir o
    lancamento, para que um duplo clique nao gere duas receitas.
    """
    from data.models import Lancamento

    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabela_contribuicoes_online(conn)
        row = conn.execute(
            """SELECT status, valor, nome_doador, comprovante IS NOT NULL AS tem_comprovante
               FROM contribuicoes_online WHERE id_contribuicao=?""",
            (id_contribuicao,),
        ).fetchone()
        if row is None or row["status"] != "pendente":
            raise ValueError("Contribuição já foi tratada ou não existe.")
        if not row["tem_comprovante"]:
            raise ValueError("Anexe o comprovante do Pix antes de confirmar.")
        reserva = conn.execute(
            """UPDATE contribuicoes_online SET status='confirmada'
               WHERE id_contribuicao=? AND status='pendente'""",
            (id_contribuicao,),
        )
        if reserva.rowcount != 1:
            raise ValueError("Contribuição já foi tratada ou não existe.")

    try:
        id_lancamento = inserir_lancamento(slug, Lancamento(
            data=data_recebimento,
            tipo="Entrada",
            categoria=categoria,
            valor=row["valor"],
            descricao=f"Contribuicao online #{id_contribuicao} - {row['nome_doador'] or 'Anonimo'}",
            forma_pagamento="Pix",
            id_cadastro=id_cadastro,
        ))
    except Exception:
        with _conn(db) as conn:
            conn.execute(
                "UPDATE contribuicoes_online SET status='pendente' WHERE id_contribuicao=?",
                (id_contribuicao,),
            )
        raise

    with _conn(db) as conn:
        conn.execute(
            """UPDATE contribuicoes_online SET id_lancamento=?, confirmado_em=?
               WHERE id_contribuicao=?""",
            (id_lancamento, datetime.datetime.now().isoformat(timespec="seconds"), id_contribuicao),
        )
    return id_lancamento


def rejeitar_contribuicao_online(slug: str, id_contribuicao: int):
    db = _tenant_db(slug)
    with _conn(db) as conn:
        _garantir_tabela_contribuicoes_online(conn)
        cur = conn.execute(
            """UPDATE contribuicoes_online SET status='rejeitada'
               WHERE id_contribuicao=? AND status='pendente'""",
            (id_contribuicao,),
        )
        if cur.rowcount != 1:
            raise ValueError("Contribuição já foi tratada ou não existe.")


def salvar_pix_qr_igreja(slug: str, dados: bytes, extensao: str):
    from PIL import Image

    if extensao not in PIX_QR_EXTENSOES:
        raise ValueError("Envie o QR Code em PNG, JPG ou WEBP.")
    if not dados or len(dados) > PIX_QR_MAX_BYTES:
        raise ValueError("A imagem do QR Code deve ter até 2 MB.")
    try:
        imagem = Image.open(io.BytesIO(dados)).convert("RGB")
    except (OSError, ValueError) as ex:
        raise ValueError("Não foi possível ler a imagem enviada.") from ex
    imagem.thumbnail((700, 700))
    saida = io.BytesIO()
    imagem.save(saida, format="PNG", optimize=True)
    b64 = base64.b64encode(saida.getvalue()).decode()
    salvar_config_igreja(slug, CONFIG_PIX_QR, f"data:image/png;base64,{b64}")


def obter_pix_qr_igreja(slug: str):
    valor = obter_config_igreja(slug, CONFIG_PIX_QR, "")
    if not valor or "," not in valor:
        return None
    try:
        return base64.b64decode(valor.split(",", 1)[1])
    except (ValueError, TypeError):
        return None


def remover_pix_qr_igreja(slug: str):
    salvar_config_igreja(slug, CONFIG_PIX_QR, "")
