package com.ytdown.receiver.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.ui.*
import com.ytdown.receiver.ui.components.AppScaffold
import kotlin.math.roundToInt

@Composable
fun FilesScreen(screen: Screen.Files, viewModel: ReceiverViewModel) {
    AppScaffold(
        title = screen.server.name,
        action = { TextButton(onClick = viewModel::backToSearch) { Text("Trocar de PC") } },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            StatusMessage(screen)
            LazyVerticalGrid(
                columns = GridCells.Adaptive(minSize = 150.dp),
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(screen.files, key = { it.id }) { file ->
                    FileCard(file, screen, viewModel) { viewModel.download(screen.server, file) }
                }
            }
        }
    }
}

@Composable
private fun StatusMessage(screen: Screen.Files) {
    val message = when {
        screen.connection == ConnectionState.CONNECTING -> "Conectando ao PC..."
        screen.connection == ConnectionState.DISCONNECTED -> "Sem conexão com o PC. Verifique se o ytDown está aberto e se o celular está no Wi-Fi da mesma rede."
        screen.files.isEmpty() -> "Nenhum áudio disponível. No PC, clique em \"Enviar para o celular\" depois de extrair um áudio."
        else -> null
    }
    if (message != null) Text(
        message, Modifier.fillMaxWidth().padding(16.dp).semantics { liveRegion = LiveRegionMode.Polite },
        color = if (screen.connection == ConnectionState.DISCONNECTED) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface,
    )
}

@Composable
private fun FileCard(file: RemoteFile, screen: Screen.Files, viewModel: ReceiverViewModel, onDownload: () -> Unit) {
    val connected = screen.connection == ConnectionState.CONNECTED
    val transfer = screen.transfers[file.id]
    val synced = transfer == Transfer.Saved || file.id in screen.synced
    val enabled = connected && !synced && transfer !is Transfer.Queued && transfer !is Transfer.Running
    val status = when {
        synced -> "Sincronizado"
        transfer is Transfer.Queued -> "Download na fila"
        transfer is Transfer.Running -> "Baixando ${ (transfer.progress.coerceIn(0f, 1f) * 100).roundToInt() }%"
        transfer is Transfer.Failed -> "Falha no download. Toque para tentar novamente"
        else -> "Fazer Download"
    }
    val cover by produceState<android.graphics.Bitmap?>(null, screen.server, file.id, file.coverRevision, connected) {
        value = if (connected && file.coverRevision != null) viewModel.cover(screen.server, file) else null
    }
    Card(Modifier.fillMaxWidth()) {
        Column {
            Box(
                Modifier.fillMaxWidth().aspectRatio(1f)
                    .background(MaterialTheme.colorScheme.secondaryContainer)
                    .clickable(enabled = enabled, onClickLabel = "Fazer Download de ${file.title}", onClick = onDownload)
                    .semantics { contentDescription = "${file.title}. $status"; liveRegion = LiveRegionMode.Polite },
            ) {
                if (cover != null) Image(cover!!.asImageBitmap(), contentDescription = null, modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                else Text("♫", Modifier.align(Alignment.Center), style = MaterialTheme.typography.displayLarge)
                Column(Modifier.align(Alignment.BottomCenter).fillMaxWidth().background(Color.Black.copy(alpha = 0.78f)).padding(8.dp)) {
                    Text(status, color = Color.White, style = MaterialTheme.typography.labelMedium)
                    if (transfer is Transfer.Running) LinearProgressIndicator(
                        progress = { transfer.progress.coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                    )
                }
            }
            Column(Modifier.padding(10.dp)) {
                Text(file.title, style = MaterialTheme.typography.titleSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(file.artist.ifBlank { "Artista desconhecido" }, style = MaterialTheme.typography.bodySmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                if (transfer is Transfer.Failed && !synced) Text(transfer.message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
