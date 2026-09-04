package online.deilja.xfiai

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class XfiAiClient(private val baseUrl: String, private val token: String) {
    fun customize(project: String, request: String, confirm: Boolean = false): AiResult {
        val url = URL(baseUrl.trimEnd('/') + "/admin/projects/$project/customize")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 10000
            readTimeout = 60000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
            if (token.isNotBlank()) setRequestProperty("Authorization", "Bearer $token")
        }
        val body = JSONObject().apply {
            put("request", request)
            put("confirm", confirm)
            put("restart", true)
        }.toString()
        connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val json = runCatching { JSONObject(text) }.getOrElse {
            return AiResult(false, "Invalid XFI AI response", raw = text)
        }
        val questions = json.optJSONArray("questions").toStringList()
        val files = json.optJSONArray("files").toStringList()
        return AiResult(
            ok = connection.responseCode in 200..299 && json.optBoolean("ok", true),
            summary = json.optString("summary", json.optString("message", "Request processed")),
            questions = questions,
            files = files,
            raw = text
        )
    }

    private fun JSONArray?.toStringList(): List<String> = if (this == null) emptyList() else buildList {
        for (i in 0 until length()) add(optString(i))
    }
}
