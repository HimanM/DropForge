package io.github.himanm.tdminer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CookieStoreTest {
    @Test
    fun persistsCookiesUntilLogout() {
        val store = MemoryCookieStore()

        store.saveCookies("auth-token=cookie-value")

        assertTrue(store.hasCookies())
        assertEquals("auth-token=cookie-value", store.loadCookies())

        store.logout()

        assertFalse(store.hasCookies())
        assertNull(store.loadCookies())
    }
}
