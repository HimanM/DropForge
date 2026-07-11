package io.github.himanm.tdminer

data class TwitchCookieJar(
    val raw: String,
    val authToken: String?,
    val userId: String?,
    val deviceId: String?,
    val cookieHeader: String,
) {
    val hasAuthToken: Boolean = !authToken.isNullOrBlank()

    companion object {
        fun parse(raw: String): TwitchCookieJar {
            return TwitchCookieJar(
                raw = raw,
                authToken = raw.cookieValue("auth-token"),
                userId = raw.cookieValue("persistent"),
                deviceId = raw.cookieValue("unique_id"),
                cookieHeader = raw.cookiePairs().associate { it.first to it.second }.entries.joinToString("; ") { "${it.key}=${it.value}" },
            )
        }
    }
}

private fun String.cookieValue(name: String): String? {
    val match = Regex(
        """"${Regex.escape(name)}"\s*:\s*\{[^}]*"value"\s*:\s*"([^"]*)"""",
        RegexOption.DOT_MATCHES_ALL,
    ).find(this)
    return match?.groupValues?.get(1)?.replace("\\\"", "\"")
}

private fun String.cookiePairs(): List<Pair<String, String>> =
    Regex(
        """"key"\s*:\s*"([^"]+)"[\s\S]*?"value"\s*:\s*"([^"]*)"""",
        RegexOption.DOT_MATCHES_ALL,
    ).findAll(this).map { match ->
        match.groupValues[1].replace("\\\"", "\"") to match.groupValues[2].replace("\\\"", "\"")
    }.toList()
