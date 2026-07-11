package io.github.himanm.tdminer

class MinerCore(private val cookieStore: CookieStore) {
    var session: MinerSession = idleSession()
        private set

    fun start(): MinerSession {
        val jar = cookieStore.loadCookieJar()
        val ready = jar?.hasAuthToken == true
        session = MinerSession.running(loggedIn = ready, authReady = ready, userId = jar?.userId)
        return session
    }

    fun validateAuth(validator: (String) -> TwitchAuthResult = ::validateTwitchAuth): MinerSession {
        val jar = cookieStore.loadCookieJar()
        val token = jar?.authToken
        if (token.isNullOrBlank()) {
            session = session.copy(loggedIn = false, authReady = false, userId = null)
            return session
        }
        val result = validator(token)
        session = session.copy(loggedIn = result.valid, authReady = result.valid, userId = result.userId ?: jar.userId)
        return session
    }

    fun refreshDrops(
        settings: MinerSettings = MinerSettings(),
        onFetchProgress: (Int, Int) -> Unit = { _, _ -> },
        fetcher: (TwitchCookieJar, (Int, Int) -> Unit) -> List<TwitchDropSnapshot> = { jar, progress ->
            fetchInventorySnapshots(jar.authToken.orEmpty(), jar.userId, jar.cookieHeader, jar.deviceId, progress)
        },
    ): MinerSession {
        val jar = cookieStore.loadCookieJar()
        if (jar?.authToken.isNullOrBlank()) return session
        if (settings.priorityGames.isEmpty()) {
            session = session.copy(
                channel = "Priority empty",
                game = "No priority selected",
                campaign = "Add a priority game to start mining",
                drop = "Waiting for priority",
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
            )
            return session
        }
        val snapshots = fetcher(jar, onFetchProgress)
        val visibleDrops = filterPrioritySnapshots(snapshots, settings.priorityGames, settings.excludedGames)
        val snapshot = selectInventorySnapshot(snapshots, settings.priorityGames, settings.excludedGames) ?: run {
            session = session.copy(
                channel = "No matching drop",
                game = "No priority drop",
                campaign = "Priority/exclude filtered active drops",
                drop = "Waiting for matching campaign",
                gameImageUrl = null,
                dropImageUrl = null,
                rewards = emptyList(),
                rewardImageUrls = emptyList(),
                channels = emptyList(),
                drops = visibleDrops,
                remainingSeconds = 0,
                remaining = "--:--:--",
                campaignProgress = 0f,
                dropProgress = 0f,
            )
            return session
        }
        session = session.copy(
            channel = if (snapshot.channel == "Twitch") session.channel.takeUnless { it == "Twitch" } ?: "Finding channel" else snapshot.channel,
            game = snapshot.game,
            campaign = snapshot.campaign,
            drop = snapshot.drop,
            gameImageUrl = snapshot.gameImageUrl,
            dropImageUrl = snapshot.dropImageUrl,
            rewards = snapshot.rewards,
            rewardImageUrls = snapshot.rewardImageUrls,
            drops = visibleDrops,
            remainingSeconds = snapshot.remainingSeconds,
            remaining = snapshot.remaining,
            campaignProgress = snapshot.campaignProgress,
            dropProgress = snapshot.dropProgress,
        )
        return session
    }

    fun watchOnce(
        channelFetcher: (String, String) -> List<TwitchChannel> = { token, game -> fetchLiveChannelsForGame(token, game) },
        watcher: (String, String, TwitchChannel) -> Boolean = ::sendWatchMinute,
    ): MinerSession {
        val jar = cookieStore.loadCookieJar()
        val token = jar?.authToken
        val userId = session.userId ?: jar?.userId
        if (token.isNullOrBlank() || userId.isNullOrBlank() || !session.authReady) return session
        if (!session.running) return session
        if (session.game.isBlank() || session.game == "Loading drops" || session.game == "Unknown game") return session
        if (session.drops.isEmpty()) return session.copy(channels = emptyList())
        val channels = channelFetcher(token, session.game)
        val channel = channels.firstOrNull() ?: return session.copy(channel = "No live drops channel", channels = emptyList())
        watcher(token, userId, channel)
        session = session.copy(channel = channel.displayName, channels = channels)
        return session
    }

    fun switchChannel(
        channel: TwitchChannel,
        watcher: (String, String, TwitchChannel) -> Boolean = ::sendWatchMinute,
    ): MinerSession {
        val jar = cookieStore.loadCookieJar()
        val token = jar?.authToken
        val userId = session.userId ?: jar?.userId
        if (!token.isNullOrBlank() && !userId.isNullOrBlank() && session.authReady) {
            watcher(token, userId, channel)
        }
        session = session.copy(channel = channel.displayName)
        return session
    }

    fun loadCategories(fetcher: (String, String?, String?, String?) -> List<TwitchCategory> = ::fetchDropCategories): List<TwitchCategory> {
        val jar = cookieStore.loadCookieJar() ?: return emptyList()
        val token = jar.authToken ?: return emptyList()
        return fetcher(token, jar.userId, jar.cookieHeader, jar.deviceId)
    }

    fun stop(): MinerSession {
        session = idleSession()
        return session
    }

    fun saveCookies(cookies: String): MinerSession {
        cookieStore.saveCookies(cookies)
        val ready = TwitchCookieJar.parse(cookies).hasAuthToken
        session = session.copy(loggedIn = ready, authReady = ready, userId = TwitchCookieJar.parse(cookies).userId)
        return session
    }

    fun logout(): MinerSession {
        cookieStore.logout()
        session = MinerSession.idle(false)
        return session
    }

    private fun idleSession(): MinerSession {
        val jar = cookieStore.loadCookieJar()
        val ready = jar?.hasAuthToken == true
        return MinerSession.idle(loggedIn = ready, authReady = ready, userId = jar?.userId)
    }
}
