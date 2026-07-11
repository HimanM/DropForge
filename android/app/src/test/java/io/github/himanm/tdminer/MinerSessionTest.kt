package io.github.himanm.tdminer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MinerSessionTest {
    @Test
    fun runningSessionStartsInLoadingStateAndReportsServiceFlags() {
        val session = MinerSession.running()

        assertTrue(session.running)
        assertEquals("Finding channel", session.channel)
        assertEquals(0f, session.campaignProgress, 0.001f)
        assertEquals(0f, session.dropProgress, 0.001f)
        assertTrue(session.wakeLockActive)
        assertTrue(session.notificationActive)
    }

    @Test
    fun idleSessionKeepsBackgroundWorkOff() {
        val session = MinerSession.idle()

        assertFalse(session.running)
        assertEquals("Not watching", session.channel)
        assertEquals("Ready", session.game)
        assertFalse(session.wakeLockActive)
        assertFalse(session.notificationActive)
    }
}
