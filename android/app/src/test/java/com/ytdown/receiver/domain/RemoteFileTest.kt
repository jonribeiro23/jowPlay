package com.ytdown.receiver.domain

import com.ytdown.receiver.domain.model.RemoteFile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RemoteFileTest {
    @Test fun legacyFilesHaveUsableDisplayFallbacks() {
        val file = RemoteFile("id", "music.mp3", 42)
        assertEquals("music", file.title)
        assertEquals("", file.artist)
        assertNull(file.coverRevision)
    }

    @Test fun metadataAndCoverRevisionAreRetained() {
        val file = RemoteFile("id", "music.mp3", 42, "Title", "Artist", "revision")
        assertEquals("Title", file.title)
        assertEquals("Artist", file.artist)
        assertEquals("revision", file.coverRevision)
    }
}
