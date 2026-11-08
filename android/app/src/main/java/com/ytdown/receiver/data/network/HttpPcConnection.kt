package com.ytdown.receiver.data.network

import com.ytdown.receiver.domain.NotPairedException
import com.ytdown.receiver.domain.PcConnection
import com.ytdown.receiver.domain.WrongCodeException
import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.domain.model.Server
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL

private const val CONNECT_TIMEOUT_MS = 4_000
private const val READ_TIMEOUT_MS = 15_000
private const val BUFFER_SIZE = 64 * 1024

/** Fala com o servidor HTTP do ytDown no PC. */
class HttpPcConnection : PcConnection {

    override fun connectManually(address: String): Server {
        val host = address.trim().substringBefore(':')
        val port = address.trim().substringAfter(':', "").toIntOrNull() ?: DEFAULT_HTTP_PORT
        return request(Server("", "", host, port), "/api/info") { connection ->
            val server = parseServer(JSONObject(readBody(connection)), host)
            server?.copy(port = port) ?: throw IOException("Não é um ytDown")
        }
    }

    override fun pair(server: Server, code: String, device: String): String =
        request(server, "/api/pair", method = "POST") { connection ->
            val body = JSONObject().put("code", code).put("device", device).toString().toByteArray()
            connection.doOutput = true
            connection.setFixedLengthStreamingMode(body.size)
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write(body) }
            if (connection.responseCode == HttpURLConnection.HTTP_FORBIDDEN) throw WrongCodeException()
            JSONObject(readBody(connection)).getString("token")
        }

    override fun listFiles(server: Server, token: String): List<RemoteFile> =
        request(server, "/api/files", token) { connection ->
            val files = JSONObject(readBody(connection)).getJSONArray("files")
            List(files.length()) { index ->
                val file = files.getJSONObject(index)
                RemoteFile(file.getString("id"), file.getString("name"), file.getLong("size"))
            }
        }

    /** Falha se chegar menos que o tamanho anunciado pelo PC. */
    override fun download(
        server: Server,
        token: String,
        file: RemoteFile,
        output: OutputStream,
        onProgress: (Long, Long) -> Unit,
    ) = request(server, "/api/files/${file.id}", token) { connection ->
        checkStatus(connection)
        val expected = connection.contentLengthLong
        var received = 0L
        connection.inputStream.use { input ->
            val buffer = ByteArray(BUFFER_SIZE)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                output.write(buffer, 0, count)
                received += count
                onProgress(received, expected)
            }
        }
        if (expected >= 0 && received != expected) throw IOException("Transferência incompleta")
    }

    /** Abre a conexão, executa `block` e sempre desconecta. JSON inválido vira IOException. */
    private fun <T> request(
        server: Server,
        path: String,
        token: String? = null,
        method: String = "GET",
        block: (HttpURLConnection) -> T,
    ): T {
        val connection = open(server, path, token, method)
        try {
            return block(connection)
        } catch (e: JSONException) {
            throw IOException("Resposta inválida", e)
        } finally {
            connection.disconnect()
        }
    }

    private fun open(server: Server, path: String, token: String?, method: String): HttpURLConnection {
        // Impede que um endereço digitado ou uma resposta forjada leve o app para fora da rede local.
        if (!InetAddress.getByName(server.host).isSiteLocalAddress) {
            throw IOException("O endereço não é da rede local")
        }
        val connection = URL("http", server.host, server.port, path).openConnection() as HttpURLConnection
        connection.connectTimeout = CONNECT_TIMEOUT_MS
        connection.readTimeout = READ_TIMEOUT_MS
        connection.requestMethod = method
        connection.instanceFollowRedirects = false
        if (token != null) connection.setRequestProperty("Authorization", "Bearer $token")
        return connection
    }

    private fun readBody(connection: HttpURLConnection): String {
        checkStatus(connection)
        return connection.inputStream.bufferedReader().use { it.readText() }
    }

    private fun checkStatus(connection: HttpURLConnection) {
        when (connection.responseCode) {
            HttpURLConnection.HTTP_OK -> Unit
            HttpURLConnection.HTTP_UNAUTHORIZED -> throw NotPairedException()
            else -> throw IOException("O PC respondeu com o erro ${connection.responseCode}")
        }
    }
}
