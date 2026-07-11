package io.github.himanm.tdminer

import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MinerCoreTest {
    @Test
    fun startUsesPersistedCookies() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)

        assertFalse(core.session.loggedIn)

        store.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"cookie-value"}}}""")
        core.start()

        assertTrue(core.session.running)
        assertTrue(core.session.loggedIn)
    }

    @Test
    fun placeholderCookiesDoNotCountAsLoggedIn() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)

        store.saveCookies("demo-auth-cookie")
        core.start()

        assertTrue(core.session.running)
        assertFalse(core.session.loggedIn)
        assertFalse(core.session.authReady)
    }

    @Test
    fun startParsesDesktopCookieJarAuthToken() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)
        store.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"oauth-token"},"persistent":{"value":"464062006"}}}""")

        core.start()

        assertTrue(core.session.authReady)
    }

    @Test
    fun validateAuthKeepsValidTokenReady() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)
        store.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"oauth-token"}}}""")

        core.start()
        core.validateAuth { TwitchAuthResult(true, "464062006") }

        assertTrue(core.session.loggedIn)
        assertTrue(core.session.authReady)
    }

    @Test
    fun validateAuthRejectsInvalidToken() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)
        store.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"expired-token"}}}""")

        core.start()
        core.validateAuth { TwitchAuthResult(false) }

        assertFalse(core.session.loggedIn)
        assertFalse(core.session.authReady)
    }

    @Test
    fun refreshDropsUpdatesSessionFromInventorySnapshot() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)
        store.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"oauth-token"}}}""")

        core.start()
        core.refreshDrops(MinerSettings(priorityGames = listOf("Detroit: Become Human"))) { _, _ ->
            listOf(TwitchDropSnapshot(
                game = "Detroit: Become Human",
                campaign = "Detroit Badge Drop",
                drop = "Android Triangle",
                currentMinutes = 15,
                requiredMinutes = 60,
                campaignProgress = 0.25f,
            ))
        }

        assertEquals("Detroit: Become Human", core.session.game)
        assertEquals("Detroit Badge Drop", core.session.campaign)
        assertEquals("Android Triangle", core.session.drop)
    }

    @Test
    fun emptyPriorityDoesNotFetchOrDisplayDrops() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)
        store.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"oauth-token"}}}""")
        var fetched = false

        core.start()
        core.refreshDrops { _, _ ->
            fetched = true
            listOf(TwitchDropSnapshot(
                game = "Overwatch",
                campaign = "OWCS",
                drop = "Reward",
                currentMinutes = 1,
                requiredMinutes = 60,
                campaignProgress = 0.01f,
            ))
        }

        assertFalse(fetched)
        assertEquals("No priority selected", core.session.game)
        assertEquals(emptyList<TwitchDropSnapshot>(), core.session.drops)
    }

    @Test
    fun refreshDropsPassesPriorityAndExcludedSettings() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)
        store.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"oauth-token"}}}""")

        core.start()
        core.refreshDrops(MinerSettings(priorityGames = listOf("Overwatch"), excludedGames = listOf("Detroit"))) { _, _ ->
            listOf(TwitchDropSnapshot(
                game = "Overwatch",
                campaign = "OWCS",
                drop = "Battle Pass Tier Skip",
                currentMinutes = 1,
                requiredMinutes = 60,
                campaignProgress = 0.01f,
            ))
        }

        assertEquals("Overwatch", core.session.game)
    }

    @Test
    fun watchOnceDoesNothingWhenIdle() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)
        store.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"oauth-token"},"persistent":{"value":"464062006"}}}""")
        var watched = false

        core.refreshDrops(MinerSettings(priorityGames = listOf("Overwatch"))) { _, _ ->
            listOf(TwitchDropSnapshot(
                game = "Overwatch",
                campaign = "OWCS",
                drop = "Reward",
                currentMinutes = 1,
                requiredMinutes = 60,
                campaignProgress = 0.01f,
            ))
        }
        core.watchOnce(
            channelFetcher = { _, _ ->
                listOf(TwitchChannel("1", "login", "Display", "b1", "g1", "Overwatch", 10))
            },
            watcher = { _, _, _ ->
                watched = true
                true
            },
        )

        assertFalse(watched)
        assertEquals(emptyList<TwitchChannel>(), core.session.channels)
    }

    @Test
    fun refreshDropsClearsSessionWhenPriorityHasNoActiveMatch() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)
        store.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"oauth-token"}}}""")

        core.start()
        core.refreshDrops(MinerSettings(priorityGames = listOf("Overwatch"))) { _, _ -> emptyList() }

        assertEquals("No priority drop", core.session.game)
        assertEquals("No matching drop", core.session.channel)
    }

    fun logoutStopsAndClearsCookies() {
        val store = MemoryCookieStore()
        val core = MinerCore(store)
        store.saveCookies("""{"twitch.tv|":{"auth-token":{"value":"cookie-value"}}}""")

        core.start()
        core.logout()

        assertFalse(core.session.running)
        assertFalse(core.session.loggedIn)
        assertFalse(store.hasCookies())
    }
}
