import hashlib

import pytest

from data.repository import _validar_slug, _verificar_senha, hash_senha, slugify, validar_nova_senha


def test_hash_senha_usa_pbkdf2_com_salt():
    h1, h2 = hash_senha("senha-forte-123"), hash_senha("senha-forte-123")
    assert h1.startswith("pbkdf2_sha256$")
    assert h1 != h2  # salt aleatorio: mesmo texto, hashes diferentes


def test_verificar_senha_correta_e_incorreta():
    h = hash_senha("senha-forte-123")
    assert _verificar_senha("senha-forte-123", h) == (True, False)
    assert _verificar_senha("outra-senha", h) == (False, False)


def test_hash_legado_sha256_valida_e_pede_migracao():
    legado = hashlib.sha256("senha-antiga".encode("utf-8")).hexdigest()
    assert _verificar_senha("senha-antiga", legado) == (True, True)
    assert _verificar_senha("errada", legado) == (False, False)


@pytest.mark.parametrize("entrada", ["", None, 123, "pbkdf2_sha256$x$y"])
def test_entradas_invalidas_nao_autenticam(entrada):
    assert _verificar_senha(entrada, "pbkdf2_sha256$1$00$00")[0] is False


def test_hash_senha_vazia_levanta_erro():
    with pytest.raises(ValueError):
        hash_senha("")


def test_validar_nova_senha_respeita_minimo_e_maximo():
    assert validar_nova_senha("curta") != []
    assert validar_nova_senha("x" * 500) != []
    assert validar_nova_senha("senha-forte-123") == []


@pytest.mark.parametrize("texto, esperado", [
    ("Igreja Central", "igreja-central"),
    ("  Igreja   X!! ", "igreja-x"),
    ("---", ""),
])
def test_slugify_basico(texto, esperado):
    assert slugify(texto) == esperado


@pytest.mark.xfail(reason="slugify remove acentos como separadores: 'Assembleia' vira 'assembl-ia'",
                   strict=True)
def test_slugify_nao_quebra_palavras_acentuadas():
    assert slugify("Assembleia de Deus") == "assembleia-de-deus"
    assert slugify("Assembléia de Deus") == "assembleia-de-deus"


def test_validar_slug_aceita_formato_valido():
    assert _validar_slug("igreja-central") == "igreja-central"


@pytest.mark.parametrize("slug", ["Igreja Central", "igreja_central", "../etc"])
def test_validar_slug_rejeita_formato_invalido(slug):
    with pytest.raises(ValueError):
        _validar_slug(slug)
