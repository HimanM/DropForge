package io.github.himanm.tdminer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TwitchCookieJarTest {
    @Test
    fun deviceLoginTokenConvertsToCookieJar() {
        val jar = TwitchCookieJar.parse(deviceLoginCookies("token", "42", "device"))

        assertEquals("token", jar.authToken)
        assertEquals("42", jar.userId)
        assertEquals("device", jar.deviceId)
    }

    @Test
    fun extractsAuthTokenAndPersistentUserIdFromDesktopCookieJson() {
        val jar = TwitchCookieJar.parse(
            """
            {
              "twitch.tv|": {
                "auth-token": {"value": "oauth-token"},
                "persistent": {"value": "464062006"}
              }
            }
            """.trimIndent(),
        )

        assertEquals("oauth-token", jar.authToken)
        assertEquals("464062006", jar.userId)
        assertTrue(jar.hasAuthToken)
    }

    @Test
    fun buildsCookieHeaderAndDeviceIdFromDesktopCookieJson() {
        val jar = TwitchCookieJar.parse(
            """
            {
              "twitch.tv|": {
                "unique_id": {"key": "unique_id", "value": "device-1"},
                "auth-token": {"key": "auth-token", "value": "oauth-token"}
              },
              "www.twitch.tv|": {
                "unique_id": {"key": "unique_id", "value": "device-2"},
                "persistent": {"key": "persistent", "value": "464062006"}
              }
            }
            """.trimIndent(),
        )

        assertEquals("device-1", jar.deviceId)
        assertTrue(jar.cookieHeader.contains("auth-token=oauth-token"))
        assertTrue(jar.cookieHeader.contains("persistent=464062006"))
    }

    @Test
    fun treatsMissingAuthTokenAsLoggedOut() {
        val jar = TwitchCookieJar.parse("""{"twitch.tv|":{}}""")

        assertFalse(jar.hasAuthToken)
    }
}
