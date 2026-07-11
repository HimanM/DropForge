package io.github.himanm.tdminer

import android.app.NotificationManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.widget.RemoteViews

const val ACTION_START = "io.github.himanm.tdminer.START"
const val ACTION_STOP = "io.github.himanm.tdminer.STOP"

class MinerWidgetProvider : AppWidgetProvider() {
    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        when (intent.action) {
            ACTION_START -> {
                context.startForegroundService(Intent(context, MinerForegroundService::class.java))
                updateAll(context, true)
            }
            ACTION_STOP -> {
                context.startService(
                    Intent(context, MinerForegroundService::class.java).setAction(ACTION_STOP),
                )
                updateAll(context, false)
            }
        }
    }

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        ids.forEach { manager.updateAppWidget(it, views(context, MinerSession.idle())) }
    }

    companion object {
        fun updateAll(context: Context, running: Boolean) {
            updateAll(context, MinerSession.idle().copy(running = running))
        }

        fun updateAll(context: Context, session: MinerSession) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, MinerWidgetProvider::class.java))
            ids.forEach { manager.updateAppWidget(it, views(context, session)) }
        }

        private fun views(context: Context, session: MinerSession): RemoteViews {
            val views = RemoteViews(context.packageName, R.layout.miner_widget)
            views.setTextViewText(R.id.widget_status, if (session.running) "RUNNING" else "IDLE")
            views.setTextViewText(
                R.id.widget_detail,
                if (session.running) "${session.channel} / ${session.drop} ${(session.dropProgress * 100).toInt()}%" else "Ready to start",
            )
            views.setProgressBar(R.id.widget_progress, 100, if (session.running) (session.dropProgress * 100).toInt() else 0, false)
            views.setTextViewText(R.id.widget_button, if (session.running) "STOP" else "START")
            views.setOnClickPendingIntent(
                R.id.widget_button,
                PendingIntent.getBroadcast(
                    context,
                    if (session.running) 4 else 3,
                    Intent(context, MinerWidgetProvider::class.java)
                        .setAction(if (session.running) ACTION_STOP else ACTION_START),
                    PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
                ),
            )
            return views
        }
    }
}
