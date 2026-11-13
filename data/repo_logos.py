"""Dominio: logos."""
from data import repo_base as _base
from data.repo_base import _validar_logo, _validar_slug


def salvar_logo_sistema(dados, extensao):
    dados, extensao = _validar_logo(dados, extensao)
    for f in _base.LOGOS_DIR.glob("sistema.*"):
        f.unlink()
    caminho = _base.LOGOS_DIR / f"sistema.{extensao}"
    caminho.write_bytes(dados)
    return caminho


def obter_logo_sistema():
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = _base.LOGOS_DIR / f"sistema.{ext}"
        if p.exists():
            return p.read_bytes(), ext
    return None


def salvar_logo_igreja(slug, dados, extensao):
    slug = _validar_slug(slug)
    dados, extensao = _validar_logo(dados, extensao)
    for f in _base.LOGOS_DIR.glob(f"{slug}.*"):
        if f.stem.startswith("sidebar_"):
            continue
        f.unlink()
    caminho = _base.LOGOS_DIR / f"{slug}.{extensao}"
    caminho.write_bytes(dados)
    return caminho


def obter_logo_igreja(slug):
    slug = _validar_slug(slug)
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = _base.LOGOS_DIR / f"{slug}.{ext}"
        if p.exists():
            return p.read_bytes(), ext
    return None


def salvar_logo_sidebar_sistema(dados, extensao):
    dados, extensao = _validar_logo(dados, extensao)
    for f in _base.LOGOS_DIR.glob("sidebar_sistema.*"):
        f.unlink()
    caminho = _base.LOGOS_DIR / f"sidebar_sistema.{extensao}"
    caminho.write_bytes(dados)
    return caminho


def obter_logo_sidebar_sistema():
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = _base.LOGOS_DIR / f"sidebar_sistema.{ext}"
        if p.exists():
            return p.read_bytes(), ext
    return None


def salvar_logo_sidebar_igreja(slug, dados, extensao):
    slug = _validar_slug(slug)
    dados, extensao = _validar_logo(dados, extensao)
    for f in _base.LOGOS_DIR.glob(f"sidebar_{slug}.*"):
        f.unlink()
    caminho = _base.LOGOS_DIR / f"sidebar_{slug}.{extensao}"
    caminho.write_bytes(dados)
    return caminho


def obter_logo_sidebar_igreja(slug):
    slug = _validar_slug(slug)
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = _base.LOGOS_DIR / f"sidebar_{slug}.{ext}"
        if p.exists():
            return p.read_bytes(), ext
    return None
