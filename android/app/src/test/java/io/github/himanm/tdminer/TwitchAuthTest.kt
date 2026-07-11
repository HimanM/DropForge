package io.github.himanm.tdminer

import org.junit.Assert.assertEquals
import org.junit.Test

class TwitchAuthTest {
    @Test
    fun extractsUserIdFromValidateResponse() {
        assertEquals("464062006", """{"client_id":"x","user_id":"464062006","login":"him"}""".jsonValue("user_id"))
    }
}
