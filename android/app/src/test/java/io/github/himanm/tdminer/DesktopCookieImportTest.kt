package io.github.himanm.tdminer

import org.junit.Assert.assertTrue
import org.junit.Test

class DesktopCookieImportTest {
    @Test
    fun desktopCookieJsonCanBeStoredAsSessionCookies() {
        val core = MinerCore(MemoryCookieStore())

        core.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"secret"}}}""")

        assertTrue(core.session.loggedIn)
    }
}
