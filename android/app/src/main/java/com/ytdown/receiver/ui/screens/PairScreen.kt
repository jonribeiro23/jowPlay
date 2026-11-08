package com.ytdown.receiver.ui.screens

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.ytdown.receiver.ui.ReceiverViewModel
import com.ytdown.receiver.ui.Screen
import com.ytdown.receiver.ui.components.AppScaffold

private const val CODE_LENGTH = 6

@Composable
fun PairScreen(screen: Screen.Pair, viewModel: ReceiverViewModel) {
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
