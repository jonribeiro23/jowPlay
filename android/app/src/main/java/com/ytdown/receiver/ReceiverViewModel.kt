package com.ytdown.receiver

import android.app.Application
import android.content.Context
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
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

sealed interface Transfer {
    data class Running(val progress: Float) : Transfer
    data object Saved : Transfer
    data class Failed(val message: String) : Transfer
}

sealed interface Screen {
    data class Search(
        val servers: List<Server> = emptyList(),
        val busy: Boolean = false,
        val message: String? = null,
    ) : Screen

    data class Pair(val server: Server, val busy: Boolean = false, val message: String? = null) : Screen

    data class Files(
        val server: Server,
        val files: List<RemoteFile> = emptyList(),
        val transfers: Map<String, Transfer> = emptyMap(),
        val connected: Boolean = true,
    ) : Screen
}

class ReceiverViewModel(application: Application) : AndroidViewModel(application) {
    private val api = ApiClient(application)
    private val storage = AudioStorage(application)
    private val tokens = application.getSharedPreferences("paired_servers", Context.MODE_PRIVATE)

    private val _screen = MutableStateFlow<Screen>(Screen.Search())
    val screen: StateFlow<Screen> = _screen.asStateFlow()

    /** Falso depois de "Trocar de PC", para o app não voltar sozinho ao mesmo PC. */
    private var autoConnect = true

    private fun token(server: Server): String? = tokens.getString(server.id, null)

    /** Procura PCs enquanto a tela de busca estiver aberta. */
    suspend fun searchLoop() {
        while (coroutineContext.isActive && _screen.value is Screen.Search) {
            val servers = try {
                withContext(Dispatchers.IO) { api.discover() }
            } catch (_: IOException) {
                emptyList()
            }
            val only = servers.singleOrNull()
            if (autoConnect && only != null && token(only) != null) {
                open(only)
                return
            }
            _screen.update { current ->
                if (current is Screen.Search) current.copy(servers = servers) else current
            }
            delay(2_000)
        }
    }

    fun open(server: Server) {
        _screen.value = if (token(server) != null) Screen.Files(server) else Screen.Pair(server)
    }

    fun connectManually(address: String) {
        _screen.update { current -> if (current is Screen.Search) current.copy(busy = true, message = null) else current }
        viewModelScope.launch {
            try {
                open(withContext(Dispatchers.IO) { api.connectManually(address) })
            } catch (_: IOException) {
                _screen.update { current ->
                    if (current is Screen.Search) {
                        current.copy(
                            busy = false,
                            message = "Não foi possível conectar. Confira o endereço e se a janela " +
                                "\"Enviar para o celular\" está aberta no PC.",
                        )
                    } else {
                        current
                    }
                }
            }
        }
    }

    fun pair(server: Server, code: String) {
        _screen.value = Screen.Pair(server, busy = true)
        viewModelScope.launch {
            try {
                val device = "${Build.MANUFACTURER} ${Build.MODEL}"
                val token = withContext(Dispatchers.IO) { api.pair(server, code, device) }
                tokens.edit().putString(server.id, token).apply()
                _screen.value = Screen.Files(server)
            } catch (_: WrongCodeException) {
                _screen.value = Screen.Pair(server, message = "Código incorreto. Confira o código na tela do PC.")
            } catch (_: IOException) {
                _screen.value = Screen.Pair(server, message = "Sem conexão com o PC. Tente de novo.")
            }
        }
    }

    fun backToSearch() {
        autoConnect = false
        _screen.value = Screen.Search()
    }

    /** Atualiza a lista enquanto a tela de arquivos estiver aberta. */
    suspend fun filesLoop(server: Server) {
        while (coroutineContext.isActive && (_screen.value as? Screen.Files)?.server == server) {
            val token = token(server)
            if (token == null) {
                _screen.value = Screen.Pair(server)
                return
            }
            try {
                val files = withContext(Dispatchers.IO) { api.listFiles(server, token) }
                updateFiles { it.copy(files = files, connected = true) }
            } catch (_: NotPairedException) {
                tokens.edit().remove(server.id).apply()
                _screen.value = Screen.Pair(server, message = "O PC pediu um novo pareamento.")
                return
            } catch (_: IOException) {
                updateFiles { it.copy(connected = false) }
            }
            delay(2_000)
        }
    }

    private fun updateFiles(change: (Screen.Files) -> Screen.Files) {
        _screen.update { current -> if (current is Screen.Files) change(current) else current }
    }

    private fun setTransfer(file: RemoteFile, transfer: Transfer) {
        updateFiles { it.copy(transfers = it.transfers + (file.id to transfer)) }
    }

    fun download(server: Server, file: RemoteFile) {
        val token = token(server) ?: return
        val name = safeAudioName(file.name)
        val mimeType = name?.let(::mimeTypeFor)
        if (name == null || mimeType == null) {
            setTransfer(file, Transfer.Failed("O PC enviou um arquivo que não é de áudio."))
            return
        }
        setTransfer(file, Transfer.Running(0f))
        viewModelScope.launch {
            var lastUpdate = 0L
            try {
                withContext(Dispatchers.IO) {
                    storage.save(name, mimeType) { output ->
                        api.download(server, token, file, output) { received, total ->
                            val now = System.currentTimeMillis()
                            if (total > 0 && now - lastUpdate > 100) {
                                lastUpdate = now
                                setTransfer(file, Transfer.Running(received.toFloat() / total))
                            }
                        }
                    }
                }
                setTransfer(file, Transfer.Saved)
            } catch (e: CancellationException) {
                throw e
            } catch (_: IOException) {
                setTransfer(file, Transfer.Failed("A transferência falhou. Tente de novo."))
            }
        }
    }
}
