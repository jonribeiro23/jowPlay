package com.ytdown.receiver.data.network

import com.ytdown.receiver.domain.model.Server
import org.json.JSONObject

/** Constantes e formato do protocolo entre o app e o ytDown do PC (ver README do projeto). */
internal const val DISCOVERY_PORT = 47820
internal const val DEFAULT_HTTP_PORT = 47821
internal const val DISCOVERY_REQUEST = "YTDOWN_DISCOVER_V1"

/** Lê a identificação do PC; devolve null se a resposta não for de um ytDown. */
internal fun parseServer(json: JSONObject, host: String): Server? {
    if (json.optString("service") != "ytdown") return null
    return Server(json.getString("id"), json.getString("name"), host, json.getInt("port"))
}
