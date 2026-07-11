package io.github.himanm.tdminer

import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID

data class TwitchDeviceCode(
    val deviceCode: String,
    val userCode: String,
    val verificationUrl: String,
    val intervalSeconds: Int,
    val expiresInSeconds: Int,
    val deviceId: String,
)

fun requestTwitchDeviceCode(): TwitchDeviceCode {
    val deviceId = UUID.randomUUID().toString().replace("-", "")
    val response = postForm(
        "https://id.twitch.tv/oauth2/device",
        mapOf("client_id" to ANDROID_APP_CLIENT_ID, "scopes" to ""),
        deviceId,
    )
    return TwitchDeviceCode(
        deviceCode = response.jsonValue("device_code") ?: error("Twitch did not return a device code"),
        userCode = response.jsonValue("user_code") ?: error("Twitch did not return a user code"),
        verificationUrl = response.jsonValue("verification_uri") ?: "https://www.twitch.tv/activate",
        intervalSeconds = response.jsonInt("interval") ?: 5,
        expiresInSeconds = response.jsonInt("expires_in") ?: 1800,
        deviceId = deviceId,
    )
}

fun awaitTwitchDeviceLogin(code: TwitchDeviceCode): String {
    val deadline = System.currentTimeMillis() + code.expiresInSeconds * 1000L
    while (System.currentTimeMillis() < deadline) {
        Thread.sleep(code.intervalSeconds * 1000L)
        val result = runCatching {
            postForm(
                "https://id.twitch.tv/oauth2/token",
                mapOf(
                    "client_id" to ANDROID_APP_CLIENT_ID,
                    "device_code" to code.deviceCode,
                    "grant_type" to "urn:ietf:params:oauth:grant-type:device_code",
                ),
                code.deviceId,
            )
        }.getOrNull() ?: continue
        val token = result.jsonValue("access_token") ?: continue
        val userId = validateTwitchAuth(token).userId.orEmpty()
        return deviceLoginCookies(token, userId, code.deviceId)
    }
    error("Twitch login code expired")
}

internal fun deviceLoginCookies(token: String, userId: String, deviceId: String): String =
    """{"twitch.tv|":{"auth-token":{"key":"auth-token","value":"$token"},"persistent":{"key":"persistent","value":"$userId"},"unique_id":{"key":"unique_id","value":"$deviceId"}}}"""

private fun postForm(url: String, fields: Map<String, String>, deviceId: String): String {
    val body = fields.entries.joinToString("&") { (key, value) ->
        "${URLEncoder.encode(key, "UTF-8")}=${URLEncoder.encode(value, "UTF-8")}"
    }
    val connection = (URL(url).openConnection() as HttpURLConnection).apply {
        requestMethod = "POST"
        connectTimeout = 10_000
        readTimeout = 10_000
        doOutput = true
        setRequestProperty("Client-Id", ANDROID_APP_CLIENT_ID)
        setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
        setRequestProperty("X-Device-Id", deviceId)
    }
    return try {
        connection.outputStream.use { it.write(body.toByteArray()) }
        val stream = if (connection.responseCode < 400) connection.inputStream else connection.errorStream
        val response = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (connection.responseCode >= 400) error(response)
        response
    } finally {
        connection.disconnect()
    }
}

private fun String.jsonInt(name: String): Int? =
    Regex(""""${Regex.escape(name)}"\s*:\s*(\d+)""").find(this)?.groupValues?.get(1)?.toIntOrNull()
