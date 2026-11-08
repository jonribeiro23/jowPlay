package com.ytdown.receiver

import android.content.Context
import android.os.Build
import com.ytdown.receiver.data.network.HttpPcConnection
import com.ytdown.receiver.data.network.UdpServerDiscovery
import com.ytdown.receiver.data.storage.MediaStoreAudioLibrary
import com.ytdown.receiver.data.storage.SharedPreferencesPairingTokens
import com.ytdown.receiver.domain.PairingTokens
import com.ytdown.receiver.domain.PcConnection
import com.ytdown.receiver.domain.ServerDiscovery
import com.ytdown.receiver.domain.usecase.DownloadAudio

/** Ponto de montagem: escolhe as implementações concretas e as entrega a quem usa. */
class AppContainer(context: Context) {
    val discovery: ServerDiscovery = UdpServerDiscovery(context)
    val connection: PcConnection = HttpPcConnection()
    val tokens: PairingTokens = SharedPreferencesPairingTokens(context)
    val downloadAudio = DownloadAudio(connection, MediaStoreAudioLibrary(context))

    /** Como o celular aparece na lista de pareados do PC. */
    val deviceName = "${Build.MANUFACTURER} ${Build.MODEL}"
}
