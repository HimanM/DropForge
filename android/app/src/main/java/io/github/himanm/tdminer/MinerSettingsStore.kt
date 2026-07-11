package io.github.himanm.tdminer

import android.content.Context

data class MinerSettings(
    val priorityGames: List<String> = emptyList(),
    val excludedGames: List<String> = emptyList(),
    val farmUnlinkedDrops: Boolean = true,
    val badgeEmoteSupport: Boolean = true,
    val notificationsEnabled: Boolean = true,
    val wakeLockEnabled: Boolean = true,
)

data class CategoryCache(
    val categories: List<TwitchCategory>,
    val savedAtMillis: Long,
) {
    fun isFresh(nowMillis: Long, ttlMillis: Long = 60 * 60 * 1000L): Boolean =
        categories.isNotEmpty() && nowMillis - savedAtMillis < ttlMillis
}

interface MinerSettingsStore {
    fun load(): MinerSettings
    fun save(settings: MinerSettings)
    fun loadCategoryCache(): CategoryCache
    fun saveCategoryCache(categories: List<TwitchCategory>, savedAtMillis: Long = System.currentTimeMillis())
}

class SharedPrefsMinerSettingsStore(context: Context) : MinerSettingsStore {
    private val prefs = context.getSharedPreferences("tdminer_settings", Context.MODE_PRIVATE)

    override fun load(): MinerSettings {
        migratePlaceholderDefaults()
        return MinerSettings(
            priorityGames = prefs.loadList(KEY_PRIORITY) ?: MinerSettings().priorityGames,
            excludedGames = prefs.loadList(KEY_EXCLUDED) ?: MinerSettings().excludedGames,
            farmUnlinkedDrops = prefs.getBoolean(KEY_FARM_UNLINKED, true),
            badgeEmoteSupport = prefs.getBoolean(KEY_BADGE_EMOTE, true),
            notificationsEnabled = prefs.getBoolean(KEY_NOTIFICATIONS, true),
            wakeLockEnabled = prefs.getBoolean(KEY_WAKE_LOCK, true),
        )
    }

    override fun save(settings: MinerSettings) {
        prefs.edit()
            .putString(KEY_PRIORITY, encodeSettingsList(settings.priorityGames))
            .putString(KEY_EXCLUDED, encodeSettingsList(settings.excludedGames))
            .putBoolean(KEY_FARM_UNLINKED, settings.farmUnlinkedDrops)
            .putBoolean(KEY_BADGE_EMOTE, settings.badgeEmoteSupport)
            .putBoolean(KEY_NOTIFICATIONS, settings.notificationsEnabled)
            .putBoolean(KEY_WAKE_LOCK, settings.wakeLockEnabled)
            .apply()
    }

    override fun loadCategoryCache(): CategoryCache =
        if (prefs.getInt(KEY_CATEGORIES_VERSION, 0) == CATEGORY_CACHE_VERSION) {
            CategoryCache(
                categories = prefs.loadCategories(KEY_CATEGORIES),
                savedAtMillis = prefs.getLong(KEY_CATEGORIES_SAVED_AT, 0L),
            )
        } else {
            CategoryCache(emptyList(), 0L)
        }

    override fun saveCategoryCache(categories: List<TwitchCategory>, savedAtMillis: Long) {
        prefs.edit()
            .putString(KEY_CATEGORIES, encodeCategories(categories))
            .putLong(KEY_CATEGORIES_SAVED_AT, savedAtMillis)
            .putInt(KEY_CATEGORIES_VERSION, CATEGORY_CACHE_VERSION)
            .apply()
    }

    private fun android.content.SharedPreferences.loadList(key: String): List<String>? =
        getString(key, null)?.lineSequence()?.toList()?.let(::normalizeSettingsList)

    private fun android.content.SharedPreferences.loadCategories(key: String): List<TwitchCategory> =
        getString(key, null)
            ?.lineSequence()
            ?.mapNotNull { row ->
                val parts = row.split('\t', limit = 2)
                if (parts.size == 2 && parts[0].isNotBlank() && parts[1].isNotBlank()) {
                    TwitchCategory(parts[0], parts[1])
                } else {
                    null
                }
            }
            ?.toList()
            ?: emptyList()

    private fun migratePlaceholderDefaults() {
        val version = prefs.getInt(KEY_VERSION, 0)
        if (version >= 3) return
        val priority = prefs.loadList(KEY_PRIORITY)
        val excluded = prefs.loadList(KEY_EXCLUDED)
        val autoSeededPriority = setOf("Overwatch", "Overwatch 2", "Marvel Rivals")
        prefs.edit()
            .apply {
                if (priority == listOf("Detroit: Become Human") || priority?.all { it in autoSeededPriority } == true) {
                    remove(KEY_PRIORITY)
                } else {
                    priority?.filterNot { it == "Detroit: Become Human" }?.let { putString(KEY_PRIORITY, encodeSettingsList(it)) }
                }
                if (excluded == listOf("Just Chatting")) {
                    remove(KEY_EXCLUDED)
                } else {
                    excluded?.filterNot { it == "Just Chatting" }?.let { putString(KEY_EXCLUDED, encodeSettingsList(it)) }
                }
            }
            .putInt(KEY_VERSION, 3)
            .apply()
    }

    companion object {
        private const val KEY_VERSION = "settings_version"
        private const val KEY_PRIORITY = "priority_games"
        private const val KEY_EXCLUDED = "excluded_games"
        private const val KEY_FARM_UNLINKED = "farm_unlinked_drops"
        private const val KEY_BADGE_EMOTE = "badge_emote_support"
        private const val KEY_NOTIFICATIONS = "notifications_enabled"
        private const val KEY_WAKE_LOCK = "wake_lock_enabled"
        private const val KEY_CATEGORIES = "drop_categories"
        private const val KEY_CATEGORIES_SAVED_AT = "drop_categories_saved_at"
        private const val KEY_CATEGORIES_VERSION = "drop_categories_version"
        private const val CATEGORY_CACHE_VERSION = 2
    }
}

class MemoryMinerSettingsStore(settings: MinerSettings = MinerSettings()) : MinerSettingsStore {
    private var settings = settings

    override fun load(): MinerSettings = settings

    override fun save(settings: MinerSettings) {
        this.settings = settings.copy(
            priorityGames = normalizeSettingsList(settings.priorityGames),
            excludedGames = normalizeSettingsList(settings.excludedGames),
        )
    }

    private var categoryCache = CategoryCache(emptyList(), 0L)

    override fun loadCategoryCache(): CategoryCache = categoryCache

    override fun saveCategoryCache(categories: List<TwitchCategory>, savedAtMillis: Long) {
        categoryCache = CategoryCache(categories, savedAtMillis)
    }
}

internal fun encodeSettingsList(items: Iterable<String>): String =
    normalizeSettingsList(items).joinToString("\n")

internal fun normalizeSettingsList(items: Iterable<String>): List<String> =
    items.map(String::trim).filter(String::isNotEmpty).distinct()

private fun encodeCategories(categories: List<TwitchCategory>): String =
    categories.distinctBy { it.id }.joinToString("\n") { "${it.id}\t${it.name}" }
