package io.github.himanm.tdminer

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat

class MinerForegroundService : Service() {
    private var wakeLock: PowerManager.WakeLock? = null
    private var worker: Thread? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSession()
            return START_NOT_STICKY
        }
        if (worker?.isAlive == true) return START_STICKY
        if (SharedPrefsMinerSettingsStore(this).load().wakeLockEnabled) acquireWakeLock()
        val core = MinerCore(SharedPrefsCookieStore(this))
        val session = core.start()
        startForeground(NOTIFICATION_ID, notification("Validating Twitch session", session, indeterminate = true))
        MinerWidgetProvider.updateAll(this, session)
        worker?.interrupt()
        worker = Thread {
            var firstRun = true
            while (!Thread.currentThread().isInterrupted) {
                if (firstRun) {
                    firstRun = false
                    try {
                        Thread.sleep(60_000)
                    } catch (_: InterruptedException) {
                        break
                    }
                }
                val refreshed = refresh(core, validate = false)
                val title = if (refreshed.authReady) "TD Miner running" else "TD Miner login needed"
                getSystemService(NotificationManager::class.java)
                    .notify(NOTIFICATION_ID, notification(title, refreshed, indeterminate = false))
                MinerWidgetProvider.updateAll(this, refreshed)
                try {
                    Thread.sleep(60_000)
                } catch (_: InterruptedException) {
                    break
                }
            }
        }.apply { start() }
        return START_STICKY
    }

    override fun onDestroy() {
        worker?.interrupt()
        worker = null
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
        MinerWidgetProvider.updateAll(this, false)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val power = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "tdminer:session").apply {
            acquire(6 * 60 * 60 * 1000L)
        }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < 26) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "TD Miner session",
            NotificationManager.IMPORTANCE_LOW,
        )
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun notification(title: String, session: MinerSession, indeterminate: Boolean) =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(title)
            .setContentText(notificationText(session))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setProgress(100, (session.dropProgress * 100).toInt(), indeterminate)
            .addAction(0, "STOP", stopIntent())
            .build()

    private fun notificationText(session: MinerSession): String =
        if (session.authReady) {
            "${session.channel} / ${session.drop} ${(session.dropProgress * 100).toInt()}%"
        } else {
            "Saved Twitch cookies are missing or expired"
        }

    private fun refresh(core: MinerCore, validate: Boolean): MinerSession {
        val validated = if (validate) {
            try {
                core.validateAuth()
            } catch (_: Exception) {
                core.session.copy(loggedIn = false, authReady = false)
            }
        } else {
            core.session
        }
        return if (validated.authReady) {
            try {
                val settings = SharedPrefsMinerSettingsStore(this).load()
                core.refreshDrops(settings)
                core.watchOnce()
            } catch (_: Exception) {
                validated
            }
        } else {
            validated
        }
    }

    private fun stopIntent(): PendingIntent {
        val intent = Intent(this, MinerForegroundService::class.java).setAction(ACTION_STOP)
        return PendingIntent.getService(
            this,
            2,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
    }

    private fun stopSession() {
        worker?.interrupt()
        worker = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        getSystemService(NotificationManager::class.java).cancel(NOTIFICATION_ID)
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
        MinerWidgetProvider.updateAll(this, false)
        stopSelf()
    }

    companion object {
        const val CHANNEL_ID = "tdminer-session"
        const val NOTIFICATION_ID = 1
    }
}
