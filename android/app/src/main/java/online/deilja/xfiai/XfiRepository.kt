package online.deilja.xfiai

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class XfiRepository(context: Context) {
    private val store = XfiSecureStore(context.applicationContext)

    suspend fun login(endpoint: String, adminKey: String): String = withContext(Dispatchers.IO) {
        val session = XfiAiClient(endpoint).login(adminKey)
        store.saveSession(session)
        session
    }

    fun session(): String? = store.loadSession()

    suspend fun logout(endpoint: String) = withContext(Dispatchers.IO) {
        store.loadSession()?.let { runCatching { XfiAiClient(endpoint, it).logout() } }
        store.clearSession()
    }

    fun client(endpoint: String): XfiAiClient? = store.loadSession()?.let { XfiAiClient(endpoint, it) }
}
