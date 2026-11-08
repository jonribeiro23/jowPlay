package com.ytdown.receiver.data.network

import android.content.Context
import android.net.ConnectivityManager
import com.ytdown.receiver.domain.ServerDiscovery
import com.ytdown.receiver.domain.model.Server
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.SocketTimeoutException

private const val ROUNDS = 3
private const val ROUND_TIMEOUT_MS = 600

/** Envia um pedido em broadcast na rede e coleta os PCs que responderem. */
class UdpServerDiscovery(private val context: Context) : ServerDiscovery {

    override fun discover(): List<Server> {
        val found = linkedMapOf<String, Server>()
        DatagramSocket().use { socket ->
            socket.broadcast = true
            socket.soTimeout = ROUND_TIMEOUT_MS
            repeat(ROUNDS) {
                sendRequests(socket)
                collectReplies(socket) { server -> found[server.id] = server }
            }
        }
        return found.values.toList()
    }

    private fun sendRequests(socket: DatagramSocket) {
        val request = DISCOVERY_REQUEST.toByteArray()
        for (address in broadcastAddresses()) {
            try {
                socket.send(DatagramPacket(request, request.size, address, DISCOVERY_PORT))
            } catch (_: IOException) {
                // Sem rede neste endereço; o outro pode funcionar.
            }
        }
    }

    private fun collectReplies(socket: DatagramSocket, onServer: (Server) -> Unit) {
        try {
            while (true) {
                val packet = DatagramPacket(ByteArray(1024), 1024)
                socket.receive(packet)
                parseReply(packet)?.let(onServer)
            }
        } catch (_: SocketTimeoutException) {
            // Fim das respostas desta rodada.
        }
    }

    private fun parseReply(packet: DatagramPacket): Server? {
        // Uma resposta de fora da rede local nunca é de um PC confiável.
        if (!packet.address.isSiteLocalAddress) return null
        val host = packet.address.hostAddress ?: return null
        return try {
            parseServer(JSONObject(String(packet.data, packet.offset, packet.length)), host)
        } catch (_: JSONException) {
            null
        }
    }

    /** O broadcast geral e o da sub-rede atual: alguns roteadores só repassam um deles. */
    private fun broadcastAddresses(): List<InetAddress> {
        val addresses = mutableListOf(InetAddress.getByName("255.255.255.255"))
        val manager = context.getSystemService(ConnectivityManager::class.java)
        manager.getLinkProperties(manager.activeNetwork)?.linkAddresses?.forEach { link ->
            val address = link.address.address
            if (address.size == 4) {
                addresses += subnetBroadcast(address, link.prefixLength)
            }
        }
        return addresses
    }

    private fun subnetBroadcast(address: ByteArray, prefixLength: Int): InetAddress {
        val mask = -1 shl (32 - prefixLength)
        val ip = address.fold(0) { value, byte -> (value shl 8) or (byte.toInt() and 0xFF) }
        val broadcast = ip or mask.inv()
        return InetAddress.getByAddress(
            byteArrayOf(
                (broadcast ushr 24).toByte(),
                (broadcast ushr 16).toByte(),
                (broadcast ushr 8).toByte(),
                broadcast.toByte(),
            ),
        )
    }
}
