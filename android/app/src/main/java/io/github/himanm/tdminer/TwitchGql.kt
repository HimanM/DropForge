package io.github.himanm.tdminer

import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.util.Base64
import java.util.zip.GZIPOutputStream

data class TwitchCategory(val id: String, val name: String)
data class TwitchChannel(
    val id: String,
    val login: String,
    val displayName: String,
    val broadcastId: String,
    val gameId: String,
    val gameName: String,
    val viewers: Int,
)

data class TwitchDropSnapshot(
    val campaignId: String = "",
    val dropId: String = "",
    val game: String,
    val campaign: String,
    val drop: String,
    val channel: String = "Twitch",
    val gameImageUrl: String? = null,
    val dropImageUrl: String? = null,
    val rewards: List<String> = emptyList(),
    val rewardImageUrls: List<String> = emptyList(),
    val currentMinutes: Int,
    val requiredMinutes: Int,
    val remainingSeconds: Int = (requiredMinutes - currentMinutes).coerceAtLeast(0) * 60,
    val campaignProgress: Float,
) {
    val dropProgress: Float = progress(currentMinutes, requiredMinutes)
    val remaining: String = formatRemainingSeconds(remainingSeconds)
    val dropKey: String = listOf(campaignId, dropId, game, campaign, drop).joinToString("\u0000")
}

fun fetchInventorySnapshots(authToken: String): List<TwitchDropSnapshot> {
    return fetchInventorySnapshots(authToken, userId = null, cookieHeader = null, deviceId = null)
}

fun fetchInventorySnapshots(
    authToken: String,
    userId: String?,
    cookieHeader: String?,
    deviceId: String?,
    onCampaignProgress: (Int, Int) -> Unit = { _, _ -> },
): List<TwitchDropSnapshot> {
    val body = JSONObject()
        .put("operationName", "Inventory")
        .put("variables", JSONObject().put("fetchRewardCampaigns", false))
        .put(
            "extensions",
            JSONObject().put(
                "persistedQuery",
                JSONObject()
                    .put("version", 1)
                    .put("sha256Hash", INVENTORY_HASH),
            ),
        )
        .toString()
    val campaignsBody = JSONObject()
        .put("operationName", "ViewerDropsDashboard")
        .put("variables", JSONObject().put("fetchRewardCampaigns", false))
        .put(
            "extensions",
            JSONObject().put(
                "persistedQuery",
                JSONObject()
                    .put("version", 1)
                    .put("sha256Hash", CAMPAIGNS_HASH),
            ),
        )
        .toString()
    val inventoryRaw = postGql(authToken, body, cookieHeader, deviceId)
    val campaignsRaw = postGql(authToken, campaignsBody, cookieHeader, deviceId)
    val claimedBenefits = parseClaimedBenefits(inventoryRaw)
    return (parseInventorySnapshots(inventoryRaw) +
        fetchCampaignDetailSnapshots(authToken, userId, cookieHeader, deviceId, parseDropCampaignIds(campaignsRaw), claimedBenefits, onCampaignProgress))
        .distinctBy { it.dropKey }
}

fun fetchInventorySnapshot(
    authToken: String,
    priorityGames: List<String> = emptyList(),
    excludedGames: List<String> = emptyList(),
): TwitchDropSnapshot? {
    return selectInventorySnapshot(fetchInventorySnapshots(authToken), priorityGames, excludedGames)
}

fun fetchDropCategories(authToken: String, userId: String? = null): List<TwitchCategory> {
    return fetchDropCategories(authToken, userId, cookieHeader = null, deviceId = null)
}

fun fetchDropCategories(
    authToken: String,
    userId: String?,
    cookieHeader: String?,
    deviceId: String?,
): List<TwitchCategory> {
    val inventoryBody = JSONObject()
        .put("operationName", "Inventory")
        .put("variables", JSONObject().put("fetchRewardCampaigns", false))
        .put(
            "extensions",
            JSONObject().put(
                "persistedQuery",
                JSONObject()
                    .put("version", 1)
                    .put("sha256Hash", INVENTORY_HASH),
            ),
        )
        .toString()
    val campaignsBody = JSONObject()
        .put("operationName", "ViewerDropsDashboard")
        .put("variables", JSONObject().put("fetchRewardCampaigns", false))
        .put(
            "extensions",
            JSONObject().put(
                "persistedQuery",
                JSONObject()
                    .put("version", 1)
                    .put("sha256Hash", CAMPAIGNS_HASH),
            ),
        )
        .toString()
    val inventoryRaw = postGql(authToken, inventoryBody, cookieHeader, deviceId)
    val campaignsRaw = postGql(authToken, campaignsBody, cookieHeader, deviceId)
    return normalizeCategories(
        parseInventoryCategories(inventoryRaw) +
            parseDropCategories(campaignsRaw) +
            fetchCampaignDetailCategories(authToken, userId, cookieHeader, deviceId, parseDropCampaignIds(campaignsRaw)),
    )
}

private fun fetchCampaignDetailCategories(
    authToken: String,
    userId: String?,
    cookieHeader: String?,
    deviceId: String?,
    campaignIds: List<String>,
): List<TwitchCategory> {
    if (campaignIds.isEmpty()) return emptyList()
    val channelLogin = userId.orEmpty()
    return campaignIds.flatMap { campaignId ->
        val body = JSONObject()
            .put("operationName", "DropCampaignDetails")
            .put("variables", JSONObject().put("channelLogin", channelLogin).put("dropID", campaignId))
            .put(
                "extensions",
                JSONObject().put(
                    "persistedQuery",
                    JSONObject()
                        .put("version", 1)
                        .put("sha256Hash", CAMPAIGN_DETAILS_HASH),
                ),
            )
            .toString()
        runCatching { parseCampaignDetailCategories(postGql(authToken, body, cookieHeader, deviceId)) }.getOrDefault(emptyList())
    }
}

private fun fetchCampaignDetailSnapshots(
    authToken: String,
    userId: String?,
    cookieHeader: String?,
    deviceId: String?,
    campaignIds: List<String>,
    claimedBenefits: Map<String, Instant>,
    onProgress: (Int, Int) -> Unit,
): List<TwitchDropSnapshot> {
    if (campaignIds.isEmpty()) return emptyList()
    val channelLogin = userId.orEmpty()
    val total = campaignIds.size
    return campaignIds.flatMapIndexed { index, campaignId ->
        val body = JSONObject()
            .put("operationName", "DropCampaignDetails")
            .put("variables", JSONObject().put("channelLogin", channelLogin).put("dropID", campaignId))
            .put(
                "extensions",
                JSONObject().put(
                    "persistedQuery",
                    JSONObject()
                        .put("version", 1)
                        .put("sha256Hash", CAMPAIGN_DETAILS_HASH),
                ),
            )
            .toString()
        runCatching { parseCampaignDetailSnapshots(postGql(authToken, body, cookieHeader, deviceId), claimedBenefits) }
            .also { onProgress(index + 1, total) }
            .getOrDefault(emptyList())
    }
}

fun fetchLiveChannelsForGame(authToken: String, gameName: String, limit: Int = 30): List<TwitchChannel> {
    val slug = fetchGameSlug(authToken, gameName) ?: gameName.toGameSlug()
    val body = JSONObject()
        .put("operationName", "DirectoryPage_Game")
        .put(
            "variables",
            JSONObject()
                .put("limit", limit)
                .put("slug", slug)
                .put("imageWidth", 50)
                .put("includeCostreaming", false)
                .put(
                    "options",
                    JSONObject()
                        .put("broadcasterLanguages", JSONArray())
                        .put("freeformTags", JSONObject.NULL)
                        .put("includeRestricted", JSONArray().put("SUB_ONLY_LIVE"))
                        .put("recommendationsContext", JSONObject().put("platform", "web"))
                        .put("sort", "RELEVANCE")
                        .put("systemFilters", JSONArray().put("DROPS_ENABLED"))
                        .put("tags", JSONArray())
                        .put("requestID", "JIRA-VXP-2397"),
                )
                .put("sortTypeIsRecency", false),
        )
        .put(
            "extensions",
            JSONObject().put(
                "persistedQuery",
                JSONObject()
                    .put("version", 1)
                    .put("sha256Hash", GAME_DIRECTORY_HASH),
            ),
        )
        .toString()
    return parseLiveChannels(postGql(authToken, body))
}

fun fetchGameSlug(authToken: String, gameName: String): String? {
    val body = JSONObject()
        .put("operationName", "DirectoryGameRedirect")
        .put("variables", JSONObject().put("name", gameName))
        .put(
            "extensions",
            JSONObject().put(
                "persistedQuery",
                JSONObject()
                    .put("version", 1)
                    .put("sha256Hash", GAME_REDIRECT_HASH),
            ),
        )
        .toString()
    return parseGameSlug(postGql(authToken, body))
}

internal fun parseGameSlug(raw: String): String? =
    JSONObject(raw)
        .optJSONObject("data")
        ?.optJSONObject("game")
        ?.optString("slug")
        ?.takeIf(String::isNotBlank)

fun sendWatchMinute(authToken: String, userId: String, channel: TwitchChannel): Boolean {
    val event = JSONObject()
        .put("event", "minute-watched")
        .put(
            "properties",
            JSONObject()
                .put("broadcast_id", channel.broadcastId)
                .put("channel_id", channel.id)
                .put("channel", channel.login)
                .put("client_time", Instant.now().toString())
                .put("game", channel.gameName)
                .put("game_id", channel.gameId)
                .put("hidden", false)
                .put("is_live", true)
                .put("live", true)
                .put("logged_in", true)
                .put("minutes_logged", 1)
                .put("muted", false)
                .put("user_id", userId),
        )
    val body = JSONObject()
        .put("query", "\n mutation SendEvents(${'$'}input: SendSpadeEventsInput!) {\n sendSpadeEvents(input: ${'$'}input) {\n statusCode\n}\n}\n")
        .put(
            "variables",
            JSONObject().put(
                "input",
                JSONObject()
                    .put("data", gzipBase64(JSONArray().put(event).toString()))
                    .put("repository", "twilight")
                    .put("encoding", "GZIP_B64"),
            ),
        )
        .toString()
    val statusCode = JSONObject(postGql(authToken, body))
        .optJSONObject("data")
        ?.optJSONObject("sendSpadeEvents")
        ?.optInt("statusCode", 0)
        ?: 0
    return statusCode == 204
}

internal fun parseLiveChannels(raw: String): List<TwitchChannel> {
    val edges = JSONObject(raw)
        .optJSONObject("data")
        ?.optJSONObject("game")
        ?.optJSONObject("streams")
        ?.optJSONArray("edges")
        ?: return emptyList()
    return buildList {
        for (index in 0 until edges.length()) {
            val node = edges.optJSONObject(index)?.optJSONObject("node") ?: continue
            val broadcaster = node.optJSONObject("broadcaster") ?: continue
            val game = node.optJSONObject("game") ?: continue
            val channelId = broadcaster.optString("id")
            val login = broadcaster.optString("login")
            val broadcastId = node.optString("id")
            val gameId = game.optString("id")
            val name = gameName(game).orFallback("")
            if (channelId.isBlank() || login.isBlank() || broadcastId.isBlank() || gameId.isBlank() || name.isBlank()) continue
            add(
                TwitchChannel(
                    id = channelId,
                    login = login,
                    displayName = broadcaster.optString("displayName").orFallback(login),
                    broadcastId = broadcastId,
                    gameId = gameId,
                    gameName = name,
                    viewers = node.optInt("viewersCount", 0),
                ),
            )
        }
    }
}

internal fun parseInventoryCategories(raw: String): List<TwitchCategory> {
    val campaigns = JSONObject(raw)
        .optJSONObject("data")
        ?.optJSONObject("currentUser")
        ?.optJSONObject("inventory")
        ?.optJSONArray("dropCampaignsInProgress")
        ?: return emptyList()
    val activeOrUpcoming = JSONArray()
    for (index in 0 until campaigns.length()) {
        val campaign = campaigns.optJSONObject(index) ?: continue
        if (campaign.isActiveOrUpcomingCampaign()) activeOrUpcoming.put(campaign)
    }
    return campaignGames(activeOrUpcoming)
}

internal fun parseDropCategories(raw: String): List<TwitchCategory> {
    val campaigns = JSONObject(raw)
        .optJSONObject("data")
        ?.optJSONObject("currentUser")
        ?.optJSONArray("dropCampaigns")
        ?: return emptyList()
    val activeCampaigns = JSONArray()
    for (index in 0 until campaigns.length()) {
        val campaign = campaigns.optJSONObject(index) ?: continue
        if (campaign.optString("status") in setOf("ACTIVE", "UPCOMING", "") && campaign.isActiveOrUpcomingCampaign()) {
            activeCampaigns.put(campaign)
        }
    }
    return campaignGames(activeCampaigns)
}

internal fun parseDropCampaignIds(raw: String): List<String> {
    val campaigns = JSONObject(raw)
        .optJSONObject("data")
        ?.optJSONObject("currentUser")
        ?.optJSONArray("dropCampaigns")
        ?: return emptyList()
    return buildList {
        for (index in 0 until campaigns.length()) {
            val campaign = campaigns.optJSONObject(index) ?: continue
            val id = campaign.optString("id")
            if (id.isNotBlank() && campaign.optString("status") in setOf("ACTIVE", "UPCOMING", "") && campaign.isActiveOrUpcomingCampaign()) {
                add(id)
            }
        }
    }
}

internal fun parseCampaignDetailCategories(raw: String): List<TwitchCategory> {
    val value = JSONTokener(raw).nextValue()
    val responses = when (value) {
        is JSONArray -> value.objects()
        is JSONObject -> listOf(value)
        else -> emptyList()
    }
    return responses.mapNotNull { response ->
        val campaign = response
            .optJSONObject("data")
            ?.optJSONObject("user")
            ?.optJSONObject("dropCampaign")
        categoryFromGame(campaign?.optJSONObject("game"))
    }
}

internal fun parseCampaignDetailSnapshots(raw: String, claimedBenefits: Map<String, Instant> = emptyMap()): List<TwitchDropSnapshot> {
    val value = JSONTokener(raw).nextValue()
    val responses = when (value) {
        is JSONArray -> value.objects()
        is JSONObject -> listOf(value)
        else -> emptyList()
    }
    return responses.flatMap { response ->
        val campaign = response
            .optJSONObject("data")
            ?.optJSONObject("user")
            ?.optJSONObject("dropCampaign")
        campaignSnapshot(campaign, claimedBenefits)?.let(::listOf) ?: emptyList()
    }
}

private fun campaignSnapshot(campaign: JSONObject?, claimedBenefits: Map<String, Instant> = emptyMap()): TwitchDropSnapshot? {
    if (campaign == null || !campaign.isActiveCampaign()) return null
    val drops = campaign.optJSONArray("timeBasedDrops") ?: JSONArray()
    val drop = firstEarnableDrop(drops, claimedBenefits) ?: return null
    val current = drop.optJSONObject("self")?.optInt("currentMinutesWatched", 0) ?: 0
    val required = drop.optInt("requiredMinutesWatched", 0)
    if (required <= 0) return null
    val game = campaign.optJSONObject("game")
    val rewards = rewardNames(drop)
    val rewardImages = rewardImages(drop)
    return TwitchDropSnapshot(
        campaignId = campaign.optString("id"),
        dropId = drop.optString("id").orFallback(drop.optString("dropID")),
        game = gameName(game).orFallback("Unknown game"),
        campaign = campaign.optString("name").orFallback("Drops campaign"),
        drop = drop.optString("name").orFallback(rewards.firstOrNull() ?: "Drop reward"),
        gameImageUrl = imageUrl(game?.optString("boxArtURL")),
        dropImageUrl = imageUrl(drop.deepString("imageAssetURL", "imageURL", "imageUrl") ?: rewardImages.firstOrNull()),
        rewards = rewards,
        rewardImageUrls = rewardImages,
        currentMinutes = current,
        requiredMinutes = required,
        campaignProgress = campaignProgress(drops),
    )
}

private fun campaignGames(campaigns: JSONArray): List<TwitchCategory> {
    return buildList {
        for (index in 0 until campaigns.length()) {
            val game = campaigns.optJSONObject(index)?.optJSONObject("game") ?: continue
            categoryFromGame(game)?.let(::add)
        }
    }
}

private fun categoryFromGame(game: JSONObject?): TwitchCategory? {
    val id = game?.optString("id").orEmpty()
    val name = gameName(game).orFallback("")
    return if (id.isNotBlank() && name.isNotBlank()) TwitchCategory(id, name) else null
}

private fun normalizeCategories(categories: List<TwitchCategory>): List<TwitchCategory> =
    categories.distinctBy { it.id }.sortedBy { it.name.lowercase() }

internal fun String.toGameSlug(): String =
    lowercase()
        .replace("'", "")
        .replace(Regex("\\W+"), "-")
        .trim('-')
        .replace(Regex("-{2,}"), "-")

private fun gzipBase64(text: String): String {
    val output = ByteArrayOutputStream()
    GZIPOutputStream(output).use { it.write(text.toByteArray(Charsets.UTF_8)) }
    return Base64.getEncoder().encodeToString(output.toByteArray())
}

private fun gameName(game: JSONObject?): String? =
    game?.optString("displayName").orFallback(game?.optString("name") ?: "")

internal fun parseInventorySnapshot(raw: String): TwitchDropSnapshot? {
    return parseInventorySnapshots(raw).minByOrNull { it.remainingSeconds }
}

internal fun parseInventorySnapshots(raw: String): List<TwitchDropSnapshot> {
    val root = JSONObject(raw)
    val claimedBenefits = parseClaimedBenefits(root)
    val campaigns = root
        .optJSONObject("data")
        ?.optJSONObject("currentUser")
        ?.optJSONObject("inventory")
        ?.optJSONArray("dropCampaignsInProgress")
        ?: return emptyList()
    return buildList {
        for (campaignIndex in 0 until campaigns.length()) {
            val campaign = campaigns.optJSONObject(campaignIndex) ?: continue
            if (!campaign.isActiveCampaign()) continue
            val drops = campaign.optJSONArray("timeBasedDrops") ?: JSONArray()
            val drop = firstEarnableDrop(drops, claimedBenefits) ?: continue
            val current = drop.optJSONObject("self")?.optInt("currentMinutesWatched", 0) ?: 0
            val required = drop.optInt("requiredMinutesWatched", 0)
            if (required <= 0) continue
            val game = campaign.optJSONObject("game")
            val rewards = rewardNames(drop)
            val rewardImages = rewardImages(drop)
            add(
                TwitchDropSnapshot(
                    campaignId = campaign.optString("id"),
                    dropId = drop.optString("id").orFallback(drop.optString("dropID")),
                    game = gameName(game).orFallback("Unknown game"),
                    campaign = campaign.optString("name").orFallback("Drops campaign"),
                    drop = drop.optString("name").orFallback(rewards.firstOrNull() ?: "Drop reward"),
                    gameImageUrl = imageUrl(game?.optString("boxArtURL")),
                    dropImageUrl = imageUrl(drop.deepString("imageAssetURL", "imageURL", "imageUrl") ?: rewardImages.firstOrNull()),
                    rewards = rewards,
                    rewardImageUrls = rewardImages,
                    currentMinutes = current,
                    requiredMinutes = required,
                    campaignProgress = campaignProgress(drops),
                ),
            )
        }
    }
}

private fun JSONObject.isActiveCampaign(now: Instant = Instant.now()): Boolean {
    if (optString("status").equals("EXPIRED", ignoreCase = true)) return false
    val start = parseInstant("startAt")
    val end = parseInstant("endAt")
    return (start == null || !now.isBefore(start)) && (end == null || now.isBefore(end))
}

private fun JSONObject.isActiveOrUpcomingCampaign(now: Instant = Instant.now()): Boolean {
    if (optString("status").equals("EXPIRED", ignoreCase = true)) return false
    val end = parseInstant("endAt")
    return end == null || now.isBefore(end)
}

private fun JSONObject.parseInstant(key: String): Instant? =
    optString(key).takeIf(String::isNotBlank)?.let { runCatching { Instant.parse(it) }.getOrNull() }

internal fun selectInventorySnapshot(
    snapshots: List<TwitchDropSnapshot>,
    priorityGames: List<String>,
    excludedGames: List<String>,
): TwitchDropSnapshot? {
    val priority = priorityGames.map { it.lowercase() }
    if (priority.isEmpty()) return null
    val allowed = filterPrioritySnapshots(snapshots, priorityGames, excludedGames)
    return priority.firstNotNullOfOrNull { wanted ->
        allowed
            .filter { gameMatches(wanted, it.game.lowercase()) && it.requiredMinutes > 0 && it.currentMinutes < it.requiredMinutes }
            .minByOrNull { it.remainingSeconds }
    }
}

internal fun filterPrioritySnapshots(
    snapshots: List<TwitchDropSnapshot>,
    priorityGames: List<String>,
    excludedGames: List<String>,
): List<TwitchDropSnapshot> {
    val priority = priorityGames.map { it.lowercase() }
    if (priority.isEmpty()) return emptyList()
    val excluded = excludedGames.map { it.lowercase() }.toSet()
    return priority.flatMap { wanted ->
        snapshots
            .filterNot { it.game.lowercase() in excluded }
            .filter { gameMatches(wanted, it.game.lowercase()) }
            .sortedWith(compareBy<TwitchDropSnapshot> { it.currentMinutes >= it.requiredMinutes }.thenBy { it.remainingSeconds })
    }
}

private fun gameMatches(wanted: String, actual: String): Boolean =
    wanted == actual || wanted in actual || actual in wanted

private fun postGql(authToken: String, body: String, cookieHeader: String? = null, deviceId: String? = null): String {
    val connection = (URL("https://gql.twitch.tv/gql").openConnection() as HttpURLConnection).apply {
        requestMethod = "POST"
        connectTimeout = 10_000
        readTimeout = 10_000
        doOutput = true
        setRequestProperty("Client-Id", ANDROID_APP_CLIENT_ID)
        setRequestProperty("User-Agent", ANDROID_APP_USER_AGENT)
        setRequestProperty("Accept", "*/*")
        setRequestProperty("Accept-Language", "en-US")
        setRequestProperty("Pragma", "no-cache")
        setRequestProperty("Cache-Control", "no-cache")
        setRequestProperty("Authorization", "OAuth $authToken")
        setRequestProperty("Origin", "https://www.twitch.tv")
        setRequestProperty("Referer", "https://www.twitch.tv")
        setRequestProperty("Content-Type", "application/json")
        if (!cookieHeader.isNullOrBlank()) setRequestProperty("Cookie", cookieHeader)
        if (!deviceId.isNullOrBlank()) setRequestProperty("X-Device-Id", deviceId)
    }
    return try {
        connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        val stream = if (connection.responseCode < 400) connection.inputStream else connection.errorStream
        stream.bufferedReader().use { it.readText() }
    } finally {
        connection.disconnect()
    }
}

private fun firstEarnableDrop(drops: JSONArray, claimedBenefits: Map<String, Instant> = emptyMap()): JSONObject? {
    for (index in 0 until drops.length()) {
        val drop = drops.optJSONObject(index) ?: continue
        if (drop.optInt("requiredMinutesWatched", 0) <= 0) continue
        val self = drop.optJSONObject("self")
        val current = self?.optInt("currentMinutesWatched", 0) ?: 0
        val claimed = self?.optBoolean("isClaimed", false) ?: drop.wasClaimedAsGameEvent(claimedBenefits)
        if (!claimed && current < drop.optInt("requiredMinutesWatched", 0)) return drop
    }
    return null
}

private fun parseClaimedBenefits(raw: String): Map<String, Instant> = parseClaimedBenefits(JSONObject(raw))

private fun parseClaimedBenefits(root: JSONObject): Map<String, Instant> {
    val events = root.optJSONObject("data")?.optJSONObject("currentUser")?.optJSONObject("inventory")
        ?.optJSONArray("gameEventDrops") ?: return emptyMap()
    return buildMap {
        for (index in 0 until events.length()) {
            val event = events.optJSONObject(index) ?: continue
            val id = event.optString("id")
            val awarded = event.parseInstant("lastAwardedAt")
            if (id.isNotBlank() && awarded != null) put(id, awarded)
        }
    }
}

private fun JSONObject.wasClaimedAsGameEvent(claimedBenefits: Map<String, Instant>): Boolean {
    val start = parseInstant("startAt") ?: return false
    val end = parseInstant("endAt") ?: return false
    val benefits = optJSONArray("benefitEdges") ?: return false
    val awards = benefits.objects().mapNotNull { edge ->
        claimedBenefits[edge.optJSONObject("benefit")?.optString("id")]
    }
    return awards.isNotEmpty() && awards.all { !it.isBefore(start) && it.isBefore(end) }
}

private fun campaignProgress(drops: JSONArray): Float {
    var current = 0
    var required = 0
    for (index in 0 until drops.length()) {
        val drop = drops.optJSONObject(index) ?: continue
        val dropRequired = drop.optInt("requiredMinutesWatched", 0).coerceAtLeast(0)
        required += dropRequired
        current += (drop.optJSONObject("self")?.optInt("currentMinutesWatched", 0) ?: 0).coerceAtMost(dropRequired)
    }
    return progress(current, required)
}

private fun rewardNames(drop: JSONObject): List<String> =
    drop.optJSONArray("benefitEdges")?.objects()
        ?.mapNotNull { it.optJSONObject("benefit")?.optString("name")?.takeIf(String::isNotBlank) }
        ?: emptyList()

private fun rewardImages(drop: JSONObject): List<String> =
    drop.optJSONArray("benefitEdges")?.objects()
        ?.mapNotNull { it.optJSONObject("benefit")?.deepString("imageAssetURL", "imageURL", "imageUrl")?.let(::imageUrl) }
        ?: emptyList()

private fun JSONArray.objects(): List<JSONObject> =
    buildList {
        for (index in 0 until length()) optJSONObject(index)?.let(::add)
    }

private fun JSONObject.deepString(vararg keys: String): String? {
    for (key in keys) optString(key).takeIf(String::isNotBlank)?.let { return it }
    for (key in keys()) {
        when (val value = opt(key)) {
            is JSONObject -> value.deepString(*keys)?.let { return it }
            is JSONArray -> value.objects().firstNotNullOfOrNull { it.deepString(*keys) }?.let { return it }
        }
    }
    return null
}

private fun imageUrl(url: String?): String? =
    url?.takeIf(String::isNotBlank)
        ?.replace("{width}", "300")
        ?.replace("{height}", "400")

private fun progress(current: Int, required: Int): Float =
    if (required <= 0) 0f else (current.toFloat() / required.toFloat()).coerceIn(0f, 1f)

internal fun formatRemainingSeconds(seconds: Int): String {
    val safeSeconds = seconds.coerceAtLeast(0)
    val hours = safeSeconds / 3600
    val mins = (safeSeconds % 3600) / 60
    val secs = safeSeconds % 60
    return "%02d:%02d:%02d".format(hours, mins, secs)
}

private fun String?.orFallback(fallback: String): String =
    if (isNullOrBlank()) fallback else this

internal const val ANDROID_APP_CLIENT_ID = "kd1unb4b3q4t58fwlpcbzcbnm76a8fp"
private const val ANDROID_APP_USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 16; SM-S911B Build/TP1A.220624.014) tv.twitch.android.app/25.3.0/2503006"
private const val INVENTORY_HASH = "d86775d0ef16a63a33ad52e80eaff963b2d5b72fada7c991504a57496e1d8e4b"
private const val CAMPAIGNS_HASH = "5a4da2ab3d5b47c9f9ce864e727b2cb346af1e3ea8b897fe8f704a97ff017619"
private const val CAMPAIGN_DETAILS_HASH = "039277bf98f3130929262cc7c6efd9c141ca3749cb6dca442fc8ead9a53f77c1"
private const val GAME_DIRECTORY_HASH = "cb5dc816e139dcb8a118f14b4b677d59abc224a4b016c4bc2bb00a47fe0ddec4"
private const val GAME_REDIRECT_HASH = "1f0300090caceec51f33c5e20647aceff9017f740f223c3c532ba6fa59f6b6cc"
