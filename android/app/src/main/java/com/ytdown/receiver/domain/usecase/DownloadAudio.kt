package com.ytdown.receiver.domain.usecase

import com.ytdown.receiver.domain.AudioLibrary
import com.ytdown.receiver.domain.NotAudioException
import com.ytdown.receiver.domain.PcConnection
import com.ytdown.receiver.domain.mimeTypeFor
import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.domain.model.Server
import com.ytdown.receiver.domain.safeAudioName
import java.io.IOException
import java.security.DigestOutputStream
import java.security.MessageDigest

/** Baixa um áudio do PC para a biblioteca de músicas do celular. Bloqueia a thread. */
class DownloadAudio(private val pc: PcConnection, private val library: AudioLibrary) {
    fun isSynced(server: Server, file: RemoteFile) = library.isSynced(server, file)

    /**
     * `onProgress` recebe a fração já baixada, de 0 a 1.
     * Falha com NotAudioException se o PC oferecer outro tipo de arquivo, ou IOException.
     */
    operator fun invoke(server: Server, token: String, file: RemoteFile, onProgress: (Float) -> Unit) {
        val name = safeAudioName(file.name) ?: throw NotAudioException()
        val mimeType = mimeTypeFor(name) ?: throw NotAudioException()
        library.saveFor(server, file, name, mimeType) { output ->
            val digest = MessageDigest.getInstance("SHA-256")
            var receivedBytes = 0L
            val checked = object : java.io.FilterOutputStream(DigestOutputStream(output, digest)) {
                override fun write(b: Int) { out.write(b); receivedBytes++ }
                override fun write(b: ByteArray, off: Int, len: Int) { out.write(b, off, len); receivedBytes += len }
            }
            pc.download(server, token, file, checked) { received, total ->
                if (total > 0) onProgress(received.toFloat() / total)
            }
            val hash = digest.digest().joinToString("") { "%02x".format(it) }
            if (receivedBytes != file.size || (file.sha256 != null && !hash.equals(file.sha256, ignoreCase = true)))
                throw IOException("Arquivo incompleto ou alterado durante a transferência")
        }
    }
}
