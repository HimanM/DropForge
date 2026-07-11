package io.github.himanm.tdminer

data class MinerSession(
    val running: Boolean,
    val channel: String,
    val game: String,
    val campaign: String,
    val drop: String,
    val gameImageUrl: String?,
    val dropImageUrl: String?,
    val rewards: List<String>,
    val rewardImageUrls: List<String>,
    val channels: List<TwitchChannel>,
    val drops: List<TwitchDropSnapshot>,
    val remainingSeconds: Int,
    val remaining: String,
    val campaignProgress: Float,
    val dropProgress: Float,
    val wakeLockActive: Boolean,
    val notificationActive: Boolean,
    val loggedIn: Boolean,
    val authReady: Boolean,
    val userId: String?,
) {
    companion object {
        fun running(loggedIn: Boolean = false, authReady: Boolean = loggedIn, userId: String? = null) = MinerSession(
            running = true,
            channel = "Finding channel",
            game = "Loading drops",
            campaign = "Validating Twitch session",
            drop = "Waiting for inventory",
            gameImageUrl = null,
            dropImageUrl = null,
            rewards = emptyList(),
            rewardImageUrls = emptyList(),
            channels = emptyList(),
            drops = emptyList(),
            remainingSeconds = 0,
            remaining = "--:--:--",
            campaignProgress = 0f,
            dropProgress = 0f,
            wakeLockActive = true,
            notificationActive = true,
            loggedIn = loggedIn,
            authReady = authReady,
            userId = userId,
        )

        fun idle(loggedIn: Boolean = false, authReady: Boolean = loggedIn, userId: String? = null) = running(loggedIn, authReady, userId).copy(
            running = false,
            channel = "Not watching",
            game = "Ready",
            campaign = "Press Start to mine drops",
            drop = "No active drop",
            remaining = "--:--:--",
            wakeLockActive = false,
            notificationActive = false,
        )
    }
}
