"""Regras de comparação de textos usadas na busca e na ordenação."""

from __future__ import annotations

import unicodedata


def search_key(text: str) -> str:
    """Forma do texto usada para buscar e ordenar: sem acentos, sem diferenciar maiúsculas
    e com espaços repetidos reduzidos. Assim, "acao" encontra "Ação".
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.casefold().split())
