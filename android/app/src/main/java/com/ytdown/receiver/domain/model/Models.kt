package com.ytdown.receiver.domain.model

/** Um PC com o ytDown compartilhando áudios na rede local. */
data class Server(val id: String, val name: String, val host: String, val port: Int)

/** Um áudio oferecido pelo PC. */
data class RemoteFile(val id: String, val name: String, val size: Long)
