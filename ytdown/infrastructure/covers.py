"""Preparo da imagem de capa com Pillow."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from ytdown.domain.errors import InvalidCover

MAX_COVER_SIZE = 1000  # Alguns players não exibem capas muito grandes.


class PillowCoverLoader:
    """Implementa CoverLoader: devolve a capa em JPEG, o formato mais aceito pelos players.

    A proporção da imagem é preservada, e áreas transparentes ficam brancas,
    porque JPEG não tem transparência.
    """

    def __init__(self, default_cover: Path) -> None:
        self._default_cover = default_cover

    def load(self, path: Path | None) -> bytes:
        source = path or self._default_cover
        try:
            with Image.open(source) as image:
                rgba = ImageOps.exif_transpose(image).convert("RGBA")
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            raise InvalidCover(f"Não foi possível ler a imagem de capa: {source}") from exc

        cover = Image.new("RGB", rgba.size, "white")
        cover.paste(rgba, mask=rgba.getchannel("A"))
        cover.thumbnail((MAX_COVER_SIZE, MAX_COVER_SIZE))
        output = io.BytesIO()
        cover.save(output, format="JPEG", quality=90)
        return output.getvalue()
