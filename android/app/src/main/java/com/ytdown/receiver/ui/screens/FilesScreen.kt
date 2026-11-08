package com.ytdown.receiver.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.ui.ReceiverViewModel
import com.ytdown.receiver.ui.Screen
import com.ytdown.receiver.ui.Transfer
import com.ytdown.receiver.ui.components.AppScaffold
import com.ytdown.receiver.ui.components.WhileResumed
import com.ytdown.receiver.ui.formatSize

@Composable
fun FilesScreen(screen: Screen.Files, viewModel: ReceiverViewModel) {
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
            StatusMessage(screen)
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
private fun StatusMessage(screen: Screen.Files) {
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
