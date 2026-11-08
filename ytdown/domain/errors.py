"""Erros do domínio. As mensagens já estão prontas para serem mostradas ao usuário."""


class ExtractionError(Exception):
    """A extração de um vídeo falhou."""


class InvalidCover(ExtractionError):
    """A imagem de capa escolhida não pôde ser lida."""


class ExtractionCancelled(Exception):
    """O usuário cancelou a extração."""


class ShareError(Exception):
    """O compartilhamento com o celular não pôde ser iniciado."""
