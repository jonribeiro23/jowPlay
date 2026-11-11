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
                val files = withContext(io) { connection.listFiles(server, token) }
                if (request != generation) return
                updateFiles { it.copy(server = server, files = files, connection = ConnectionState.CONNECTED) }
            } catch (_: NotPairedException) {
                if (request != generation) return
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
        val token = tokens.get(server.id) ?: return
        val request = generation
        setTransfer(file, Transfer.Running(0f))
        viewModelScope.launch {
            var lastUpdate = 0L
            val result = try {
                withContext(io) {
                    downloadAudio(server, token, file) { progress ->
                        val now = System.currentTimeMillis()
                        if (now - lastUpdate > PROGRESS_INTERVAL_MS) {
                            lastUpdate = now
                            if (request == generation) setTransfer(file, Transfer.Running(progress))
                        }
                    }
                }
                Transfer.Saved
            } catch (e: CancellationException) {
                throw e
            } catch (_: NotAudioException) {
                Transfer.Failed(NOT_AUDIO)
            } catch (_: IOException) {
                Transfer.Failed(DOWNLOAD_FAILED)
            }
            if (request == generation) setTransfer(file, result)
        }
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
        updateFiles { it.copy(transfers = it.transfers + (file.id to transfer)) }
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
