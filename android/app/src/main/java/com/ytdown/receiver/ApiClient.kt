package com.ytdown.receiver

import android.content.Context
import android.net.ConnectivityManager
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.io.OutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.SocketTimeoutException
import java.net.URL

private const val DISCOVERY_PORT = 47820
private const val DEFAULT_HTTP_PORT = 47821
private const val DISCOVERY_REQUEST = "YTDOWN_DISCOVER_V1"
private const val CONNECT_TIMEOUT_MS = 4_000
private const val READ_TIMEOUT_MS = 15_000

data class Server(val id: String, val name: String, val host: String, val port: Int)

data class RemoteFile(val id: String, val name: String, val size: Long)

/** O PC recusou o token: é preciso parear de novo. */
class NotPairedException : IOException()

/** O código digitado está errado. */
class WrongCodeException : IOException()

/** Fala com o servidor do ytDown no PC. Todas as funções bloqueiam: chame fora da thread principal. */
class ApiClient(private val context: Context) {

    /** Envia um pedido em broadcast na rede e devolve os PCs que responderem. */
    fun discover(): List<Server> {
        val found = linkedMapOf<String, Server>()
        DatagramSocket().use { socket ->
            socket.broadcast = true
            socket.soTimeout = 600
            val request = DISCOVERY_REQUEST.toByteArray()
            repeat(3) {
                for (address in broadcastAddresses()) {
                    try {
                        socket.send(DatagramPacket(request, request.size, address, DISCOVERY_PORT))
                    } catch (_: IOException) {
                        // Sem rede neste endereço; o outro pode funcionar.
                    }
                }
                try {
                    while (true) {
                        val packet = DatagramPacket(ByteArray(1024), 1024)
                        socket.receive(packet)
                        parseDiscoveryReply(packet)?.let { found[it.id] = it }
                    }
                } catch (_: SocketTimeoutException) {
                    // Fim das respostas desta rodada.
                }
            }
        }
        return found.values.toList()
    }

    private fun parseDiscoveryReply(packet: DatagramPacket): Server? {
        if (!packet.address.isSiteLocalAddress) return null
        return try {
            val text = String(packet.data, packet.offset, packet.length)
            parseServer(JSONObject(text), packet.address.hostAddress ?: return null)
        } catch (_: JSONException) {
            null
        }
    }

    private fun parseServer(json: JSONObject, host: String): Server? {
        if (json.optString("service") != "ytdown") return null
        return Server(json.getString("id"), json.getString("name"), host, json.getInt("port"))
    }

    private fun broadcastAddresses(): List<InetAddress> {
        val addresses = mutableListOf(InetAddress.getByName("255.255.255.255"))
        val manager = context.getSystemService(ConnectivityManager::class.java)
        manager.getLinkProperties(manager.activeNetwork)?.linkAddresses?.forEach { link ->
            val address = link.address.address
            if (address.size == 4) {
                val mask = -1 shl (32 - link.prefixLength)
                val ip = address.fold(0) { value, byte -> (value shl 8) or (byte.toInt() and 0xFF) }
                val broadcast = ip or mask.inv()
                addresses += InetAddress.getByAddress(
                    byteArrayOf(
                        (broadcast ushr 24).toByte(),
                        (broadcast ushr 16).toByte(),
                        (broadcast ushr 8).toByte(),
                        broadcast.toByte(),
                    ),
                )
            }
        }
        return addresses
    }

    /** Conecta a um endereço digitado, como "192.168.0.8" ou "192.168.0.8:47821". */
    fun connectManually(address: String): Server {
        val host = address.trim().substringBefore(':')
        val port = address.trim().substringAfter(':', "").toIntOrNull() ?: DEFAULT_HTTP_PORT
        val connection = open(Server("", "", host, port), "/api/info", token = null)
        try {
            val server = parseServer(JSONObject(readBody(connection)), host)
            return server?.copy(port = port) ?: throw IOException("Não é um ytDown")
        } catch (e: JSONException) {
            throw IOException("Não é um ytDown", e)
        } finally {
            connection.disconnect()
        }
    }

    /** Troca o código de pareamento por um token permanente. */
    fun pair(server: Server, code: String, device: String): String {
        val connection = open(server, "/api/pair", token = null, method = "POST")
        try {
            val body = JSONObject().put("code", code).put("device", device).toString().toByteArray()
            connection.doOutput = true
            connection.setFixedLengthStreamingMode(body.size)
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write(body) }
            if (connection.responseCode == HttpURLConnection.HTTP_FORBIDDEN) throw WrongCodeException()
            return JSONObject(readBody(connection)).getString("token")
        } catch (e: JSONException) {
            throw IOException("Resposta inválida", e)
        } finally {
            connection.disconnect()
        }
    }

    fun listFiles(server: Server, token: String): List<RemoteFile> {
        val connection = open(server, "/api/files", token)
        try {
            val files = JSONObject(readBody(connection)).getJSONArray("files")
            return List(files.length()) { index ->
                val file = files.getJSONObject(index)
                RemoteFile(file.getString("id"), file.getString("name"), file.getLong("size"))
            }
        } catch (e: JSONException) {
            throw IOException("Resposta inválida", e)
        } finally {
            connection.disconnect()
        }
    }

    /** Copia o arquivo para `output`. Falha se chegar menos que o tamanho anunciado pelo PC. */
    fun download(
        server: Server,
        token: String,
        file: RemoteFile,
        output: OutputStream,
        onProgress: (Long, Long) -> Unit,
    ) {
        val connection = open(server, "/api/files/${file.id}", token)
        try {
            checkStatus(connection)
            val expected = connection.contentLengthLong
            var received = 0L
            connection.inputStream.use { input ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    output.write(buffer, 0, count)
                    received += count
                    onProgress(received, expected)
                }
            }
            if (expected >= 0 && received != expected) throw IOException("Transferência incompleta")
        } finally {
            connection.disconnect()
        }
    }

    private fun open(server: Server, path: String, token: String?, method: String = "GET"): HttpURLConnection {
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
