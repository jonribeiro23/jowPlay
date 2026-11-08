package com.ytdown.receiver.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.ytdown.receiver.ui.ReceiverViewModel
import com.ytdown.receiver.ui.Screen
import com.ytdown.receiver.ui.components.AppScaffold
import com.ytdown.receiver.ui.components.WhileResumed

@Composable
fun SearchScreen(screen: Screen.Search, viewModel: ReceiverViewModel) {
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
