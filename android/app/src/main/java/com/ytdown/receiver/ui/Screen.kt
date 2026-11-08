package com.ytdown.receiver.ui

import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.domain.model.Server

/** Situação do download de um arquivo. */
sealed interface Transfer {
    data class Running(val progress: Float) : Transfer
    data object Saved : Transfer
    data class Failed(val message: String) : Transfer
}

/** O que a tela mostra em cada momento. */
sealed interface Screen {
    data class Search(
        val servers: List<Server> = emptyList(),
        val busy: Boolean = false,
        val message: String? = null,
    ) : Screen

    data class Pair(val server: Server, val busy: Boolean = false, val message: String? = null) : Screen

    data class Files(
        val server: Server,
        val files: List<RemoteFile> = emptyList(),
        val transfers: Map<String, Transfer> = emptyMap(),
        val connected: Boolean = true,
    ) : Screen
}
