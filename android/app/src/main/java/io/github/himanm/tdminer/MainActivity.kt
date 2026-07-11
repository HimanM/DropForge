package io.github.himanm.tdminer

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.net.Uri
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
        }
        val core = MinerCore(SharedPrefsCookieStore(this))
        intent.getStringExtra(EXTRA_COOKIES)?.takeIf { it.isNotBlank() }?.let(core::saveCookies)
        setContent {
            TDMinerApp(
                core = core,
                settingsStore = SharedPrefsMinerSettingsStore(this),
                onStart = {
                    startForegroundService(Intent(this, MinerForegroundService::class.java))
                    MinerWidgetProvider.updateAll(this, true)
                },
                onStop = {
                    startService(
                        Intent(this, MinerForegroundService::class.java).setAction(ACTION_STOP),
                    )
                    MinerWidgetProvider.updateAll(this, false)
                },
                onOpenUrl = { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(it))) },
            )
        }
    }

    companion object {
        const val EXTRA_COOKIES = "io.github.himanm.tdminer.COOKIES"
    }
}
