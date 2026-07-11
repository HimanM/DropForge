package io.github.himanm.tdminer

import org.junit.Assert.assertEquals
import org.junit.Test

class MinerSettingsStoreTest {
    @Test
    fun defaultsDoNotContainPlaceholderGames() {
        val settings = MinerSettings()

        assertEquals(emptyList<String>(), settings.priorityGames)
        assertEquals(emptyList<String>(), settings.excludedGames)
    }

    @Test
    fun categoryCacheIsFreshForOneHour() {
        val cache = CategoryCache(listOf(TwitchCategory("1", "Overwatch")), savedAtMillis = 1_000)

        assertEquals(true, cache.isFresh(nowMillis = 1_000 + 59 * 60 * 1000L))
        assertEquals(false, cache.isFresh(nowMillis = 1_000 + 61 * 60 * 1000L))
    }

    @Test
    fun memoryStorePersistsCategoryCache() {
        val store = MemoryMinerSettingsStore()

        store.saveCategoryCache(listOf(TwitchCategory("1", "Overwatch")), savedAtMillis = 123)

        assertEquals("Overwatch", store.loadCategoryCache().categories[0].name)
        assertEquals(123, store.loadCategoryCache().savedAtMillis)
    }

    @Test
    fun normalizeSettingsListRemovesBlanksAndDuplicates() {
        val normalized = normalizeSettingsList(
            listOf(" Detroit: Become Human ", "", "Just Chatting", "Detroit: Become Human"),
        )

        assertEquals(listOf("Detroit: Become Human", "Just Chatting"), normalized)
    }

    @Test
    fun memoryStoreNormalizesSavedLists() {
        val store = MemoryMinerSettingsStore()

        store.save(
            MinerSettings(
                priorityGames = listOf("Minecraft", " Minecraft "),
                excludedGames = listOf("", "Slots"),
                notificationsEnabled = false,
            ),
        )

        assertEquals(listOf("Minecraft"), store.load().priorityGames)
        assertEquals(listOf("Slots"), store.load().excludedGames)
        assertEquals(false, store.load().notificationsEnabled)
    }
}
