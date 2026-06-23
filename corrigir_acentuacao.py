import shutil
from pathlib import Path


PADROES_CORROMPIDOS = (
    "?",
    "?",
    "?",
    "?",
    "??",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
)
PASTAS_IGNORADAS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".streamlit",
    ".mypy_cache",
    ".pytest_cache",
}


def pontuar_corrupcao(texto):
    return sum(texto.count(padrao) for padrao in PADROES_CORROMPIDOS)


def parece_corrompido(texto):
    return pontuar_corrupcao(texto) > 0


def _tentativas_decodificacao(texto):
    tentativas = []

    try:
        tentativas.append(
            texto.encode("cp1252", errors="strict").decode(
                "utf-8",
                errors="strict",
            )
        )
    except UnicodeError:
        pass

    # Fallbacks so entram se a conversao ideal nao for possivel.
    if tentativas:
        return tentativas

    for encoding_origem in ("cp1252", "latin1"):
        for erros in ("replace",):
            try:
                tentativas.append(
                    texto.encode(encoding_origem, errors=erros).decode(
                        "utf-8",
                        errors=erros,
                    )
                )
            except UnicodeError:
                pass

    return tentativas

def corrigir_mojibake(texto):
    corrigido = texto

    # Corrige arquivos que foram lidos como ANSI/Windows-1252 e salvos como UTF-8.
    # Repete porque alguns trechos aparecem com dupla conversao, como "irmão".
    for _ in range(6):
        pontuacao_atual = pontuar_corrupcao(corrigido)
        if pontuacao_atual == 0:
            break

        candidatos = _tentativas_decodificacao(corrigido)
        if not candidatos:
            break

        melhor = min(candidatos, key=pontuar_corrupcao)
        if pontuar_corrupcao(melhor) >= pontuacao_atual:
            break

        corrigido = melhor

    return corrigido


def deve_ignorar(caminho):
    partes = set(caminho.parts)
    return bool(partes & PASTAS_IGNORADAS)


def main():
    raiz = Path.cwd()
    pasta_backup = raiz / "_backup_acentuacao"
    alterados = []

    for caminho in raiz.rglob("*.py"):
        if deve_ignorar(caminho):
            continue
        if pasta_backup in caminho.parents:
            continue

        dados = caminho.read_bytes()

        try:
            texto = dados.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = dados.decode("cp1252")

        if not parece_corrompido(texto):
            continue

        corrigido = corrigir_mojibake(texto)

        if corrigido != texto:
            destino_backup = pasta_backup / caminho.relative_to(raiz)
            destino_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(caminho, destino_backup)
            caminho.write_text(corrigido, encoding="utf-8", newline="")
            alterados.append(caminho)

    if not alterados:
        print("Nenhum arquivo Python com acentuacao corrompida foi encontrado.")
        return

    print("Arquivos corrigidos:")
    for caminho in alterados:
        print(f"- {caminho}")
    print(f"\nBackup dos arquivos originais em: {pasta_backup}")


if __name__ == "__main__":
    main()
