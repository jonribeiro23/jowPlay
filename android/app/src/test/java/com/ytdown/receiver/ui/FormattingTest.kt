package com.ytdown.receiver.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class FormattingTest {
    @Test
    fun formatsSizes() {
        assertEquals("500 B", formatSize(500))
        assertEquals("2 KB", formatSize(2048))
        assertEquals("1,5 MB", formatSize(1_572_864))
    }
}
