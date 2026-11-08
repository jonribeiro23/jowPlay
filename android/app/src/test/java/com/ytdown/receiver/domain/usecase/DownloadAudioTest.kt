package com.ytdown.receiver.domain.usecase

import com.ytdown.receiver.domain.AudioLibrary
import com.ytdown.receiver.domain.NotAudioException
import com.ytdown.receiver.domain.PcConnection
import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.domain.model.Server
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.OutputStream

private val SERVER = Server("pc", "pc-teste", "192.168.0.8", 47821)
private val AUDIO = "audio".toByteArray()

private class FakePc(private val failAfterBytes: Boolean = false) : PcConnection {
    var downloads = 0

    override fun connectManually(address: String) = SERVER
    override fun pair(server: Server, code: String, device: String) = "token"
    override fun listFiles(server: Server, token: String) = emptyList<RemoteFile>()

    override fun download(
        server: Server,
        token: String,
        file: RemoteFile,
        output: OutputStream,
        onProgress: (Long, Long) -> Unit,
    ) {
        downloads++
        output.write(AUDIO)
        onProgress(AUDIO.size.toLong(), AUDIO.size.toLong())
        if (failAfterBytes) throw IOException("conexão caiu")
    }
}

/** Imita a biblioteca real: só guarda o arquivo se a escrita terminar sem erro. */
private class FakeLibrary : AudioLibrary {
    val saved = mutableMapOf<String, Pair<String, ByteArray>>()

    override fun save(name: String, mimeType: String, write: (OutputStream) -> Unit) {
        val buffer = ByteArrayOutputStream()
        write(buffer)
        saved[name] = mimeType to buffer.toByteArray()
    }
}

class DownloadAudioTest {
    @Test
    fun savesTheAudioWithItsTypeAndReportsProgress() {
        val library = FakeLibrary()
        val progress = mutableListOf<Float>()
        DownloadAudio(FakePc(), library)(SERVER, "token", RemoteFile("1", "Música.mp3", 5)) { progress += it }

        val (mimeType, bytes) = library.saved.getValue("Música.mp3")
        assertEquals("audio/mpeg", mimeType)
        assertArrayEquals(AUDIO, bytes)
        assertEquals(listOf(1f), progress)
    }

    @Test
    fun cleansTheNameBeforeSaving() {
        val library = FakeLibrary()
        DownloadAudio(FakePc(), library)(SERVER, "token", RemoteFile("1", "../../x.flac", 5)) {}
        assertEquals(setOf("x.flac"), library.saved.keys)
    }

    @Test
    fun refusesFilesThatAreNotAudioWithoutDownloading() {
        val pc = FakePc()
        val library = FakeLibrary()
        assertThrows(NotAudioException::class.java) {
            DownloadAudio(pc, library)(SERVER, "token", RemoteFile("1", "app.apk", 5)) {}
        }
        assertEquals(0, pc.downloads)
        assertTrue(library.saved.isEmpty())
    }

    @Test
    fun aBrokenTransferSavesNothing() {
        val library = FakeLibrary()
        assertThrows(IOException::class.java) {
            DownloadAudio(FakePc(failAfterBytes = true), library)(SERVER, "token", RemoteFile("1", "a.mp3", 5)) {}
        }
        assertTrue(library.saved.isEmpty())
    }
}
