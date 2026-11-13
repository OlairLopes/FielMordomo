"""Testes de integracao da camada de dados com bancos SQLite temporarios.

Cada teste roda numa pasta temporaria propria: nenhum dado real e tocado.
"""
import datetime

import pytest

from data import repo_base
from data import repository as repo
from data.models import Igreja


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Redireciona master.db, tenants, logos e backups para tmp_path."""
    dados = tmp_path / "dados"
    tenants = dados / "tenants"
    logos = dados / "logos"
    backups = dados / "backups"
    for pasta in (dados, tenants, logos, backups):
        pasta.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(repo_base, "DATA_DIR", dados)
    monkeypatch.setattr(repo_base, "MASTER_DB", dados / "master.db")
    monkeypatch.setattr(repo_base, "TENANTS_DIR", tenants)
    monkeypatch.setattr(repo_base, "LOGOS_DIR", logos)
    monkeypatch.setattr(repo_base, "BACKUP_DIR", backups)
    repo.inicializar_master()
    return dados


def _criar_igreja(slug="igreja-teste", senha="senha-forte-123"):
    igreja = Igreja(
        nome="Igreja Teste",
        slug=slug,
        email_admin="admin@exemplo.com",
        senha_hash=repo.hash_senha(senha),
    )
    repo.criar_igreja(igreja)
    repo.inicializar_tenant(slug)
    return slug


def test_inicializacao_cria_master_com_tabela_igrejas(banco):
    assert (banco / "master.db").exists()


def test_autenticacao_aceita_senha_correta_e_recusa_errada(banco):
    slug = _criar_igreja()
    assert repo.autenticar_igreja(slug, "senha-forte-123") is not None
    assert repo.autenticar_igreja(slug, "senha-errada") is None


def test_contribuicao_pendente_sem_comprovante_nao_confirma(banco):
    slug = _criar_igreja()
    id_c = repo.criar_contribuicao_online(slug, "Maria", "Oferta", 30.0, "62999990000")
    with pytest.raises(ValueError, match="comprovante"):
        repo.confirmar_contribuicao_online(slug, id_c, datetime.date(2026, 11, 3), "Oferta", None)


def test_fluxo_completo_de_contribuicao_online(banco):
    slug = _criar_igreja()
    id_c = repo.criar_contribuicao_online(slug, "Maria", "Oferta", 30.0, "62999990000")

    pendentes = repo.listar_contribuicoes_online(slug, status="pendente")
    assert [p["id_contribuicao"] for p in pendentes] == [id_c]

    comprovante = b"%PDF-1.4 comprovante de teste"
    repo.anexar_comprovante_online(slug, id_c, comprovante, "pdf", "comprovante.pdf", "62999990000")

    id_lancamento = repo.confirmar_contribuicao_online(
        slug, id_c, datetime.date(2026, 11, 3), "Oferta", None
    )
    assert id_lancamento is not None
    assert repo.listar_contribuicoes_online(slug, status="pendente") == []

    # Uma contribuicao ja tratada nao pode ser confirmada de novo.
    with pytest.raises(ValueError):
        repo.confirmar_contribuicao_online(slug, id_c, datetime.date(2026, 11, 3), "Oferta", None)


def test_rejeitar_contribuicao_remove_da_fila_de_pendentes(banco):
    slug = _criar_igreja()
    id_c = repo.criar_contribuicao_online(slug, "Joao", "Oferta", 10.0, "62988880000")
    repo.rejeitar_contribuicao_online(slug, id_c)
    assert repo.listar_contribuicoes_online(slug, status="pendente") == []


def test_comprovante_com_formato_invalido_e_recusado(banco):
    slug = _criar_igreja()
    id_c = repo.criar_contribuicao_online(slug, "Ana", "Oferta", 10.0, "62977770000")
    with pytest.raises(ValueError):
        repo.anexar_comprovante_online(slug, id_c, b"texto qualquer", "txt", "x.txt", "62977770000")


def test_chave_pix_salva_e_lida_de_volta(banco):
    slug = _criar_igreja()
    repo.salvar_pix_igreja(slug, "teste@exemplo.com", "IGREJA TESTE", "MINACU")
    pix = repo.obter_pix_igreja(slug)
    assert pix["chave"] == "teste@exemplo.com"
    assert pix["beneficiario"] == "IGREJA TESTE"
    assert pix["cidade"] == "MINACU"


def test_slug_invalido_nao_chega_ao_banco(banco):
    with pytest.raises(ValueError):
        repo.criar_contribuicao_online("../fora", "X", "Oferta", 1.0, "")
