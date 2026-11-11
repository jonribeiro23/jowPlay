package com.ytdown.receiver.data.storage

import android.content.ContentValues
import android.content.Context
import android.os.Environment
import android.provider.MediaStore
import com.ytdown.receiver.domain.AudioLibrary
import java.io.IOException
import java.io.OutputStream
import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.domain.model.Server
import java.security.MessageDigest
import java.util.UUID
import org.json.JSONObject

/** Salva áudios em Música/ytDown, onde os players do celular os encontram. */
class MediaStoreAudioLibrary(context: Context) : AudioLibrary {
    private val resolver = context.contentResolver
    private val associations = context.getSharedPreferences("download_associations", Context.MODE_PRIVATE)

    private fun key(server: Server, file: RemoteFile): String =
        MessageDigest.getInstance("SHA-256").digest((server.id.length.toString() + ":" + server.id + file.id).toByteArray())
            .joinToString("") { "%02x".format(it) }

    override fun isSynced(server: Server, file: RemoteFile): Boolean {
        val revision = file.revision?.takeIf { it.matches(Regex("[0-9a-fA-F]{64}")) } ?: return false
        val expected = file.sha256?.takeIf { it.matches(Regex("[0-9a-fA-F]{64}")) } ?: return false
        return try {
            val record = JSONObject(associations.getString(key(server, file), null) ?: return false)
            if (record.getString("revision") != revision || !record.getString("sha256").equals(expected, true)) return false
            val digest = MessageDigest.getInstance("SHA-256")
            var size = 0L
            val input = resolver.openInputStream(android.net.Uri.parse(record.getString("uri"))) ?: return false
            input.use {
                val buffer = ByteArray(65536)
                while (true) {
                    val count = it.read(buffer)
                    if (count < 0) break
                    size += count
                    digest.update(buffer, 0, count)
                }
            }
            size == file.size && digest.digest().joinToString("") { "%02x".format(it) }.equals(expected, true)
        } catch (_: Exception) { false }
    }

    override fun saveFor(server: Server, file: RemoteFile, name: String, mimeType: String, write: (OutputStream) -> Unit) {
        val suffix = UUID.randomUUID().toString()
        val uniqueName = name.substringBeforeLast('.', name) + "-" + suffix + "." + name.substringAfterLast('.')
        saveInternal(uniqueName, mimeType, write) { uri ->
            if (file.revision?.matches(Regex("[0-9a-fA-F]{64}")) == true && file.sha256?.matches(Regex("[0-9a-fA-F]{64}")) == true) {
                val record = JSONObject().put("uri", uri.toString()).put("revision", file.revision).put("sha256", file.sha256)
                if (!associations.edit().putString(key(server, file), record.toString()).commit()) throw IOException("Falha ao salvar associação")
            }
        }
    }

    /** Enquanto `write` roda, o arquivo fica oculto; se falhar, nada fica salvo. */
    override fun save(name: String, mimeType: String, write: (OutputStream) -> Unit) {
        saveInternal(name, mimeType, write) { }
    }

    private fun saveInternal(name: String, mimeType: String, write: (OutputStream) -> Unit, associate: (android.net.Uri) -> Unit) {
        val values = ContentValues().apply {
            put(MediaStore.Audio.Media.DISPLAY_NAME, name)
            put(MediaStore.Audio.Media.MIME_TYPE, mimeType)
            put(MediaStore.Audio.Media.RELATIVE_PATH, "${Environment.DIRECTORY_MUSIC}/ytDown")
            put(MediaStore.Audio.Media.IS_PENDING, 1)
        }
        val collection = MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val uri = resolver.insert(collection, values) ?: throw IOException("Não foi possível criar o arquivo")
        try {
            val output = resolver.openOutputStream(uri) ?: throw IOException("Não foi possível abrir o arquivo")
            output.use(write)
            if (resolver.update(uri, ContentValues().apply { put(MediaStore.Audio.Media.IS_PENDING, 0) }, null, null) != 1) throw IOException("Falha ao publicar arquivo")
            associate(uri)
        } catch (failure: Throwable) {
            resolver.delete(uri, null, null)
            throw failure
        }
    }
}
