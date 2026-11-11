package com.ytdown.receiver.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.ytdown.receiver.AppContainer
import com.ytdown.receiver.domain.NotAudioException
import com.ytdown.receiver.domain.NotPairedException
import com.ytdown.receiver.domain.PairingTokens
import com.ytdown.receiver.domain.PcConnection
import com.ytdown.receiver.domain.ServerDiscovery
import com.ytdown.receiver.domain.WrongCodeException
import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.domain.model.Server
import com.ytdown.receiver.domain.usecase.DownloadAudio
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.Job
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.withContext
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.ensureActive
import java.io.IOException
import kotlin.coroutines.coroutineContext

private const val POLL_INTERVAL_MS = 2_000L
private const val PROGRESS_INTERVAL_MS = 100L

private const val MANUAL_CONNECT_FAILED =
    "Não foi possível conectar. Confira o endereço e se o ytDown está aberto no PC."
private const val WRONG_CODE = "Código incorreto. Confira o código na tela do PC."
private const val NO_CONNECTION = "Sem conexão com o PC. Tente de novo."
private const val PAIR_AGAIN = "O PC pediu um novo pareamento."
private const val NOT_AUDIO = "O PC enviou um arquivo que não é de áudio."
private const val DOWNLOAD_FAILED = "A transferência falhou. Tente de novo."

class ReceiverViewModel(
    private val discovery: ServerDiscovery,
    private val connection: PcConnection,
    private val tokens: PairingTokens,
    private val downloadAudio: DownloadAudio,
    private val deviceName: String,
    private val io: CoroutineDispatcher = Dispatchers.IO,
    private val pollInterval: Long = POLL_INTERVAL_MS,
) : ViewModel() {

    private val _screen = MutableStateFlow<Screen>(Screen.Search())
    val screen: StateFlow<Screen> = _screen.asStateFlow()

    /** Falso depois de "Trocar de PC", para o app não voltar sozinho ao mesmo PC. */
    private var autoConnect = true
    private var filesJob: Job? = null
    private var generation = 0L
    private data class DownloadKey(val serverId: String, val fileId: String, val revision: String?, val hash: String?)
    private data class DownloadRequest(val key: DownloadKey, val file: RemoteFile)
    private var queue = Channel<DownloadRequest>(Channel.UNLIMITED)
    private val pending = mutableSetOf<DownloadKey>()
    private var worker: Job? = null
    private val transferMutex = Mutex()

    private fun closeQueue() {
        queue.close()
        worker?.cancel()
        worker = null
        pending.clear()
        queue = Channel(Channel.UNLIMITED)
    }

    // --- busca

    /** Procura PCs enquanto a tela de busca estiver aberta. */
    suspend fun searchLoop() {
        while (coroutineContext.isActive && _screen.value is Screen.Search) {
            val request = generation
            val servers = try {
                withContext(io) { discovery.discover() }
            } catch (_: IOException) {
                emptyList()
            }
            if (_screen.value !is Screen.Search) return
            if (request != generation || (_screen.value as Screen.Search).busy) {
                delay(pollInterval)
                continue
            }
            val only = servers.singleOrNull()
            if (autoConnect && only != null && tokens.get(only.id) != null) {
                open(only)
                return
            }
            updateSearch { it.copy(servers = servers) }
            delay(pollInterval)
        }
    }

    fun open(server: Server) {
        closeQueue()
        filesJob?.cancel()
        generation++
        if (tokens.get(server.id) != null) startFiles(server) else _screen.value = Screen.Pair(server)
    }

    fun connectManually(address: String) {
        val request = ++generation
        updateSearch { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            try {
                val server = withContext(io) { connection.connectManually(address) }
                if (request == generation) open(server)
            } catch (_: IOException) {
                if (request == generation) updateSearch { it.copy(busy = false, message = MANUAL_CONNECT_FAILED) }
            }
        }
    }

    fun backToSearch() {
        closeQueue()
        generation++
        filesJob?.cancel()
        autoConnect = false
        _screen.value = Screen.Search()
    }

    // --- pareamento

    fun pair(server: Server, code: String) {
        val request = ++generation
        _screen.value = Screen.Pair(server, busy = true)
        viewModelScope.launch {
            try {
                val token = withContext(io) { connection.pair(server, code, deviceName) }
                if (request == generation) {
                    tokens.save(server.id, token)
                    startFiles(server)
                }
            } catch (_: WrongCodeException) {
                if (request == generation) _screen.value = Screen.Pair(server, message = WRONG_CODE)
            } catch (_: IOException) {
                if (request == generation) _screen.value = Screen.Pair(server, message = NO_CONNECTION)
            }
        }
    }

    // --- arquivos

    private fun startFiles(server: Server) {
        filesJob?.cancel()
        val request = generation
        _screen.value = Screen.Files(server)
        filesJob = viewModelScope.launch { filesLoop(server, request) }
    }

    private suspend fun filesLoop(initial: Server, request: Long) {
        var server = initial
        while (coroutineContext.isActive && request == generation) {
            val token = tokens.get(server.id)
            if (token == null) {
                _screen.value = Screen.Pair(server)
                return
            }
            try {
                val (files, synced) = withContext(io) {
                    val files = connection.listFiles(server, token)
                    files to files.filter { downloadAudio.isSynced(server, it) }.map { it.id }.toSet()
                }
                if (request != generation) return
                updateFiles { state -> state.copy(server = server, files = files, synced = synced,
                    transfers = state.transfers.filter { (id, transfer) ->
                        val old = state.files.firstOrNull { it.id == id }
                        val fresh = files.firstOrNull { it.id == id }
                        transfer !is Transfer.Saved && old != null && fresh != null &&
                            old.revision == fresh.revision && old.sha256 == fresh.sha256
                    }, connection = ConnectionState.CONNECTED) }
            } catch (_: NotPairedException) {
                if (request != generation) return
                closeQueue()
                tokens.remove(server.id)
                _screen.value = Screen.Pair(server, message = PAIR_AGAIN)
                return
            } catch (_: IOException) {
                if (request != generation) return
                updateFiles { it.copy(connection = ConnectionState.DISCONNECTED) }
                val found = try {
                    withContext(io) { discovery.discover().firstOrNull { it.id == server.id } }
                } catch (_: IOException) { null }
                if (request != generation) return
                if (found != null) server = found
            }
            delay(pollInterval)
        }
    }

    fun download(server: Server, file: RemoteFile) {
        val current = _screen.value as? Screen.Files ?: return
        if (current.server.id != server.id || tokens.get(server.id) == null) return
        val latest = current.files.firstOrNull { it.id == file.id } ?: return
        if (latest.revision != file.revision || latest.sha256 != file.sha256 ||
            file.id in current.synced || current.transfers[file.id] == Transfer.Saved) return
        val key = DownloadKey(server.id, file.id, file.revision, file.sha256)
        if (!pending.add(key)) return
        setTransfer(file, Transfer.Queued)
        queue.trySend(DownloadRequest(key, file))
        if (worker?.isActive == true) return
        val requestGeneration = generation
        val requests = queue
        worker = viewModelScope.launch {
            for (item in requests) {
                try {
                    val available = screen.first { state ->
                        state !is Screen.Files || state.server.id != item.key.serverId || state.connection == ConnectionState.CONNECTED
                    } as? Screen.Files ?: break
                    if (requestGeneration != generation || available.server.id != item.key.serverId) break
                    val latest = available.files.firstOrNull { it.id == item.file.id }
                    if (latest == null || latest.revision != item.file.revision || latest.sha256 != item.file.sha256) {
                        setTransfer(item.file, Transfer.Failed("A faixa mudou no PC. Tente de novo."))
                        continue
                    }
                    val token = tokens.get(item.key.serverId) ?: break
                    transferMutex.withLock {
                        if (requestGeneration == generation) performDownload(available.server, item.file, token, requestGeneration)
                    }
                } finally {
                    if (requestGeneration == generation) pending.remove(item.key)
                }
            }
        }
    }

    private suspend fun performDownload(server: Server, file: RemoteFile, token: String, request: Long) {
            setTransfer(file, Transfer.Running(0f))
            var lastUpdate = 0L
            val result = try {
                withContext(io) {
                    val context = coroutineContext
                    downloadAudio(server, token, file, { context.ensureActive() }) { progress ->
                        val now = System.currentTimeMillis()
                        if (now - lastUpdate > PROGRESS_INTERVAL_MS) {
                            lastUpdate = now
                            if (request == generation) setTransfer(file, Transfer.Running(progress))
                        }
                    }
                }
                if (withContext(io) { downloadAudio.isSynced(server, file) }) Transfer.Saved else Transfer.Failed("Arquivo salvo; sincronização indisponível neste PC.")
            } catch (e: CancellationException) {
                throw e
            } catch (_: NotAudioException) {
                Transfer.Failed(NOT_AUDIO)
            } catch (_: IOException) {
                Transfer.Failed(DOWNLOAD_FAILED)
            }
            if (request == generation) setTransfer(file, result)
    }

    override fun onCleared() {
        closeQueue()
        super.onCleared()
    }

    suspend fun cover(server: Server, file: RemoteFile): android.graphics.Bitmap? {
        val token = tokens.get(server.id) ?: return null
        return try {
            withContext(io) {
                connection.cover(server, token, file)?.let {
                    val bounds = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
                    android.graphics.BitmapFactory.decodeByteArray(it, 0, it.size, bounds)
                    var sample = 1
                    while (bounds.outWidth / sample > 512 || bounds.outHeight / sample > 512) sample *= 2
                    android.graphics.BitmapFactory.decodeByteArray(it, 0, it.size,
                        android.graphics.BitmapFactory.Options().apply { inSampleSize = sample })
                }
            }
        } catch (_: IOException) { null }
    }

    // --- estado

    private fun updateSearch(change: (Screen.Search) -> Screen.Search) {
        _screen.update { current -> if (current is Screen.Search) change(current) else current }
    }

    private fun updateFiles(change: (Screen.Files) -> Screen.Files) {
        _screen.update { current -> if (current is Screen.Files) change(current) else current }
    }

    private fun setTransfer(file: RemoteFile, transfer: Transfer) {
        updateFiles { state ->
            val current = state.files.firstOrNull { it.id == file.id }
            if (current == null || current.revision != file.revision || current.sha256 != file.sha256) state
            else state.copy(transfers = state.transfers + (file.id to transfer))
        }
    }

    companion object {
        fun factory(container: AppContainer): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                ReceiverViewModel(
                    container.discovery,
                    container.connection,
                    container.tokens,
                    container.downloadAudio,
                    container.deviceName,
                )
            }
        }
    }
}
