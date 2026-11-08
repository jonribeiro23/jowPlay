package com.ytdown.receiver.ui

import java.util.Locale

private val BRAZIL = Locale.forLanguageTag("pt-BR")

fun formatSize(bytes: Long): String = when {
    bytes < 1024 -> "$bytes B"
    bytes < 1024 * 1024 -> String.format(BRAZIL, "%.0f KB", bytes / 1024.0)
    else -> String.format(BRAZIL, "%.1f MB", bytes / (1024.0 * 1024.0))
}
