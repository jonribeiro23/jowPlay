package com.ytdown.receiver.data.storage

import android.content.Context
import com.ytdown.receiver.domain.PairingTokens

/** Guarda um token por PC. O backup automático está desligado no manifesto. */
class SharedPreferencesPairingTokens(context: Context) : PairingTokens {
    // O nome do arquivo não pode mudar: é onde as versões anteriores guardaram os pareamentos.
    private val preferences = context.getSharedPreferences("paired_servers", Context.MODE_PRIVATE)

    override fun get(serverId: String): String? = preferences.getString(serverId, null)

    override fun save(serverId: String, token: String) {
        preferences.edit().putString(serverId, token).apply()
    }

    override fun remove(serverId: String) {
        preferences.edit().remove(serverId).apply()
    }
}
