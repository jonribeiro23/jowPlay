package com.ytdown.receiver

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.ytdown.receiver.ui.ReceiverViewModel
import com.ytdown.receiver.ui.Screen
import com.ytdown.receiver.ui.Transfer
import com.ytdown.receiver.ui.screens.FilesScreen
import com.ytdown.receiver.ui.screens.PairScreen
import com.ytdown.receiver.ui.screens.SearchScreen
import com.ytdown.receiver.ui.theme.YtDownTheme

class MainActivity : ComponentActivity() {
    private val viewModel: ReceiverViewModel by viewModels {
        ReceiverViewModel.factory(AppContainer(applicationContext))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            YtDownTheme {
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
