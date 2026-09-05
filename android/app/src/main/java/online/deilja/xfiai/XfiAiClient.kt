package online.deilja.xfiai

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class SessionExpiredException(message: String = "XFI AI admin session expired") : IllegalStateException(message)

class XfiAiClient(
    private val baseUrl: String,
    private val session: String? = null,
    private val openConnection: (String) -> HttpURLConnection = { URL(it).openConnection() as HttpURLConnection }
) {
    init {
        require(baseUrl.trim().startsWith("https://")) { "XFI AI endpoint must use HTTPS" }
    }

    private fun projectPath(project: String): String {
        require(project == "connect" || project == "webapp") { "Unsupported project" }
        return project
    }

    private fun connection(path: String, method: String): HttpURLConnection =
        openConnection(baseUrl.trimEnd('/') + path).apply {
            requestMethod = method
            connectTimeout = 10000
            readTimeout = 60000
            if (session != null) setRequestProperty("X-Admin-Session", session)
        }

    fun login(adminKey: String): String {
        require(adminKey.isNotBlank()) { "Admin key is required" }
        val connection = connection("/admin/session", "POST").apply {
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
        }
        connection.outputStream.use { it.write(JSONObject().put("key", adminKey).toString().toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        val cookie = connection.headerFields.entries
            .firstOrNull { it.key.equals("Set-Cookie", ignoreCase = true) }
            ?.value.orEmpty()
            .asSequence()
            .map { it.substringBefore(';') }
            .firstNotNullOfOrNull { value ->
                value.removePrefix("xfi_admin_session=").takeIf { it.isNotBlank() && it != value }
            }
        val text = readText(connection, code)
        if (code !in 200..299) throw IllegalStateException("Login failed ($code): ${errorMessage(text)}")
        return cookie ?: throw IllegalStateException("XFI AI did not return an admin session")
    }

    fun logout() {
        val connection = connection("/admin/session/logout", "POST")
        connection.responseCode
        connection.disconnect()
    }

    fun dashboard(): DashboardStatus {
        val connection = connection("/admin/dashboard", "GET")
        val code = connection.responseCode
        val text = readText(connection, code)
        checkResponse(code, text)
        val json = JSONObject(text)
        val summary = json.optJSONObject("summary") ?: JSONObject()
        val contract = json.optJSONObject("contract") ?: JSONObject()
        return DashboardStatus(summary.optInt("integrations_ready"), summary.optInt("integrations_total"), summary.optInt("providers_configured"), contract.optString("version", "unknown"))
    }

    fun projectStatus(project: String): ProjectStatus {
        val connection = connection("/admin/projects/${projectPath(project)}", "GET")
        val code = connection.responseCode
        val text = readText(connection, code)
        checkResponse(code, text)
        val json = JSONObject(text)
        return ProjectStatus(json.optString("id", project), json.optString("name", project), json.optBoolean("active", false), if (json.has("health") && !json.isNull("health")) json.optBoolean("health") else null, json.optString("status", "unknown").trim())
    }

    fun analyze(project: String, request: String): AiResult {
        require(request.isNotBlank()) { "Request is required" }
        val connection = connection("/admin/projects/${projectPath(project)}/analyze", "POST").jsonRequest()
        return parseResult(connection, JSONObject().put("request", request))
    }

    fun generate(project: String, request: String, answers: List<Answer> = emptyList()): AiResult {
        require(request.isNotBlank()) { "Request is required" }
        val connection = connection("/admin/projects/${projectPath(project)}/generate", "POST").jsonRequest()
        return parseResult(connection, JSONObject().put("request", request).put("answers", answers.toJson()))
    }

    fun apply(project: String, edits: List<EditPreview>, restart: Boolean = true): AiResult {
        require(edits.isNotEmpty()) { "No patch to apply" }
        val connection = connection("/admin/projects/${projectPath(project)}/apply", "POST").jsonRequest()
        val payload = JSONArray().apply {
            edits.forEach { edit -> put(JSONObject().put("path", edit.path).put("content", edit.content).put("reason", edit.reason).put("expected_sha256", edit.expectedSha256)) }
        }
        return parseResult(connection, JSONObject().put("confirm", true).put("restart", restart).put("edits", payload))
    }

    fun audit(project: String): List<String> {
        val connection = connection("/admin/projects/${projectPath(project)}/audit", "GET")
        val code = connection.responseCode
        val text = readText(connection, code)
        checkResponse(code, text)
        val array = JSONObject(text).optJSONArray("audit") ?: JSONArray()
        return buildList { for (i in 0 until array.length()) add(array.optJSONObject(i)?.toString() ?: array.optString(i)) }
    }

    private fun HttpURLConnection.jsonRequest(): HttpURLConnection = apply {
        doOutput = true
        setRequestProperty("Content-Type", "application/json")
    }

    private fun parseResult(connection: HttpURLConnection, body: JSONObject): AiResult {
        connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        val text = readText(connection, code)
        checkResponse(code, text)
        val json = runCatching { JSONObject(text) }.getOrElse { return AiResult(false, "Invalid XFI AI response", raw = text) }
        val edits = json.optJSONArray("edits").toEdits()
        val architecture = json.optJSONObject("architecture")
        return AiResult(
            ok = json.optBoolean("ok", json.optBoolean("ready", true)),
            summary = json.optString("summary", json.optString("message", "Request processed")),
            stage = json.optString("stage", ""),
            questions = json.optJSONArray("questions").toStringList(),
            files = json.optJSONArray("files").toStringList().ifEmpty { edits.map { it.path } },
            edits = edits,
            tests = json.optJSONArray("tests").toStringList(),
            architectureNodes = architecture?.optInt("node_count"),
            architectureEdges = architecture?.optInt("edge_count"),
            raw = text
        )
    }

    private fun checkResponse(code: Int, text: String) {
        if (code == 401) throw SessionExpiredException()
        if (code !in 200..299) throw IllegalStateException(errorMessage(text))
    }

    private fun readText(connection: HttpURLConnection, code: Int): String {
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        return stream?.bufferedReader()?.use { it.readText() }.orEmpty()
    }

    private fun errorMessage(text: String): String = runCatching { JSONObject(text).optString("detail", text) }.getOrDefault(text).ifBlank { "XFI AI request failed" }

    private fun JSONArray?.toStringList(): List<String> = if (this == null) emptyList() else buildList { for (i in 0 until length()) add(optString(i)) }

    private fun JSONArray?.toEdits(): List<EditPreview> = if (this == null) emptyList() else buildList {
        for (i in 0 until length()) {
            val item = optJSONObject(i) ?: continue
            add(EditPreview(item.optString("path"), item.optString("reason"), item.optString("content"), item.optString("expected_sha256")))
        }
    }

    private fun List<Answer>.toJson() = JSONArray().apply { forEach { put(JSONObject().put("question", it.question).put("answer", it.answer)) } }
}