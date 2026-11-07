package com.ytdown.receiver

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class FileNamesTest {
    @Test
    fun keepsNormalNames() {
        assertEquals("Canção número 1.mp3", safeAudioName("Canção número 1.mp3"))
        assertEquals("a.b.FLAC", safeAudioName("a.b.FLAC"))
    }

    @Test
    fun removesAnyPathFromTheName() {
        assertEquals("x.mp3", safeAudioName("../../x.mp3"))
        assertEquals("x.mp3", safeAudioName("..\\..\\x.mp3"))
        assertEquals("x.mp3", safeAudioName("/sdcard/x.mp3"))
    }

    @Test
    fun removesControlCharacters() {
        assertEquals("ab.mp3", safeAudioName("a\u0000b\n.mp3"))
    }

    @Test
    fun rejectsWhatIsNotAudio() {
        assertNull(safeAudioName("app.apk"))
        assertNull(safeAudioName("script.mp3.exe"))
        assertNull(safeAudioName("semextensao"))
        assertNull(safeAudioName(".mp3"))
        assertNull(safeAudioName("  "))
        assertNull(safeAudioName("pasta/"))
    }

    @Test
    fun knowsTheTypeOfEveryFormatTheDesktopProduces() {
        assertEquals("audio/mpeg", mimeTypeFor("a.mp3"))
        assertEquals("audio/mp4", mimeTypeFor("a.M4A"))
        assertEquals("audio/flac", mimeTypeFor("a.flac"))
        assertEquals("audio/x-wav", mimeTypeFor("a.wav"))
    }

    @Test
    fun formatsSizes() {
        assertEquals("500 B", formatSize(500))
        assertEquals("2 KB", formatSize(2048))
        assertEquals("1,5 MB", formatSize(1_572_864))
    }
}
