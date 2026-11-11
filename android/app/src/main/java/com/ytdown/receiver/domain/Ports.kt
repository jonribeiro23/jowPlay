package com.ytdown.receiver.domain

import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.domain.model.Server
import java.io.OutputStream

// Interfaces de que o app precisa; a camada data as implementa.
// Todas as funções bloqueiam: chame fora da thread principal.

/** Encontra os PCs com o ytDown compartilhando na rede local. */
interface ServerDiscovery {
    fun discover(): List<Server>
}

/** Conversa com o ytDown de um PC. Falhas de rede são IOException. */
interface PcConnection {
    /** Conecta a um endereço digitado, como "192.168.0.8" ou "192.168.0.8:47821". */
    fun connectManually(address: String): Server

    /** Troca o código de pareamento por um token permanente. Falha com WrongCodeException. */
    fun pair(server: Server, code: String, device: String): String

    /** Falha com NotPairedException se o PC não reconhecer mais o token. */
    fun listFiles(server: Server, token: String): List<RemoteFile>

    fun cover(server: Server, token: String, file: RemoteFile): ByteArray? = null

    /** Copia o arquivo para `output`, informando (recebidos, total) em bytes. */
    fun download(server: Server, token: String, file: RemoteFile, output: OutputStream, onProgress: (Long, Long) -> Unit)
}

/** Onde os áudios recebidos ficam disponíveis para os players do celular. */
interface AudioLibrary {
    /** Se `write` falhar, nada fica salvo. */
    fun save(name: String, mimeType: String, write: (OutputStream) -> Unit)
    fun saveFor(server: Server, file: RemoteFile, name: String, mimeType: String, write: (OutputStream) -> Unit) = save(name, mimeType, write)
    fun isSynced(server: Server, file: RemoteFile): Boolean = false
}

/** Tokens dos PCs já pareados, guardados entre aberturas do app. */
interface PairingTokens {
    fun get(serverId: String): String?
    fun save(serverId: String, token: String)
    fun remove(serverId: String)
}
