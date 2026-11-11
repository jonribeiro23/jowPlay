package com.ytdown.receiver.ui

import com.ytdown.receiver.domain.*
import com.ytdown.receiver.domain.model.*
import com.ytdown.receiver.domain.usecase.DownloadAudio
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
class SessionLifecycleTest {
    private val dispatcher = StandardTestDispatcher()
    private val original = Server("pc", "PC", "old", 1)
    private val moved = original.copy(host = "new")
    private var failing = false
    private val calls = mutableListOf<Server>()
    private val tokens = object : PairingTokens {
        var token: String? = "saved"
        override fun get(serverId: String) = token
        override fun save(serverId: String, token: String) { this.token = token }
        override fun remove(serverId: String) { token = null }
    }
    private val pc = object : PcConnection {
        override fun connectManually(address: String) = original
        override fun pair(server: Server, code: String, device: String) = "saved"
        override fun listFiles(server: Server, token: String): List<RemoteFile> {
            calls.add(server)
            if (failing) throw IOException()
            return listOf(RemoteFile("1", "a.mp3", 10))
        }
        override fun download(server: Server, token: String, file: RemoteFile, output: OutputStream, onProgress: (Long, Long) -> Unit) {}
    }
    private val library = object : AudioLibrary {
        override fun save(name: String, mimeType: String, write: (OutputStream) -> Unit) {}
    }
    private fun model() = ReceiverViewModel(object : ServerDiscovery {
        override fun discover() = listOf(moved)
    }, pc, tokens, DownloadAudio(pc, library), "phone", dispatcher, 100)

    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { Dispatchers.resetMain() }

    @Test fun reconnectsToSamePcAtNewAddressWithoutLosingToken() = runTest(dispatcher) {
        val vm = model()
        vm.open(original)
        assertEquals(ConnectionState.CONNECTING, (vm.screen.value as Screen.Files).connection)
        runCurrent()
        assertEquals(ConnectionState.CONNECTED, (vm.screen.value as Screen.Files).connection)
        failing = true
        advanceTimeBy(100); runCurrent()
        assertEquals(ConnectionState.DISCONNECTED, (vm.screen.value as Screen.Files).connection)
        assertEquals("saved", tokens.token)
        failing = false
        advanceTimeBy(100); runCurrent()
        assertEquals(moved, calls.last())
        assertEquals(ConnectionState.CONNECTED, (vm.screen.value as Screen.Files).connection)
        vm.backToSearch()
    }

    @Test fun switchingPcCancelsPendingSession() = runTest(dispatcher) {
        val vm = model()
        vm.open(original)
        vm.backToSearch()
        runCurrent()
        assertTrue(vm.screen.value is Screen.Search)
        assertTrue(calls.isEmpty())
        assertEquals("saved", tokens.token)
    }

    @Test fun automaticallySelectsPairedPcAmongOtherDiscoveredPcs() = runTest(dispatcher) {
        val selectiveTokens = object : PairingTokens {
            override fun get(serverId: String) = if (serverId == original.id) "saved" else null
            override fun save(serverId: String, token: String) {}
            override fun remove(serverId: String) {}
        }
        val vm = ReceiverViewModel(object : ServerDiscovery {
            override fun discover() = listOf(moved, Server("other", "Outro", "other", 1))
        }, pc, selectiveTokens, DownloadAudio(pc, library), "phone", dispatcher, 100)
        vm.searchLoop()
        runCurrent()
        assertEquals(moved, (vm.screen.value as Screen.Files).server)
        vm.backToSearch()
    }
}
