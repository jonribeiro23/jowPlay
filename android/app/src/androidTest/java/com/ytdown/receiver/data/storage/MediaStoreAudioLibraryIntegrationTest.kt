package com.ytdown.receiver.data.storage

import android.content.Context
import android.net.Uri
import android.test.InstrumentationTestCase
import com.ytdown.receiver.domain.model.RemoteFile
import com.ytdown.receiver.domain.model.Server
import java.io.IOException
import java.security.MessageDigest
import java.util.UUID
import org.json.JSONObject

@Suppress("DEPRECATION")
class MediaStoreAudioLibraryIntegrationTest : InstrumentationTestCase() {
    private val runId = UUID.randomUUID().toString()
    private val server = Server("integration-$runId", "test", "192.168.0.1", 1)
    private val audio = "integration audio $runId".toByteArray()
    private val file = RemoteFile("track-$runId", "integration-$runId.mp3", audio.size.toLong(),
        revision = "a".repeat(64), sha256 = hash(audio))
    private lateinit var context: Context
    private var removed = false
    private val key: String get() = hash((server.id.length.toString() + ":" + server.id + file.id).toByteArray())
    private val preferences get() = context.getSharedPreferences("download_associations", Context.MODE_PRIVATE)
    private val uri: Uri get() = Uri.parse(JSONObject(preferences.getString(key, null)!!).getString("uri"))

    override fun setUp() {
        super.setUp()
        context = instrumentation.targetContext
    }

    override fun tearDown() {
        // Somente a URI e a associação criadas por esta execução com UUID próprio.
        if (!removed) preferences.getString(key, null)?.let {
            context.contentResolver.delete(Uri.parse(JSONObject(it).getString("uri")), null, null)
        }
        preferences.edit().remove(key).commit()
        super.tearDown()
    }

    fun testPersistenceIntegrityIdentityAndRemoval() {
        val library = MediaStoreAudioLibrary(context)
        library.saveFor(server, file, file.name, "audio/mpeg") { it.write(audio) }
        val stored = uri
        val reopened = MediaStoreAudioLibrary(context)
        assertTrue(reopened.isSynced(server, file))
        assertFalse(reopened.isSynced(server.copy(id = server.id + "other"), file))
        assertFalse(reopened.isSynced(server, file.copy(id = file.id + "other")))
        assertFalse(reopened.isSynced(server, file.copy(revision = "b".repeat(64))))
        assertFalse(reopened.isSynced(server, file.copy(sha256 = null)))
        context.contentResolver.openOutputStream(stored, "wt")!!.use { it.write(ByteArray(audio.size)) }
        assertFalse(reopened.isSynced(server, file))
        context.contentResolver.openOutputStream(stored, "wt")!!.use { it.write(audio) }
        assertTrue(reopened.isSynced(server, file))
        assertEquals(1, context.contentResolver.delete(stored, null, null))
        removed = true
        assertFalse(reopened.isSynced(server, file))
    }

    fun testInterruptedWriteDoesNotAssociate() {
        val library = MediaStoreAudioLibrary(context)
        try {
            library.saveFor(server, file, file.name, "audio/mpeg") {
                it.write(audio)
                throw IOException("interrupted")
            }
            fail("Expected IOException")
        } catch (_: IOException) { }
        assertFalse(preferences.contains(key))
        assertFalse(MediaStoreAudioLibrary(context).isSynced(server, file))
    }

    private companion object {
        fun hash(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes)
            .joinToString("") { "%02x".format(it) }
    }
}
