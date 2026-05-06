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
    id_cadastro: Optional[int] = None

    def validar(self) -> list[str]:
        erros = []
        if not self.nome.strip():
            erros.append("Nome e obrigatorio.")
        if self.tipo_cadastro not in ("Membro", "Fornecedor"):
            erros.append("Tipo de cadastro invalido.")
        return erros


@dataclass
class Lancamento:
    data: date
    tipo: str
    categoria: str
    valor: float
    descricao: str = ""
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
