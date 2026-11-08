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
import kotlinx.coroutines.withContext
import java.io.IOException
import kotlin.coroutines.coroutineContext

private const val POLL_INTERVAL_MS = 2_000L
private const val PROGRESS_INTERVAL_MS = 100L

private const val MANUAL_CONNECT_FAILED =
    "Não foi possível conectar. Confira o endereço e se a janela \"Enviar para o celular\" está aberta no PC."
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
) : ViewModel() {

    private val _screen = MutableStateFlow<Screen>(Screen.Search())
    val screen: StateFlow<Screen> = _screen.asStateFlow()

    /** Falso depois de "Trocar de PC", para o app não voltar sozinho ao mesmo PC. */
    private var autoConnect = true

    // --- busca

    /** Procura PCs enquanto a tela de busca estiver aberta. */
    suspend fun searchLoop() {
        while (coroutineContext.isActive && _screen.value is Screen.Search) {
            val servers = try {
                withContext(Dispatchers.IO) { discovery.discover() }
            } catch (_: IOException) {
                emptyList()
            }
            val only = servers.singleOrNull()
            if (autoConnect && only != null && tokens.get(only.id) != null) {
                open(only)
                return
            }
            updateSearch { it.copy(servers = servers) }
            delay(POLL_INTERVAL_MS)
        }
    }

    fun open(server: Server) {
        _screen.value = if (tokens.get(server.id) != null) Screen.Files(server) else Screen.Pair(server)
    }

    fun connectManually(address: String) {
        updateSearch { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            try {
                open(withContext(Dispatchers.IO) { connection.connectManually(address) })
            } catch (_: IOException) {
                updateSearch { it.copy(busy = false, message = MANUAL_CONNECT_FAILED) }
            }
        }
    }

    fun backToSearch() {
        autoConnect = false
        _screen.value = Screen.Search()
    }

    // --- pareamento

    fun pair(server: Server, code: String) {
        _screen.value = Screen.Pair(server, busy = true)
        viewModelScope.launch {
            _screen.value = try {
                val token = withContext(Dispatchers.IO) { connection.pair(server, code, deviceName) }
                tokens.save(server.id, token)
                Screen.Files(server)
            } catch (_: WrongCodeException) {
                Screen.Pair(server, message = WRONG_CODE)
            } catch (_: IOException) {
                Screen.Pair(server, message = NO_CONNECTION)
            }
        }
    }

    // --- arquivos

    /** Atualiza a lista enquanto a tela de arquivos estiver aberta. */
    suspend fun filesLoop(server: Server) {
        while (coroutineContext.isActive && (_screen.value as? Screen.Files)?.server == server) {
            val token = tokens.get(server.id)
            if (token == null) {
                _screen.value = Screen.Pair(server)
                return
            }
            try {
                val files = withContext(Dispatchers.IO) { connection.listFiles(server, token) }
                updateFiles { it.copy(files = files, connected = true) }
            } catch (_: NotPairedException) {
                tokens.remove(server.id)
                _screen.value = Screen.Pair(server, message = PAIR_AGAIN)
                return
            } catch (_: IOException) {
                updateFiles { it.copy(connected = false) }
            }
            delay(POLL_INTERVAL_MS)
        }
    }

    fun download(server: Server, file: RemoteFile) {
        val token = tokens.get(server.id) ?: return
        setTransfer(file, Transfer.Running(0f))
        viewModelScope.launch {
            var lastUpdate = 0L
            val result = try {
                withContext(Dispatchers.IO) {
                    downloadAudio(server, token, file) { progress ->
                        val now = System.currentTimeMillis()
                        if (now - lastUpdate > PROGRESS_INTERVAL_MS) {
                            lastUpdate = now
                            setTransfer(file, Transfer.Running(progress))
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
            setTransfer(file, result)
        }
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
