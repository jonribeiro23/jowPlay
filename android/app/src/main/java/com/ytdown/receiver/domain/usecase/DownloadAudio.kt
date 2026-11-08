package com.ytdown.receiver.domain.usecase

import com.ytdown.receiver.domain.AudioLibrary
import com.ytdown.receiver.domain.NotAudioException
import com.ytdown.receiver.domain.PcConnection
import com.ytdown.receiver.domain.mimeTypeFor
import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.domain.model.Server
import com.ytdown.receiver.domain.safeAudioName

/** Baixa um áudio do PC para a biblioteca de músicas do celular. Bloqueia a thread. */
class DownloadAudio(private val pc: PcConnection, private val library: AudioLibrary) {

    /**
     * `onProgress` recebe a fração já baixada, de 0 a 1.
     * Falha com NotAudioException se o PC oferecer outro tipo de arquivo, ou IOException.
     */
    operator fun invoke(server: Server, token: String, file: RemoteFile, onProgress: (Float) -> Unit) {
        val name = safeAudioName(file.name) ?: throw NotAudioException()
        val mimeType = mimeTypeFor(name) ?: throw NotAudioException()
        library.save(name, mimeType) { output ->
            pc.download(server, token, file, output) { received, total ->
                if (total > 0) onProgress(received.toFloat() / total)
            }
        }
    }
}
