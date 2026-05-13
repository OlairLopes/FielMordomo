"""
Definicao dos planos do FielMordomo e regras de acesso.
"""

PLANOS = {
    "basico": {
        "nome":              "Basico",
        "preco":             "R$ 29,90/mes",
        "limite_membros":    50,
        "lancamento_lote":   False,
        "backup_automatico": False,
        "cor":               "#6c757d",
    },
    "profissional": {
        "nome":              "Profissional",
        "preco":             "R$ 59,90/mes",
        "limite_membros":    250,
        "lancamento_lote":   True,
        "backup_automatico": True,
        "cor":               "#1D9E75",
    },
    "premium": {
        "nome":              "Premium",
        "preco":             "R$ 90,90/mes",
        "limite_membros":    None,
        "lancamento_lote":   True,
        "backup_automatico": True,
        "cor":               "#0F6E56",
    },
}


def obter_plano(slug_plano):
    return PLANOS.get((slug_plano or "basico").lower(), PLANOS["basico"])


def pode_cadastrar_membro(plano, qtd_atual):
    p = obter_plano(plano)
    limite = p["limite_membros"]
    if limite is None:
        return True
    return qtd_atual < limite


def texto_limite(plano):
    p = obter_plano(plano)
    limite = p["limite_membros"]
    if limite is None:
        return "ilimitado"
    return str(limite)


def tem_lancamento_lote(plano):
    return obter_plano(plano)["lancamento_lote"]


def tem_backup_automatico(plano):
    return obter_plano(plano)["backup_automatico"]


def proximo_plano(plano):
    if plano == "basico":
        return "profissional"
    if plano == "profissional":
        return "premium"
    return "premium"
