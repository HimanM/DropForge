package io.github.himanm.tdminer

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.automirrored.outlined.ViewList
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Campaign
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Dashboard
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Terminal
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.NavigationRailItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.roundToInt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.URL

private val Paper = Color(0xFFF1EBDD)
private val Ink = Color(0xFF101513)
private val Muted = Color(0xFF9DA8A1)
private val Rule = Color(0xFF34413C)
private val Green = Color(0xFF37E2B2)
private val Orange = Color(0xFFFF665A)
private val Panel = Color(0xFF18201D)
private val DisplayFont = FontFamily(
    Font(R.font.roboto_condensed_regular, FontWeight.Normal),
    Font(R.font.roboto_condensed_bold, FontWeight.Bold),
    Font(R.font.roboto_condensed_black, FontWeight.Black),
)
private val AppColors = darkColorScheme(
    primary = Green,
    secondary = Green,
    tertiary = Orange,
    background = Ink,
    surface = Panel,
    surfaceVariant = Color(0xFF222C28),
    onPrimary = Ink,
    onSecondary = Ink,
    onBackground = Paper,
    onSurface = Paper,
)

private data class AppTab(val title: String, val icon: ImageVector)

private val Tabs = listOf(
    AppTab("Home", Icons.Outlined.Dashboard),
    AppTab("Drops", Icons.Outlined.Campaign),
    AppTab("Channels", Icons.AutoMirrored.Outlined.ViewList),
    AppTab("Prefs", Icons.Outlined.Settings),
    AppTab("Logs", Icons.Outlined.Terminal),
)

@Composable
fun TDMinerApp(
    core: MinerCore,
    settingsStore: MinerSettingsStore,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onOpenUrl: (String) -> Unit,
) {
    var selected by remember { mutableIntStateOf(0) }
    var session by remember { mutableStateOf(core.session) }
    var showLogoutConfirm by remember { mutableStateOf(false) }
    var notice by remember { mutableStateOf<String?>(null) }
    val savedSettings = remember { settingsStore.load() }
    val scope = rememberCoroutineScope()
    val priority = remember { mutableStateListOf<String>().also { it.addAll(savedSettings.priorityGames) } }
    val excluded = remember { mutableStateListOf<String>().also { it.addAll(savedSettings.excludedGames) } }
    var priorityInput by remember { mutableStateOf("") }
    var excludedInput by remember { mutableStateOf("") }
    var availableCategories by remember { mutableStateOf(emptyList<TwitchCategory>()) }
    var priorityResults by remember { mutableStateOf(emptyList<TwitchCategory>()) }
    var excludedResults by remember { mutableStateOf(emptyList<TwitchCategory>()) }
    var categoriesLoading by remember { mutableStateOf(true) }
    var miningLoading by remember { mutableStateOf(false) }
    var loginCode by remember { mutableStateOf<TwitchDeviceCode?>(null) }
    var loginLoading by remember { mutableStateOf(false) }
    var loginError by remember { mutableStateOf<String?>(null) }
    var farmUnlinked by remember { mutableStateOf(savedSettings.farmUnlinkedDrops) }
    var badgeEmote by remember { mutableStateOf(savedSettings.badgeEmoteSupport) }
    var notifications by remember { mutableStateOf(savedSettings.notificationsEnabled) }
    var wakeLock by remember { mutableStateOf(savedSettings.wakeLockEnabled) }
    suspend fun fetchAndCacheCategories(showNotice: Boolean) {
        categoriesLoading = true
        try {
            val categories = withContext(Dispatchers.IO) { core.loadCategories() }
            if (categories.isNotEmpty()) {
                availableCategories = categories
                settingsStore.saveCategoryCache(categories)
                if (showNotice) notice = "Drop game list reloaded"
            } else if (showNotice) {
                notice = "No drop games returned"
            }
        } catch (_: Exception) {
            if (showNotice) notice = "Could not reload drop games"
        } finally {
            categoriesLoading = false
        }
    }
    fun reloadCategories(showNotice: Boolean = true) {
        scope.launch { fetchAndCacheCategories(showNotice) }
    }
    LaunchedEffect(Unit) {
        val cache = settingsStore.loadCategoryCache()
        availableCategories = cache.categories
        if (!cache.isFresh(System.currentTimeMillis())) {
            fetchAndCacheCategories(showNotice = false)
        } else {
            categoriesLoading = false
        }
    }
    LaunchedEffect(priorityInput, availableCategories) {
        priorityResults = matchLoadedCategories(availableCategories, priorityInput)
    }
    LaunchedEffect(excludedInput, availableCategories) {
        excludedResults = matchLoadedCategories(availableCategories, excludedInput)
    }
    LaunchedEffect(session.running, session.game, session.campaign, session.drop) {
        while (session.running) {
            delay(1000)
            session = session.let { current ->
                if (!current.running || current.remainingSeconds <= 0) {
                    current
                } else {
                    val next = (current.remainingSeconds - 1).coerceAtLeast(0)
                    val drops = current.drops.map { drop ->
                        if (drop.game == current.game && drop.campaign == current.campaign && drop.drop == current.drop) {
                            drop.copy(remainingSeconds = next)
                        } else {
                            drop
                        }
                    }
                    current.copy(drops = drops, remainingSeconds = next, remaining = formatRemainingSeconds(next))
                }
            }
        }
    }
    fun currentSettings(): MinerSettings {
        val cleanPriority = normalizeSettingsList(priority)
        return MinerSettings(
            priorityGames = cleanPriority,
            excludedGames = normalizeSettingsList(excluded).filterNot { it in cleanPriority.toSet() },
            farmUnlinkedDrops = farmUnlinked,
            badgeEmoteSupport = badgeEmote,
            notificationsEnabled = notifications,
            wakeLockEnabled = wakeLock,
        )
    }
    fun onFetchProgress(done: Int, total: Int) {
        scope.launch {
            val progress = if (total <= 0) 0f else done.toFloat() / total.toFloat()
            session = core.session.copy(
                campaign = "Fetching drop campaigns",
                drop = "$done/$total campaigns loaded",
                campaignProgress = progress,
                dropProgress = progress,
            )
        }
    }
    val start = {
        if (!miningLoading && !categoriesLoading) {
            session = core.start()
            miningLoading = true
            scope.launch {
                session = withContext(Dispatchers.IO) {
                try {
                    val validated = core.validateAuth()
                    if (validated.authReady) {
                        core.refreshDrops(currentSettings(), onFetchProgress = ::onFetchProgress)
                        core.watchOnce()
                    } else {
                        validated
                    }
                } catch (_: Exception) {
                    core.session
                }
                }
                miningLoading = false
                if (session.authReady && session.running) onStart()
            }
        }
        Unit
    }
    val stop = {
        session = core.stop()
        onStop()
    }
    val logout = {
        session = core.logout()
        showLogoutConfirm = false
        notice = "Saved Twitch session cleared"
        onStop()
    }
    fun beginLogin() {
        if (loginLoading) return
        loginLoading = true
        loginError = null
        scope.launch {
            try {
                val code = withContext(Dispatchers.IO) { requestTwitchDeviceCode() }
                loginCode = code
                onOpenUrl(code.verificationUrl)
                val cookies = withContext(Dispatchers.IO) { awaitTwitchDeviceLogin(code) }
                session = core.saveCookies(cookies)
                loginCode = null
                notice = "Twitch account connected"
                reloadCategories(showNotice = false)
            } catch (error: Exception) {
                loginError = error.message?.take(120) ?: "Could not start Twitch login"
            } finally {
                loginLoading = false
            }
        }
    }
    fun refreshSessionFromSettings() {
        scope.launch {
            session = withContext(Dispatchers.IO) {
                try {
                    core.refreshDrops(currentSettings(), onFetchProgress = ::onFetchProgress)
                    core.watchOnce()
                } catch (_: Exception) {
                    core.session
                }
            }
        }
    }
    fun saveLists() {
        saveSettings(settingsStore, priority, excluded, farmUnlinked, badgeEmote, notifications, wakeLock)
        refreshSessionFromSettings()
    }
    fun movePriority(from: Int, to: Int) {
        if (from !in priority.indices || to !in priority.indices || from == to) return
        val item = priority.removeAt(from)
        priority.add(to, item)
        saveLists()
        notice = "Priority order updated"
    }

    MaterialTheme(colorScheme = AppColors) {
        Surface(color = Ink, modifier = Modifier.fillMaxSize()) {
            if (!session.loggedIn) {
                LoginScreen(loginCode, loginLoading, loginError, ::beginLogin, onOpenUrl)
                return@Surface
            }
            BoxWithConstraints(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
                val wide = maxWidth >= 720.dp
                Scaffold(
                    modifier = Modifier.fillMaxSize(),
                    containerColor = Ink,
                    contentWindowInsets = WindowInsets(0, 0, 0, 0),
                    bottomBar = {
                        if (!wide) {
                            NavigationBar(containerColor = Ink, tonalElevation = 0.dp) {
                                Tabs.forEachIndexed { index, tab ->
                                    NavigationBarItem(
                                        selected = selected == index,
                                        onClick = { selected = index },
                                        icon = { Icon(tab.icon, contentDescription = tab.title) },
                                        label = { Text(tab.title) },
                                        colors = NavigationBarItemDefaults.colors(
                                            selectedIconColor = Green,
                                            selectedTextColor = Green,
                                            indicatorColor = Color.Transparent,
                                            unselectedIconColor = Muted,
                                            unselectedTextColor = Muted,
                                        ),
                                    )
                                }
                            }
                        }
                    },
                ) { padding ->
                    Row(Modifier.fillMaxSize().padding(padding)) {
                        if (wide) {
                            NavigationRail(containerColor = Ink) {
                                Tabs.forEachIndexed { index, tab ->
                                    NavigationRailItem(
                                        selected = selected == index,
                                        onClick = { selected = index },
                                        icon = { Icon(tab.icon, contentDescription = tab.title) },
                                        label = { Text(tab.title) },
                                        colors = NavigationRailItemDefaults.colors(
                                            selectedIconColor = Green,
                                            selectedTextColor = Green,
                                            indicatorColor = Color.Transparent,
                                            unselectedIconColor = Muted,
                                            unselectedTextColor = Muted,
                                        ),
                                    )
                                }
                            }
                        }
                        Box(Modifier.fillMaxSize()) {
                            when (selected) {
                                0 -> Dashboard(session, miningLoading, categoriesLoading, start, stop)
                                1 -> Campaigns(session, availableCategories)
                                2 -> Channels(session) { channel ->
                                    scope.launch {
                                        session = withContext(Dispatchers.IO) { core.switchChannel(channel) }
                                    }
                                    notice = "Watching ${channel.displayName}"
                                }
                                3 -> Settings(
                                    session = session,
                                    priority = priority,
                                    excluded = excluded,
                                    priorityInput = priorityInput,
                                    excludedInput = excludedInput,
                                    availableCategories = availableCategories,
                                    priorityResults = priorityResults,
                                    excludedResults = excludedResults,
                                    categoriesLoading = categoriesLoading,
                                    farmUnlinked = farmUnlinked,
                                    badgeEmote = badgeEmote,
                                    notifications = notifications,
                                    wakeLock = wakeLock,
                                    onPriorityInput = { priorityInput = it },
                                    onExcludedInput = { excludedInput = it },
                                    onPickPriority = { category ->
                                        normalizeSettingsList(listOf(category.name) + priority).also {
                                            priority.clear()
                                            priority.addAll(it)
                                        }
                                        excluded.remove(category.name)
                                        priorityInput = ""
                                        priorityResults = emptyList()
                                        saveLists()
                                        notice = "Priority list updated"
                                    },
                                    onPickExcluded = { category ->
                                        normalizeSettingsList(excluded + category.name).also {
                                            excluded.clear()
                                            excluded.addAll(it)
                                        }
                                        priority.remove(category.name)
                                        excludedInput = ""
                                        excludedResults = emptyList()
                                        saveLists()
                                        notice = "Excluded list updated"
                                    },
                                    onRemovePriority = {
                                        priority.remove(it)
                                        saveLists()
                                        notice = "Priority list updated"
                                    },
                                    onMovePriority = ::movePriority,
                                    onRemoveExcluded = {
                                        excluded.remove(it)
                                        saveLists()
                                        notice = "Excluded list updated"
                                    },
                                    onFarmUnlinkedChange = {
                                        farmUnlinked = it
                                        saveLists()
                                    },
                                    onBadgeEmoteChange = {
                                        badgeEmote = it
                                        saveLists()
                                    },
                                    onNotificationsChange = {
                                        notifications = it
                                        saveLists()
                                    },
                                    onWakeLockChange = {
                                        wakeLock = it
                                        saveLists()
                                    },
                                    onReloadCategories = { reloadCategories(showNotice = true) },
                                    onLogoutClick = { showLogoutConfirm = true },
                                )
                                else -> Logs(session, availableCategories.size)
                            }
                            if (showLogoutConfirm) {
                                LogoutDialog(
                                    onCancel = { showLogoutConfirm = false },
                                    onConfirm = logout,
                                )
                            }
                            notice?.let {
                                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.BottomCenter) {
                                    NoticeBanner(it)
                                }
                                LaunchedEffect(it) {
                                    delay(1800)
                                    notice = null
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun LoginScreen(
    code: TwitchDeviceCode?,
    loading: Boolean,
    error: String?,
    onBegin: () -> Unit,
    onOpenUrl: (String) -> Unit,
) {
    Column(
        Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing).padding(28.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("TDM / MOBILE", style = mono(17, FontWeight.Black), color = Green)
            Text("CONNECT\nTWITCH", style = swiss(48, FontWeight.Black))
            Text("One account. Stored privately on this device.", style = swiss(15), color = Muted)
        }
        ModernCard {
            if (code == null) {
                Text("DEVICE LOGIN", style = mono(12, FontWeight.Bold), color = Green)
                Text("Twitch opens in your browser. Approve this device, then return here.", style = swiss(16, FontWeight.Bold))
            } else {
                Text("ENTER THIS CODE", style = mono(12, FontWeight.Bold), color = Green)
                Text(code.userCode, style = mono(38, FontWeight.Black))
                Text("Waiting for Twitch approval...", style = swiss(14), color = Muted)
            }
            error?.let { Text(it, style = swiss(13, FontWeight.Bold), color = Orange) }
            PrimaryButton(
                text = when {
                    code != null -> "OPEN TWITCH AGAIN"
                    loading -> "REQUESTING CODE"
                    else -> "CONNECT TWITCH"
                },
                color = Green,
                onClick = { if (code == null) onBegin() else onOpenUrl(code.verificationUrl) },
                enabled = code != null || !loading,
            )
        }
        Text("No password is entered into TD Miner.", style = mono(11), color = Muted)
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun Dashboard(session: MinerSession, miningLoading: Boolean, categoriesLoading: Boolean, onStart: () -> Unit, onStop: () -> Unit) {
    val busy = miningLoading || categoriesLoading
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().height(68.dp).padding(horizontal = 20.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("TDM / MOBILE", style = mono(18, FontWeight.Black))
            Text("v19.3   ●", style = mono(13, FontWeight.Bold), color = Green)
        }
        Box(Modifier.fillMaxWidth().weight(1f).background(Panel)) {
            NetworkImage(session.gameImageUrl, Modifier.fillMaxSize(), alignment = Alignment.TopCenter)
            Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = if (session.gameImageUrl == null) 0.25f else 0.48f)))
            Column(Modifier.align(Alignment.BottomStart).padding(22.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                Text(session.game.uppercase(), style = swiss(42, FontWeight.Black))
                Text("CAMPAIGN", style = mono(12, FontWeight.Bold), color = Green)
                Text(session.campaign, style = swiss(22, FontWeight.Black))
                Spacer(Modifier.height(6.dp))
                Text("WATCHING", style = mono(12, FontWeight.Bold), color = Green)
                Text(session.channel, style = swiss(22, FontWeight.Black))
            }
        }
        Column(Modifier.padding(horizontal = 20.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Reward(session.drop.take(10), session.dropImageUrl)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text("ACTIVE REWARD", style = mono(11, FontWeight.Bold), color = Green)
                    Text(session.drop, style = swiss(18, FontWeight.Black))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("${(session.dropProgress * 100).toInt()}%", style = mono(24, FontWeight.Bold), color = Green)
                        Text(session.remaining, style = mono(19, FontWeight.Bold))
                    }
                }
            }
            if (categoriesLoading) {
                LinearProgressIndicator(
                    modifier = Modifier.fillMaxWidth(),
                    color = Green,
                    trackColor = Rule,
                )
            } else {
                ProgressLine("", "", session.dropProgress)
            }
            PrimaryButton(
                text = if (categoriesLoading) "LOADING DROP GAMES" else if (miningLoading) "LOADING CAMPAIGNS" else if (session.running) "STOP MINING" else "START MINING",
                color = if (session.running && !busy) Orange else Green,
                onClick = if (session.running && !busy) onStop else onStart,
                enabled = !busy,
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                Metric("${session.drops.map { it.game }.distinct().size}", "DROP GAMES")
                Metric("${session.channels.size}", "LIVE CHANNELS")
                Metric(if (session.wakeLockActive) "ON" else "OFF", "WAKE LOCK")
            }
        }
    }
}

@Composable
private fun Campaigns(session: MinerSession, categories: List<TwitchCategory>) = LockedPage(
    title = "CAMPAIGNS",
    subtitle = "${categories.size} searchable drop games · ${session.drops.size} timed drops · ${session.channels.size} live",
) {
    if (session.drops.isEmpty()) {
        Text("Add a priority game to show drops here. Cached games are only search suggestions.", style = swiss(14), color = Muted)
    }
    session.drops.groupBy { it.game }.forEach { (_, drops) ->
        DropGroupCard(drops, session)
    }
}

@Composable
private fun Channels(session: MinerSession, onSwitch: (TwitchChannel) -> Unit) = LockedPage(
    title = "CHANNEL SIGNAL",
    subtitle = "${session.game} · Drops enabled · ${session.channels.size} online",
) {
    if (session.channels.isEmpty()) {
        Text("No live channels loaded yet. Press Start to fetch drops-enabled channels for ${session.game}.", style = swiss(14), color = Muted)
    }
    session.channels.forEach { channel ->
        val watching = channel.displayName == session.channel
        Row(
            Modifier.fillMaxWidth().clickable { onSwitch(channel) }.border(if (watching) 1.dp else 0.dp, if (watching) Green else Color.Transparent).padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.size(58.dp).border(1.dp, Rule), contentAlignment = Alignment.Center) {
                Text(channel.displayName.take(1).uppercase(), style = swiss(24, FontWeight.Black), color = if (watching) Green else Paper)
            }
            Column(Modifier.weight(1f)) {
                Text(channel.displayName, style = swiss(17, FontWeight.Black))
                Text(channel.gameName, style = mono(12), color = Muted)
                if (watching) Text("WATCHING", style = mono(11, FontWeight.Bold), color = Green)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text("${channel.viewers}", style = mono(14, FontWeight.Bold))
                Text("● DROPS ON", style = mono(11, FontWeight.Bold), color = Green)
            }
        }
    }
}

@Composable
private fun Settings(
    session: MinerSession,
    priority: List<String>,
    excluded: List<String>,
    priorityInput: String,
    excludedInput: String,
    availableCategories: List<TwitchCategory>,
    priorityResults: List<TwitchCategory>,
    excludedResults: List<TwitchCategory>,
    categoriesLoading: Boolean,
    farmUnlinked: Boolean,
    badgeEmote: Boolean,
    notifications: Boolean,
    wakeLock: Boolean,
    onPriorityInput: (String) -> Unit,
    onExcludedInput: (String) -> Unit,
    onPickPriority: (TwitchCategory) -> Unit,
    onPickExcluded: (TwitchCategory) -> Unit,
    onRemovePriority: (String) -> Unit,
    onMovePriority: (Int, Int) -> Unit,
    onRemoveExcluded: (String) -> Unit,
    onFarmUnlinkedChange: (Boolean) -> Unit,
    onBadgeEmoteChange: (Boolean) -> Unit,
    onNotificationsChange: (Boolean) -> Unit,
    onWakeLockChange: (Boolean) -> Unit,
    onReloadCategories: () -> Unit,
    onLogoutClick: () -> Unit,
) {
    var expanded by remember { mutableIntStateOf(0) }
    var browser by remember { mutableIntStateOf(-1) }
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text("GAME ROUTING", style = swiss(30, FontWeight.Black))
            Text(
                "PRIORITIZE WHAT TO MINE. EXCLUDED GAMES WON'T BE WATCHED.",
                style = mono(8, FontWeight.Bold),
                color = Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Spacer(Modifier.width(10.dp))
        OutlinedButton(
            onClick = onReloadCategories,
            enabled = !categoriesLoading,
            shape = RoundedCornerShape(2.dp),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = Green),
            border = BorderStroke(1.dp, Green),
            contentPadding = PaddingValues(0.dp),
            modifier = Modifier.width(84.dp).height(40.dp),
        ) {
            Text(if (categoriesLoading) "LOADING" else "RELOAD", style = mono(11, FontWeight.Bold))
        }
    }
    CategoryListEditor(
        title = "PRIORITY QUEUE",
        helper = "Drag to reorder · mines top available",
        addLabel = "ADD PRIORITY GAME",
        items = priority,
        value = priorityInput,
        placeholder = "Search loaded drop game",
        results = priorityResults,
        categoriesLoaded = availableCategories.isNotEmpty(),
        categoriesLoading = categoriesLoading,
        onValueChange = onPriorityInput,
        onPick = onPickPriority,
        onRemove = onRemovePriority,
        onMove = onMovePriority,
        imageUrl = { name -> availableCategories.firstOrNull { it.name == name }?.boxArtUrl() },
        expanded = expanded == 0,
        browserOpen = browser == 0,
        onHeaderClick = { expanded = 0; browser = -1 },
        onAddClick = { expanded = 0; browser = if (browser == 0) -1 else 0 },
        modifier = if (expanded == 0) Modifier.weight(1f) else Modifier.height(62.dp),
    )
    CategoryListEditor(
        title = "EXCLUDED GAMES",
        helper = "Never watched or mined",
        addLabel = "ADD EXCLUDED GAME",
        items = excluded,
        value = excludedInput,
        placeholder = "Search loaded drop game",
        results = excludedResults,
        categoriesLoaded = availableCategories.isNotEmpty(),
        categoriesLoading = categoriesLoading,
        onValueChange = onExcludedInput,
        onPick = onPickExcluded,
        onRemove = onRemoveExcluded,
        imageUrl = { name -> availableCategories.firstOrNull { it.name == name }?.boxArtUrl() },
        expanded = expanded == 1,
        browserOpen = browser == 1,
        onHeaderClick = { expanded = 1; browser = -1 },
        onAddClick = { expanded = 1; browser = if (browser == 1) -1 else 1 },
        modifier = if (expanded == 1) Modifier.weight(1f) else Modifier.height(62.dp),
    )
    ModernCard(
        (if (expanded == 2) Modifier.weight(1f) else Modifier.height(62.dp)).clickable { expanded = 2; browser = -1 },
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column {
                Text("BEHAVIOR", style = swiss(16, FontWeight.Black), color = Green)
                Text("Notifications, partial rewards and power", style = swiss(10), color = Muted)
            }
            Text(if (expanded == 2) "−" else "+", style = mono(18, FontWeight.Bold), color = Green)
        }
        if (expanded == 2) {
            ToggleRow("Partial badges & emotes", badgeEmote, onBadgeEmoteChange, "Accept partial progress")
            ToggleRow("Farm unlinked", farmUnlinked, onFarmUnlinkedChange, "Allow drops from unlinked channels")
            ToggleRow("Notifications", notifications, onNotificationsChange, "Show mining alerts")
            ToggleRow("Wake lock", wakeLock, onWakeLockChange, "Keep device awake while mining")
            Text("${availableCategories.size} DROP GAMES CACHED", style = mono(10, FontWeight.Bold), color = Muted)
        }
    }
    OutlinedButton(
        onClick = onLogoutClick,
        shape = RoundedCornerShape(2.dp),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = Orange),
        border = BorderStroke(1.dp, Orange),
        modifier = Modifier.fillMaxWidth().height(44.dp),
    ) {
            Icon(Icons.AutoMirrored.Outlined.Logout, contentDescription = null, tint = Orange)
            Spacer(Modifier.size(6.dp))
            Text("LOG OUT", color = Orange)
    }
    }
}

@Composable
private fun Logs(session: MinerSession, categoryCount: Int) = LockedPage(
    title = "EVENT STREAM",
    trailing = "● LIVE",
) {
    Row(Modifier.fillMaxWidth().border(1.dp, Rule).padding(16.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
        Metric(if (session.running) "RUN" else "IDLE", session.remaining)
        Metric("NET", "OK")
        Metric("COOKIE", if (session.loggedIn) "SAVED" else "MISSING")
    }
    listOf(
        "10:42:31" to "Watching ${session.channel}",
        "10:41:07" to "Selected ${session.game}",
        "10:40:22" to "Loaded ${session.drops.size} drops",
        "10:39:41" to "Found $categoryCount drop games",
        "10:38:56" to if (session.authReady) "Authentication restored" else "Authentication required",
    ).forEachIndexed { index, event ->
        Row(Modifier.fillMaxWidth().height(72.dp).border(0.dp, Color.Transparent), verticalAlignment = Alignment.CenterVertically) {
            Text(event.first, style = mono(13), color = Muted, modifier = Modifier.width(92.dp))
            Text(if (index == 0) "◉" else "◇", color = Green, style = mono(18), modifier = Modifier.width(44.dp))
            Text(event.second, style = mono(14), modifier = Modifier.weight(1f))
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(Rule))
    }
}

@Composable
private fun LockedPage(
    title: String,
    subtitle: String? = null,
    trailing: String? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text(title, style = swiss(34, FontWeight.Black))
            trailing?.let { Text(it, style = mono(12, FontWeight.Bold), color = Green) }
        }
        subtitle?.let { Text(it, style = mono(12), color = Muted) }
        Box(Modifier.fillMaxWidth().height(1.dp).background(Rule))
        Column(
            Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            content = content,
        )
    }
}

@Composable
private fun ModernCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    ElevatedCard(
        colors = CardDefaults.elevatedCardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(4.dp),
        elevation = CardDefaults.elevatedCardElevation(0.dp),
        modifier = modifier.fillMaxWidth().border(1.dp, Rule, RoundedCornerShape(4.dp)),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content)
    }
}

@Composable
private fun Artwork(session: MinerSession) {
    Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
        ArtworkBlock(session.game.replace(": ", ":\n"), session.gameImageUrl)
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(session.campaign, style = swiss(22, FontWeight.Bold))
            RewardRow(session)
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun DropGroupCard(drops: List<TwitchDropSnapshot>, session: MinerSession) {
    val first = drops.first()
    Column(Modifier.fillMaxWidth().border(1.dp, Rule)) {
        Box(Modifier.fillMaxWidth().height(150.dp).background(Panel)) {
            NetworkImage(first.gameImageUrl, Modifier.fillMaxSize())
            Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.45f)))
            Column(Modifier.align(Alignment.BottomStart).padding(16.dp)) {
                Text(first.game.uppercase(), style = swiss(28, FontWeight.Black))
                Text("${drops.map { it.campaign }.distinct().size} CAMPAIGNS · ${drops.size} TIMED DROPS", style = mono(11), color = Muted)
                if (drops.any { it.game == session.game }) Text("● MINING", style = mono(12, FontWeight.Bold), color = Green)
            }
        }
        drops.forEach { drop ->
            val selected = drop.game == session.game && drop.campaign == session.campaign && drop.drop == session.drop
            DropItemRow(drop, selected, session.running, if (selected) session.remaining else drop.remaining)
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun DropItemRow(drop: TwitchDropSnapshot, selected: Boolean, running: Boolean, remaining: String) {
    Row(
        Modifier.fillMaxWidth().background(if (selected) Green.copy(alpha = 0.07f) else Panel).border(if (selected) 1.dp else 0.dp, if (selected) Green else Color.Transparent).padding(10.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        NetworkImage(drop.dropImageUrl ?: drop.rewardImageUrls.firstOrNull(), Modifier.size(58.dp).clip(RoundedCornerShape(3.dp)))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(drop.drop, style = swiss(14, FontWeight.Bold))
            Text(drop.campaign, style = swiss(11), color = Muted)
            ProgressLine("", "", drop.dropProgress)
        }
        Column(horizontalAlignment = Alignment.End) {
            Text("${(drop.dropProgress * 100).toInt()}%", style = mono(16, FontWeight.Bold), color = if (selected) Green else Paper)
            Text(remaining, style = mono(12, FontWeight.Bold), color = if (selected && running) Green else Muted)
        }
    }
}

@Composable
private fun ArtworkBlock(text: String, imageUrl: String? = null, modifier: Modifier = Modifier.size(width = 96.dp, height = 128.dp)) {
    Box(
        modifier.background(Ink, RoundedCornerShape(2.dp)),
        contentAlignment = Alignment.BottomStart,
    ) {
        NetworkImage(imageUrl, Modifier.fillMaxSize())
        if (imageUrl != null) Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.25f)))
        Text(text, style = swiss(14, FontWeight.Bold), color = Paper, modifier = Modifier.padding(10.dp))
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun RewardRow(session: MinerSession) {
    val rewards = session.rewards.ifEmpty { listOf(session.drop) }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        rewards.take(4).forEachIndexed { index, reward ->
            Reward(reward.take(10), session.rewardImageUrls.getOrNull(index))
        }
    }
}

@Composable
private fun SettingRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(20.dp)).padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = swiss(15, FontWeight.Bold))
        Text(value, style = swiss(15), color = Muted)
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun CategoryListEditor(
    title: String,
    helper: String,
    addLabel: String,
    items: List<String>,
    value: String,
    placeholder: String,
    results: List<TwitchCategory>,
    categoriesLoaded: Boolean,
    categoriesLoading: Boolean,
    onValueChange: (String) -> Unit,
    onPick: (TwitchCategory) -> Unit,
    onRemove: (String) -> Unit,
    onMove: ((Int, Int) -> Unit)? = null,
    imageUrl: (String) -> String? = { null },
    expanded: Boolean,
    browserOpen: Boolean,
    onHeaderClick: () -> Unit,
    onAddClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ModernCard(modifier) {
        Row(
            Modifier.fillMaxWidth().clickable(onClick = onHeaderClick),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(title, style = swiss(16, FontWeight.Black), color = Green)
                Text(helper, style = swiss(11), color = Muted)
            }
            Text("${items.size}  ${if (expanded) "−" else "+"}", style = mono(13, FontWeight.Bold), color = Green)
        }
        if (expanded) {
            if (!browserOpen) {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().weight(1f).border(1.dp, Rule, RoundedCornerShape(2.dp)),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    itemsIndexed(items) { index, item ->
                        if (onMove == null) {
                            CompactListRow(item, imageUrl(item), onRemove)
                        } else {
                            DraggablePriorityRow(
                                item = item,
                                imageUrl = imageUrl(item),
                                index = index,
                                lastIndex = items.lastIndex,
                                onMove = onMove,
                                onRemove = onRemove,
                            )
                        }
                    }
                }
                OutlinedButton(
                    onClick = onAddClick,
                    shape = RoundedCornerShape(2.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Green),
                    border = BorderStroke(1.dp, Green),
                    modifier = Modifier.fillMaxWidth().height(46.dp),
                ) { Text("+ $addLabel", style = mono(12, FontWeight.Bold)) }
            } else {
                BrowseCategoryPanel(
                    title = if (onMove == null) "ADD TO EXCLUDED" else "ADD TO PRIORITY",
                    value = value,
                    results = results,
                    categoriesLoaded = categoriesLoaded,
                    categoriesLoading = categoriesLoading,
                    onValueChange = onValueChange,
                    onPick = onPick,
                    onClose = onAddClick,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

@Composable
private fun BrowseCategoryPanel(
    title: String,
    value: String,
    results: List<TwitchCategory>,
    categoriesLoaded: Boolean,
    categoriesLoading: Boolean,
    onValueChange: (String) -> Unit,
    onPick: (TwitchCategory) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier.border(1.dp, Rule).padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text(title, style = mono(12, FontWeight.Bold), color = Green)
            TextButton(onClick = onClose) { Text("×", style = swiss(20), color = Green) }
        }
            OutlinedTextField(
                value = value,
                onValueChange = onValueChange,
                placeholder = { Text("Search drop games") },
                singleLine = true,
                shape = RoundedCornerShape(2.dp),
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = Color.Transparent,
                    unfocusedContainerColor = Color.Transparent,
                    focusedIndicatorColor = Green,
                    unfocusedIndicatorColor = Rule,
                    cursorColor = Green,
                ),
                modifier = Modifier.fillMaxWidth().height(56.dp),
            )
            when {
                categoriesLoading -> Text("Loading drop categories first...", style = swiss(13), color = Muted)
                value.length >= 2 && !categoriesLoaded -> Text("Drop categories are still loading", style = swiss(13, FontWeight.Bold), color = Orange)
                value.length >= 2 && results.isEmpty() -> Text("No active or upcoming drop game found", style = swiss(13, FontWeight.Bold), color = Orange)
            }
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                itemsIndexed(results) { _, category ->
                OutlinedButton(
                    onClick = { onPick(category) },
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Paper),
                    border = BorderStroke(1.dp, Rule),
                    shape = RoundedCornerShape(2.dp),
                    modifier = Modifier.fillMaxWidth().height(46.dp),
                ) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            NetworkImage(category.boxArtUrl(), Modifier.size(width = 54.dp, height = 34.dp).clip(RoundedCornerShape(2.dp)))
                            Text(category.name, style = swiss(14, FontWeight.Bold), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        Text(if (title.contains("EXCLUDED")) "EXCLUDE" else "ADD", style = swiss(12, FontWeight.Bold), color = Green)
                    }
                }
            }
        }
    }
}

@Composable
private fun DraggablePriorityRow(
    item: String,
    imageUrl: String?,
    index: Int,
    lastIndex: Int,
    onMove: (Int, Int) -> Unit,
    onRemove: (String) -> Unit,
) {
    var dragY by remember { mutableStateOf(0f) }
    Row(
        Modifier
            .fillMaxWidth()
            .offset { IntOffset(0, dragY.roundToInt()) }
            .background(Panel)
            .padding(horizontal = 10.dp, vertical = 7.dp)
            .pointerInput(index, lastIndex) {
                detectDragGesturesAfterLongPress(
                    onDragEnd = { dragY = 0f },
                    onDragCancel = { dragY = 0f },
                    onDrag = { change, dragAmount ->
                        change.consume()
                        dragY += dragAmount.y
                        when {
                            dragY > 48f && index < lastIndex -> {
                                onMove(index, index + 1)
                                dragY = 0f
                            }
                            dragY < -48f && index > 0 -> {
                                onMove(index, index - 1)
                                dragY = 0f
                            }
                        }
                    },
                )
            },
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("⋮⋮", style = mono(16, FontWeight.Bold), color = Green)
            NetworkImage(imageUrl, Modifier.size(width = 68.dp, height = 42.dp).clip(RoundedCornerShape(2.dp)))
            Text("${(index + 1).toString().padStart(2, '0')}", style = mono(13, FontWeight.Bold), color = Muted)
            Text(item, style = swiss(14, FontWeight.Bold))
        }
        TextButton(onClick = { onRemove(item) }) {
            Text("×", style = swiss(20), color = Green)
        }
    }
}

@Composable
private fun CompactListRow(item: String, imageUrl: String?, onRemove: (String) -> Unit) {
    Row(
        Modifier.fillMaxWidth().background(Panel).padding(horizontal = 10.dp, vertical = 7.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        NetworkImage(imageUrl, Modifier.size(width = 68.dp, height = 42.dp).clip(RoundedCornerShape(2.dp)))
        Spacer(Modifier.width(10.dp))
        Text(item, style = swiss(14, FontWeight.Bold), modifier = Modifier.weight(1f))
        TextButton(onClick = { onRemove(item) }) { Text("×", style = swiss(20), color = Green) }
    }
}

@Composable
private fun ToggleRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit, subtitle: String? = null) {
    Row(
        Modifier.fillMaxWidth().height(if (subtitle == null) 44.dp else 48.dp).border(1.dp, Rule)
            .clickable { onCheckedChange(!checked) }.padding(horizontal = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, style = swiss(12, FontWeight.Bold))
            subtitle?.let { Text(it, style = swiss(9), color = Muted) }
        }
        Box(
            Modifier.size(36.dp)
                .background(if (checked) Green else Ink)
                .border(1.dp, if (checked) Green else Muted),
            contentAlignment = Alignment.Center,
        ) {
            Text(if (checked) "ON" else "OFF", style = mono(9, FontWeight.Black), color = if (checked) Ink else Muted)
        }
    }
}

@Composable
private fun NoticeBanner(text: String) {
    Surface(
        color = Panel,
        shape = RoundedCornerShape(4.dp),
        border = BorderStroke(1.dp, Green),
        shadowElevation = 0.dp,
    ) {
        Row(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.CheckCircle, contentDescription = null, tint = Green, modifier = Modifier.size(18.dp))
            Column {
                Text("TD MINER", style = mono(9, FontWeight.Bold), color = Green)
                Text(text, style = swiss(13, FontWeight.Bold), color = Paper)
            }
        }
    }
}

@Composable
private fun LogoutDialog(onCancel: () -> Unit, onConfirm: () -> Unit) {
    Dialog(onDismissRequest = onCancel) {
        Column(
            Modifier.fillMaxWidth().background(Panel).border(1.dp, Green).padding(22.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("ACCOUNT / SESSION", style = mono(10, FontWeight.Bold), color = Green)
            Text("LOG OUT?", style = swiss(30, FontWeight.Black), color = Paper)
            Text(
                "This clears saved Twitch cookies from private app storage. You will need to login again.",
                style = swiss(14),
                color = Muted,
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = onCancel,
                    shape = RoundedCornerShape(2.dp),
                    border = BorderStroke(1.dp, Rule),
                    modifier = Modifier.weight(1f),
                ) {
                    Text("CANCEL", style = mono(11, FontWeight.Bold), color = Paper)
                }
            OutlinedButton(
                onClick = onConfirm,
                shape = RoundedCornerShape(2.dp),
                border = BorderStroke(1.dp, Orange),
                modifier = Modifier.weight(1f),
            ) {
                Text("LOG OUT", style = mono(11, FontWeight.Bold), color = Orange)
            }
            }
        }
    }
}

@Composable
private fun PrimaryButton(text: String, color: Color, onClick: () -> Unit, enabled: Boolean = true) {
    Button(
        onClick = onClick,
        enabled = enabled,
        colors = ButtonDefaults.buttonColors(containerColor = color),
        shape = RoundedCornerShape(2.dp),
        modifier = Modifier.fillMaxWidth().height(58.dp),
    ) {
        Text(text, style = mono(16, FontWeight.Bold), color = Ink)
    }
}

@Composable
private fun Metric(value: String, label: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(value, style = mono(18, FontWeight.Black), color = Green)
        Text(label, style = mono(9, FontWeight.Bold), color = Muted)
    }
}

@Composable
private fun ProgressLine(label: String, value: String, progress: Float) {
    val clamped = progress.coerceIn(0f, 1f)
    Text("$label  $value", style = swiss(14, FontWeight.Bold))
    Box(Modifier.fillMaxWidth().height(4.dp).background(Rule)) {
        Box(Modifier.fillMaxWidth(clamped).height(4.dp).background(Green))
    }
}

@Composable
private fun Chip(text: String, color: Color) {
    Text(text, color = color, style = swiss(12, FontWeight.Bold), modifier = Modifier.border(1.dp, color).padding(horizontal = 8.dp, vertical = 4.dp))
}

@Composable
private fun Reward(text: String, imageUrl: String? = null) {
    Box(Modifier.size(54.dp).background(Panel).border(1.dp, Rule), contentAlignment = Alignment.Center) {
        NetworkImage(imageUrl, Modifier.fillMaxSize())
        if (imageUrl != null) Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.18f)))
        Text(text, style = swiss(10, FontWeight.Bold), color = if (imageUrl == null) Ink else Paper, textAlign = TextAlign.Center, modifier = Modifier.padding(4.dp))
    }
}

@Composable
private fun NetworkImage(url: String?, modifier: Modifier = Modifier, alignment: Alignment = Alignment.Center) {
    var bitmap by remember(url) { mutableStateOf<android.graphics.Bitmap?>(null) }
    LaunchedEffect(url) {
        bitmap = if (url.isNullOrBlank()) {
            null
        } else {
            withContext(Dispatchers.IO) {
                runCatching { URL(url).openStream().use(BitmapFactory::decodeStream) }.getOrNull()
            }
        }
    }
    bitmap?.let {
        Image(it.asImageBitmap(), contentDescription = null, contentScale = ContentScale.Crop, alignment = alignment, modifier = modifier)
    }
}

private fun matchLoadedCategories(categories: List<TwitchCategory>, query: String): List<TwitchCategory> {
    val trimmed = query.trim()
    if (trimmed.length < 2) return emptyList()
    return categories.filter { it.name.contains(trimmed, ignoreCase = true) }.take(8)
}

private fun TwitchCategory.boxArtUrl() = "https://static-cdn.jtvnw.net/ttv-boxart/$id-285x380.jpg"

private fun saveSettings(
    settingsStore: MinerSettingsStore,
    priority: List<String>,
    excluded: List<String>,
    farmUnlinked: Boolean,
    badgeEmote: Boolean,
    notifications: Boolean,
    wakeLock: Boolean,
) {
    val cleanPriority = normalizeSettingsList(priority)
    val cleanExcluded = normalizeSettingsList(excluded).filterNot { it in cleanPriority.toSet() }
    settingsStore.save(
        MinerSettings(
            priorityGames = cleanPriority,
            excludedGames = cleanExcluded,
            farmUnlinkedDrops = farmUnlinked,
            badgeEmoteSupport = badgeEmote,
            notificationsEnabled = notifications,
            wakeLockEnabled = wakeLock,
        ),
    )
}

private fun swiss(size: Int, weight: FontWeight = FontWeight.Normal) =
    androidx.compose.ui.text.TextStyle(fontSize = size.sp, fontWeight = weight, fontFamily = DisplayFont, color = Paper)

private fun mono(size: Int, weight: FontWeight = FontWeight.Normal) =
    androidx.compose.ui.text.TextStyle(fontSize = size.sp, fontWeight = weight, fontFamily = FontFamily.Monospace, color = Paper)
