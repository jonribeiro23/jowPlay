package com.ytdown.receiver.ui

import com.ytdown.receiver.domain.*
import com.ytdown.receiver.domain.model.*
import com.ytdown.receiver.domain.usecase.DownloadAudio
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.OutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class DownloadQueueTest {
    private val dispatcher = StandardTestDispatcher()
    private val server = Server("pc", "PC", "host", 1)
    private val files = (1..3).map { RemoteFile("$it", "$it.mp3", 1) }
    private val calls = mutableListOf<String>()
    private var offline = false
    private var fail = false
    private val tokens = object : PairingTokens {
        override fun get(serverId: String) = "token"
        override fun save(serverId: String, token: String) {}
        override fun remove(serverId: String) {}
    }
    private val pc = object : PcConnection {
        override fun connectManually(address: String) = server
        override fun pair(server: Server, code: String, device: String) = "token"
        override fun listFiles(server: Server, token: String): List<RemoteFile> {
            if (offline) throw IOException()
            return files
        }
        override fun download(server: Server, token: String, file: RemoteFile, output: OutputStream, onProgress: (Long, Long) -> Unit) {
            calls.add(file.id)
            if (fail && file.id == "1") throw IOException()
            output.write(1)
            onProgress(1, 1)
        }
    }
    private val library = object : AudioLibrary {
        override fun save(name: String, mimeType: String, write: (OutputStream) -> Unit) { write(ByteArrayOutputStream()) }
    }
    private fun model() = ReceiverViewModel(object : ServerDiscovery {
        override fun discover() = listOf(server)
    }, pc, tokens, DownloadAudio(pc, library), "phone", dispatcher, 100)
    @Before fun setup() = Dispatchers.setMain(dispatcher)
    @After fun cleanup() = Dispatchers.resetMain()

    @Test fun queuesInOrderDeduplicatesAndContinuesAfterFailure() = runTest(dispatcher) {
        val vm = model(); vm.open(server); runCurrent()
        fail = true
        vm.download(server, files[0]); vm.download(server, files[0]); vm.download(server, files[1])
        assertEquals(Transfer.Queued, (vm.screen.value as Screen.Files).transfers["2"])
        runCurrent()
        assertEquals(listOf("1", "2"), calls)
        assertTrue((vm.screen.value as Screen.Files).transfers["1"] is Transfer.Failed)
        fail = false
        vm.download(server, files[0]); runCurrent()
        assertEquals(listOf("1", "2", "1"), calls)
        vm.backToSearch()
    }

    @Test fun reconnectResumesQueueAndSwitchCancelsIt() = runTest(dispatcher) {
        val vm = model(); vm.open(server); runCurrent()
        offline = true; advanceTimeBy(100); runCurrent()
        vm.download(server, files[0]); runCurrent()
        assertTrue(calls.isEmpty())
        offline = false; advanceTimeBy(100); runCurrent()
        assertEquals(listOf("1"), calls)
        offline = true; advanceTimeBy(100); runCurrent()
        vm.download(server, files[1]); vm.backToSearch(); runCurrent()
        assertEquals(listOf("1"), calls)
    }
}
