package io.github.himanm.tdminer

import android.content.Context

interface CookieStore {
    fun loadCookies(): String?
    fun saveCookies(cookies: String)
    fun hasCookies(): Boolean = !loadCookies().isNullOrBlank()
    fun loadCookieJar(): TwitchCookieJar? = loadCookies()?.let(TwitchCookieJar::parse)
    fun logout()
}

class SharedPrefsCookieStore(context: Context) : CookieStore {
    private val prefs = context.getSharedPreferences("tdminer_auth", Context.MODE_PRIVATE)

    override fun loadCookies(): String? = prefs.getString(KEY_COOKIES, null)

    override fun saveCookies(cookies: String) {
        prefs.edit().putString(KEY_COOKIES, cookies).apply()
    }

    override fun logout() {
        prefs.edit().remove(KEY_COOKIES).apply()
    }

    companion object {
        private const val KEY_COOKIES = "cookies"
    }
}

class MemoryCookieStore : CookieStore {
    private var cookies: String? = null

    override fun loadCookies(): String? = cookies

    override fun saveCookies(cookies: String) {
        this.cookies = cookies
    }

    override fun logout() {
        cookies = null
    }
}
