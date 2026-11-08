package com.ytdown.receiver.domain

import java.util.Locale

private val MIME_TYPES = mapOf(
    "mp3" to "audio/mpeg",
    "m4a" to "audio/mp4",
    "flac" to "audio/flac",
    "wav" to "audio/x-wav",
)

/** Tipo do áudio pela extensão, ou null se não for um formato que o ytDown gera. */
fun mimeTypeFor(name: String): String? =
    MIME_TYPES[name.substringAfterLast('.', "").lowercase(Locale.ROOT)]

/**
 * Limpa o nome informado pelo PC antes de salvar. Devolve null se não for um
 * áudio válido: o app não deve aceitar outros tipos de arquivo da rede.
 */
fun safeAudioName(name: String): String? {
    val cleaned = name.substringAfterLast('/').substringAfterLast('\\')
        .filterNot { it.isISOControl() }
        .trim()
    val stem = cleaned.substringBeforeLast('.', "")
    return if (stem.isNotBlank() && mimeTypeFor(cleaned) != null) cleaned else null
}
