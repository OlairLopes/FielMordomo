from dataclasses import dataclass
from datetime import date
import math
import re
from typing import Optional


SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def limpar_documento(documento: str) -> str:
    return "".join(c for c in str(documento or "") if c.isdigit())


def validar_cpf(cpf: str) -> bool:
    digits = limpar_documento(cpf)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False

    for tamanho in (9, 10):
        soma = sum(int(digits[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if digito != int(digits[tamanho]):
            return False
    return True


def validar_cnpj(cnpj: str) -> bool:
    digits = limpar_documento(cnpj)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False

    for pesos, posicao in (
        ((5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2), 12),
        ((6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2), 13),
    ):
        resto = sum(int(d) * peso for d, peso in zip(digits, pesos)) % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(digits[posicao]):
            return False
    return True


@dataclass
class Igreja:
    nome: str
    slug: str
    email_admin: str
    senha_hash: str
    plano: str = "basico"
    ativa: bool = True
    criada_em: Optional[str] = None
    id: Optional[int] = None

    def validar(self) -> list[str]:
        erros = []
        if not self.nome.strip():
            erros.append("Nome da igreja e obrigatorio.")
        if not SLUG_RE.fullmatch(self.slug.strip().lower()):
            erros.append("Slug invalido. Use letras minusculas, numeros e hifens.")
        if not EMAIL_RE.fullmatch(self.email_admin.strip()):
            erros.append("E-mail invalido.")
        return erros


@dataclass
class Cadastro:
    nome: str
    tipo_cadastro: str
    situacao: str
    funcao: str = ""
    congregacao: str = ""
    cpf: str = ""
    data_nascimento: str = ""
    sexo: str = ""
    telefone: str = ""
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    cidade: str = ""
    cep: str = ""
    id_cadastro: Optional[int] = None

    def validar(self) -> list[str]:
        erros = []
        if not self.nome.strip():
            erros.append("Nome e obrigatorio.")
        if self.tipo_cadastro not in ("Membro", "Fornecedor"):
            erros.append("Tipo de cadastro invalido.")
        if self.situacao not in ("Ativo", "Inativo"):
            erros.append("Situacao invalida.")

        if self.tipo_cadastro == "Membro" and not validar_cpf(self.cpf):
            erros.append("CPF invalido.")

        if self.tipo_cadastro == "Fornecedor" and not validar_cnpj(self.cpf):
            erros.append("CNPJ invalido.")

        if self.cep.strip():
            cep_limpo = limpar_documento(self.cep)
            if len(cep_limpo) != 8:
                erros.append("CEP invalido. Informe 8 digitos.")
        return erros


@dataclass
class Lancamento:
    data: date
    tipo: str
    categoria: str
    valor: float
    descricao: str = ""
    forma_pagamento: str = "Dinheiro"
    subcategoria: str = ""
    id_cadastro: Optional[int] = None
    nome_cadastro: str = ""
    tipo_cadastro: str = ""
    id_lancamento: Optional[int] = None

    def validar(self) -> list[str]:
        erros = []
        try:
            valor = float(self.valor)
        except (TypeError, ValueError):
            valor = 0
        if not math.isfinite(valor) or valor <= 0:
            erros.append("Valor deve ser maior que zero.")
        if not isinstance(self.data, date):
            erros.append("Data invalida.")
        if self.tipo not in ("Entrada", "Saida"):
            erros.append("Tipo invalido.")
        if not str(self.categoria or "").strip():
            erros.append("Categoria e obrigatoria.")
        if self.tipo == "Entrada" and self.categoria == "Dizimo":
            if not self.id_cadastro or self.tipo_cadastro != "Membro":
                erros.append("Para dizimo, selecione um membro.")
        return erros


@dataclass
class Tesoureiro:
    nome: str
    cpf: str
    usuario: str = ""
    senha: str = ""
    telefone: str = ""
    email: str = ""
    data_inicio: str = ""
    data_fim: str = ""
    situacao: str = "Ativo"
    principal: bool = False
    observacoes: str = ""
    id_tesoureiro: Optional[int] = None

    def validar(self) -> list[str]:
        erros = []
        if not self.nome.strip():
            erros.append("Nome e obrigatorio.")
        if not validar_cpf(self.cpf):
            erros.append("CPF invalido.")
        if not self.usuario.strip():
            erros.append("Usuario de acesso e obrigatorio.")
        if self.email.strip() and not EMAIL_RE.fullmatch(self.email.strip()):
            erros.append("E-mail invalido.")
        if self.situacao not in ("Ativo", "Inativo"):
            erros.append("Situacao invalida.")
        if self.principal and self.situacao != "Ativo":
            erros.append("O responsavel principal deve estar ativo.")
        inicio = self._data_iso(self.data_inicio, "Data inicial", erros)
        fim = self._data_iso(self.data_fim, "Data final", erros)
        if inicio and fim and fim < inicio:
            erros.append("Data final deve ser igual ou posterior a data inicial.")
        if self.situacao == "Inativo" and not fim:
            erros.append("Informe a data final para preservar o historico de atuacao.")
        return erros

    @staticmethod
    def _data_iso(valor, rotulo, erros):
        if not valor:
            return None
        try:
            return date.fromisoformat(str(valor))
        except ValueError:
            erros.append(f"{rotulo} invalida.")
            return None
