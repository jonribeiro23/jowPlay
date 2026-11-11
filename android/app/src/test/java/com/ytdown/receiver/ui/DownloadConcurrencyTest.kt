package com.ytdown.receiver.ui

import com.ytdown.receiver.domain.*
import com.ytdown.receiver.domain.model.*
import com.ytdown.receiver.domain.usecase.DownloadAudio
import java.io.ByteArrayOutputStream
import java.io.OutputStream
import java.util.Collections
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class DownloadConcurrencyTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setup() = Dispatchers.setMain(dispatcher)
    @After fun cleanup() = Dispatchers.resetMain()

    @Test fun blockedTransferDoesNotOverlapNextDownload() = runTest(dispatcher) {
        val server = Server("test", "test", "host", 1)
        val files = (1..3).map { RemoteFile("$it", "$it.wav", 1) }
        val started = CountDownLatch(1)
        val release = CountDownLatch(1)
        val active = AtomicInteger()
        val maximum = AtomicInteger()
        val calls = Collections.synchronizedList(mutableListOf<String>())
        val pc = object : PcConnection {
            override fun connectManually(address: String) = server
            override fun pair(server: Server, code: String, device: String) = "test"
            override fun listFiles(server: Server, token: String) = files
            override fun download(server: Server, token: String, file: RemoteFile, output: OutputStream, onProgress: (Long, Long) -> Unit) {
                val count = active.incrementAndGet()
                maximum.updateAndGet { maxOf(it, count) }
                try {
                    calls.add(file.id)
                    if (file.id == "1") { started.countDown(); check(release.await(5, TimeUnit.SECONDS)) }
                    output.write(1)
                } finally { active.decrementAndGet() }
            }
        }
        val tokens = object : PairingTokens {
            override fun get(serverId: String) = "test"
            override fun save(serverId: String, token: String) {}
            override fun remove(serverId: String) {}
        }
        val library = object : AudioLibrary {
            override fun save(name: String, mimeType: String, write: (OutputStream) -> Unit) { write(ByteArrayOutputStream()) }
        }
        val vm = ReceiverViewModel(object : ServerDiscovery { override fun discover() = listOf(server) }, pc, tokens,
            DownloadAudio(pc, library), "test", Dispatchers.IO, 60_000)
        fun pumpUntil(condition: () -> Boolean) {
            repeat(500) {
                testScheduler.runCurrent()
                if (condition()) return
                Thread.sleep(10)
            }
            fail("Timed out waiting for asynchronous operation")
        }
        try {
            vm.open(server)
            pumpUntil { (vm.screen.value as? Screen.Files)?.connection == ConnectionState.CONNECTED }
            vm.download(server, files[0]); vm.download(server, files[1]); vm.download(server, files[2])
            pumpUntil { started.count == 0L }
            assertEquals(listOf("1"), calls.toList())
            assertEquals(Transfer.Queued, (vm.screen.value as Screen.Files).transfers["2"])
            release.countDown()
            pumpUntil { calls.size == 3 && active.get() == 0 }
            assertEquals(listOf("1", "2", "3"), calls.toList())
            assertEquals(1, maximum.get())
        } finally {
            release.countDown()
            vm.backToSearch()
            testScheduler.runCurrent()
        }
    }
}
