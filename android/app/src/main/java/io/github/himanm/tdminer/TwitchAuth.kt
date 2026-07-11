package io.github.himanm.tdminer

import java.net.HttpURLConnection
import java.net.URL

data class TwitchAuthResult(val valid: Boolean, val userId: String? = null)

fun validateTwitchAuth(authToken: String): TwitchAuthResult {
    val connection = (URL("https://id.twitch.tv/oauth2/validate").openConnection() as HttpURLConnection).apply {
        requestMethod = "GET"
        connectTimeout = 10_000
        readTimeout = 10_000
        setRequestProperty("Authorization", "OAuth $authToken")
    }
    return try {
        if (connection.responseCode != HttpURLConnection.HTTP_OK) {
            TwitchAuthResult(false)
        } else {
            TwitchAuthResult(true, connection.inputStream.bufferedReader().use { it.readText() }.jsonValue("user_id"))
        }
    } finally {
        connection.disconnect()
    }
}

internal fun String.jsonValue(name: String): String? =
    Regex(""""${Regex.escape(name)}"\s*:\s*"([^"]*)"""").find(this)?.groupValues?.get(1)
