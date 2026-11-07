package com.ytdown.receiver

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle

private const val CODE_LENGTH = 6
private val BrandRed = Color(0xFFC82630)

class MainActivity : ComponentActivity() {
    private val viewModel: ReceiverViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val scheme = if (isSystemInDarkTheme()) {
                darkColorScheme(primary = Color(0xFFFFB3B0), onPrimary = Color(0xFF68000F))
            } else {
                lightColorScheme(primary = BrandRed, onPrimary = Color.White)
            }
            MaterialTheme(colorScheme = scheme) {
                val screen by viewModel.screen.collectAsStateWithLifecycle()
                val current = screen
                keepScreenOnDuringTransfers(current)
                when (current) {
                    is Screen.Search -> SearchScreen(current, viewModel)
                    is Screen.Pair -> PairScreen(current, viewModel)
                    is Screen.Files -> FilesScreen(current, viewModel)
                }
            }
        }
    }

    /** Com a tela apagada, o Android pode desligar o Wi-Fi e interromper o download. */
    private fun keepScreenOnDuringTransfers(screen: Screen) {
        val running = screen is Screen.Files && screen.transfers.values.any { it is Transfer.Running }
        if (running) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }
}

/** Repete `block` só enquanto o app estiver na frente, para não gastar bateria. */
@Composable
private fun WhileResumed(key: Any, block: suspend () -> Unit) {
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(key, lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.RESUMED) { block() }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AppScaffold(
    title: String,
    action: @Composable () -> Unit = {},
    content: @Composable (PaddingValues) -> Unit,
) {
    Scaffold(
        topBar = { TopAppBar(title = { Text(title) }, actions = { action() }) },
        content = content,
    )
}

@Composable
private fun SearchScreen(screen: Screen.Search, viewModel: ReceiverViewModel) {
    WhileResumed("search") { viewModel.searchLoop() }
    var address by rememberSaveable { mutableStateOf("") }

    AppScaffold("ytDown") { padding ->
        Column(
            Modifier
                .padding(padding)
                .padding(16.dp)
                .fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Escolha o PC", style = MaterialTheme.typography.titleLarge)
            if (screen.servers.isEmpty()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    Text("Procurando na rede...", Modifier.padding(start = 12.dp))
                }
                Text(
                    "No PC, extraia um áudio e clique em \"Enviar para o celular\". " +
                        "O celular precisa estar no Wi-Fi da mesma rede.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            screen.servers.forEach { server ->
                OutlinedButton(onClick = { viewModel.open(server) }, Modifier.fillMaxWidth()) {
                    Text("${server.name} (${server.host})")
                }
            }

            Text(
                "Não encontrou o PC? Digite o endereço mostrado na janela \"Enviar para o celular\".",
                Modifier.padding(top = 16.dp),
                style = MaterialTheme.typography.bodyMedium,
            )
            OutlinedTextField(
                value = address,
                onValueChange = { address = it },
                label = { Text("Endereço do PC") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = { viewModel.connectManually(address) },
                enabled = address.isNotBlank() && !screen.busy,
            ) {
                Text(if (screen.busy) "Conectando..." else "Conectar")
            }
            screen.message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
private fun PairScreen(screen: Screen.Pair, viewModel: ReceiverViewModel) {
    BackHandler { viewModel.backToSearch() }
    var code by rememberSaveable { mutableStateOf("") }

    AppScaffold(screen.server.name) { padding ->
        Column(
            Modifier
                .padding(padding)
                .padding(16.dp)
                .fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Parear com este PC", style = MaterialTheme.typography.titleLarge)
            Text("Digite o código de 6 dígitos mostrado na janela \"Enviar para o celular\". Isso só é preciso uma vez.")
            OutlinedTextField(
                value = code,
                onValueChange = { typed -> code = typed.filter(Char::isDigit).take(CODE_LENGTH) },
                label = { Text("Código") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = { viewModel.pair(screen.server, code) },
                enabled = code.length == CODE_LENGTH && !screen.busy,
            ) {
                Text(if (screen.busy) "Pareando..." else "Parear")
            }
            screen.message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            TextButton(onClick = viewModel::backToSearch) { Text("Voltar") }
        }
    }
}

@Composable
private fun FilesScreen(screen: Screen.Files, viewModel: ReceiverViewModel) {
    WhileResumed(screen.server) { viewModel.filesLoop(screen.server) }

    AppScaffold(
        title = screen.server.name,
        action = { TextButton(onClick = viewModel::backToSearch) { Text("Trocar de PC") } },
    ) { padding ->
        Column(
            Modifier
                .padding(padding)
                .padding(horizontal = 16.dp)
                .fillMaxSize(),
        ) {
            if (!screen.connected) {
                Text(
                    "Sem conexão com o PC. Verifique se a janela \"Enviar para o celular\" está aberta e " +
                        "se o celular está no Wi-Fi da mesma rede.",
                    Modifier.padding(vertical = 8.dp),
                    color = MaterialTheme.colorScheme.error,
                )
            } else if (screen.files.isEmpty()) {
                Text(
                    "Nenhum áudio disponível. No PC, clique em \"Enviar para o celular\" depois de extrair um áudio.",
                    Modifier.padding(vertical = 8.dp),
                )
            }
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(vertical = 8.dp),
            ) {
                items(screen.files, key = { it.id }) { file ->
                    FileCard(file, screen.transfers[file.id], screen.connected) {
                        viewModel.download(screen.server, file)
                    }
                }
            }
        }
    }
}

@Composable
private fun FileCard(file: RemoteFile, transfer: Transfer?, connected: Boolean, onDownload: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(file.name, style = MaterialTheme.typography.titleMedium)
            Text(formatSize(file.size), style = MaterialTheme.typography.bodySmall)
            when (transfer) {
                is Transfer.Running -> LinearProgressIndicator(
                    progress = { transfer.progress },
                    modifier = Modifier.fillMaxWidth(),
                )
                Transfer.Saved -> {
                    Text("Salvo em Música/ytDown", color = MaterialTheme.colorScheme.primary)
                    OutlinedButton(onClick = onDownload, enabled = connected) { Text("Baixar de novo") }
                }
                is Transfer.Failed -> {
                    Text(transfer.message, color = MaterialTheme.colorScheme.error)
                    Button(onClick = onDownload, enabled = connected) { Text("Tentar de novo") }
                }
                null -> Button(onClick = onDownload, enabled = connected) { Text("Baixar") }
            }
        }
    }
}
