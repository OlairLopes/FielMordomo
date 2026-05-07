from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


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
        if not self.slug.strip():
            erros.append("Slug e obrigatorio.")
        if not self.email_admin.strip():
            erros.append("E-mail e obrigatorio.")
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
        if self.cpf.strip():
            cpf_limpo = "".join(c for c in self.cpf if c.isdigit())
            if len(cpf_limpo) != 11:
                erros.append("CPF invalido. Informe 11 digitos.")
        if self.cep.strip():
            cep_limpo = "".join(c for c in self.cep if c.isdigit())
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
    id_cadastro: Optional[int] = None
    nome_cadastro: str = ""
    tipo_cadastro: str = ""
    id_lancamento: Optional[int] = None

    def validar(self) -> list[str]:
        erros = []
        if self.valor <= 0:
            erros.append("Valor deve ser maior que zero.")
        if self.tipo not in ("Entrada", "Saida"):
            erros.append("Tipo invalido.")
        if self.tipo == "Entrada" and self.categoria == "Dizimo" and not self.id_cadastro:
            erros.append("Para dizimo, selecione um membro.")
        return erros
