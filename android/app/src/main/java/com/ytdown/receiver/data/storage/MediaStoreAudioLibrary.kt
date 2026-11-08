package com.ytdown.receiver.data.storage

import android.content.ContentValues
import android.content.Context
import android.os.Environment
import android.provider.MediaStore
import com.ytdown.receiver.domain.AudioLibrary
import java.io.IOException
import java.io.OutputStream

/** Salva áudios em Música/ytDown, onde os players do celular os encontram. */
class MediaStoreAudioLibrary(context: Context) : AudioLibrary {
    private val resolver = context.contentResolver

    /** Enquanto `write` roda, o arquivo fica oculto; se falhar, nada fica salvo. */
    override fun save(name: String, mimeType: String, write: (OutputStream) -> Unit) {
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
            resolver.update(uri, ContentValues().apply { put(MediaStore.Audio.Media.IS_PENDING, 0) }, null, null)
        } catch (failure: Throwable) {
            resolver.delete(uri, null, null)
            throw failure
        }
    }
}
