package com.ytdown.receiver.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val BrandRed = Color(0xFFC82630)

private val LightColors = lightColorScheme(primary = BrandRed, onPrimary = Color.White)
private val DarkColors = darkColorScheme(primary = Color(0xFFFFB3B0), onPrimary = Color(0xFF68000F))

@Composable
fun YtDownTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) DarkColors else LightColors, content = content)
}
