"""
Central de regras de planos do FielMordomo.
Define limites, recursos e precos de cada plano.
"""

PLANOS = {
    "basico": {
        "nome":  "Basico",
        "preco": "R$ 29,90/mes",
        "preco_valor": 29.90,
        "limite_cadastros": 50,
        "limite_label": "ate 50 membros",
        "recursos": {
            "lancamento_lote":  False,
            "backup_automatico": False,
            "aniversariantes":   True,
            "cupom_fiscal":      True,
            "dashboard":         True,
            "relatorios":        True,
        },
        "cor": "#6c757d",
    },
    "profissional": {
        "nome":  "Profissional",
        "preco": "R$ 59,90/mes",
        "preco_valor": 59.90,
        "limite_cadastros": 250,
        "limite_label": "ate 250 membros",
        "recursos": {
            "lancamento_lote":  True,
            "backup_automatico": True,
            "aniversariantes":   True,
            "cupom_fiscal":      True,
            "dashboard":         True,
            "relatorios":        True,
        },
        "cor": "#1D9E75",
    },
    "premium": {
        "nome":  "Premium",
        "preco": "R$ 90,90/mes",
        "preco_valor": 90.90,
        "limite_cadastros": None,  # ilimitado
        "limite_label": "cadastros ilimitados",
        "recursos": {
            "lancamento_lote":  True,
            "backup_automatico": True,
            "aniversariantes":   True,
            "cupom_fiscal":      True,
            "dashboard":         True,
            "relatorios":        True,
        },
        "cor": "#F5A623",
    },
}


def plano_da_igreja(igreja: dict) -> dict:
    """Retorna o dict de regras do plano da igreja."""
    nome = str(igreja.get("plano", "basico")).strip().lower()
    return PLANOS.get(nome, PLANOS["basico"])


def limite_cadastros(igreja: dict):
    """Retorna o numero maximo de cadastros, ou None se ilimitado."""
    return plano_da_igreja(igreja)["limite_cadastros"]


def pode_cadastrar(igreja: dict, qtd_atual: int) -> bool:
    """True se ainda cabe um novo cadastro."""
    lim = limite_cadastros(igreja)
    if lim is None:
        return True
    return qtd_atual < lim


def recurso_liberado(igreja: dict, nome_recurso: str) -> bool:
    """Verifica se um recurso esta disponivel no plano."""
    return plano_da_igreja(igreja)["recursos"].get(nome_recurso, False)


def cor_plano(igreja: dict) -> str:
    return plano_da_igreja(igreja)["cor"]
