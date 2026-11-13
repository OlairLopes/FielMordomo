from modules.dashboard import _acoes_prioritarias


def _base(**over):
    kwargs = dict(
        saude_info={"cobertura": 5.0, "alertas": []},
        meta_reserva=3,
        saldo_ytd=1000.0,
        churn_info={"quantidade": 0, "impacto_estimado": 0.0},
        resumo_atencao=[],
        abc_info={"pct_valor_top_a": 40.0, "pct_dizimistas_top_a": 20.0},
        score={"score_total": 80},
    )
    kwargs.update(over)
    return kwargs


def test_sem_problemas_nao_gera_acoes():
    assert _acoes_prioritarias(**_base()) == []


def test_reserva_abaixo_da_meta_e_critica():
    acoes = _acoes_prioritarias(**_base(saude_info={"cobertura": 1.5, "alertas": []}))
    assert acoes[0][0] == "critico"
    assert "Reserva" in acoes[0][1]


def test_saldo_negativo_e_critico_e_vem_primeiro():
    acoes = _acoes_prioritarias(**_base(saldo_ytd=-300.0, churn_info={"quantidade": 2, "impacto_estimado": 90.0}))
    assert acoes[0][0] == "critico"
    assert "negativo" in acoes[0][1]
    assert acoes[-1][0] == "atencao"


def test_churn_gera_acao_com_quantidade():
    acoes = _acoes_prioritarias(**_base(churn_info={"quantidade": 3, "impacto_estimado": 450.0}))
    assert any("3 dizimista(s)" in titulo for _, titulo, _ in acoes)


def test_faixa_mais_antiga_gera_acao_critica():
    faixas = [
        {"limite": 30, "quantidade": 10, "percentual": 5.0},
        {"limite": 90, "quantidade": 4, "percentual": 2.0},
    ]
    acoes = _acoes_prioritarias(**_base(resumo_atencao=faixas))
    criticas = [a for a in acoes if a[0] == "critico"]
    assert any("4 membro(s)" in a[1] and "90 dias" in a[1] for a in criticas)


def test_concentracao_de_receita_a_partir_de_60_por_cento():
    acoes = _acoes_prioritarias(**_base(abc_info={"pct_valor_top_a": 72.0, "pct_dizimistas_top_a": 15.0}))
    assert any("concentrada" in titulo for _, titulo, _ in acoes)


def test_score_baixo_gera_acao():
    acoes = _acoes_prioritarias(**_base(score={"score_total": 42}))
    assert any("42/100" in titulo for _, titulo, _ in acoes)


def test_alertas_de_reserva_e_saldo_nao_duplicam():
    alertas = [("critico", "A reserva cobre 1.0 mes(es), abaixo da meta de 3 mes(es)."),
               ("critico", "O saldo acumulado dos lancamentos registrados esta negativo.")]
    acoes = _acoes_prioritarias(**_base(saude_info={"cobertura": 1.0, "alertas": alertas}))
    assert sum(1 for a in acoes if "reserva" in a[1].lower()) == 1
    assert not any("saldo acumulado" in a[2].lower() for a in acoes)


def test_ordenacao_por_gravidade():
    acoes = _acoes_prioritarias(**_base(
        saldo_ytd=-1.0,
        churn_info={"quantidade": 1, "impacto_estimado": 10.0},
        score={"score_total": 10},
    ))
    niveis = [a[0] for a in acoes]
    assert niveis == sorted(niveis, key=lambda n: {"critico": 0, "atencao": 1, "info": 2}[n])
