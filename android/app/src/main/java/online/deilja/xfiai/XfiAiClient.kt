package online.deilja.xfiai

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

interface XfiConnection {
    var method: String
    var connectTimeout: Int
    var readTimeout: Int
    var doOutput: Boolean
    val responseCode: Int
    val requestProperties: MutableMap<String, String>
    fun setRequestProperty(key: String, value: String)
    fun getHeaderField(name: String): String?
    fun write(body: ByteArray)
    fun readBody(): String
    fun close()
}

private class HttpUrlConnectionAdapter(private val connection: HttpURLConnection) : XfiConnection {
    override var method: String
        get() = connection.requestMethod
        set(value) { connection.requestMethod = value }
    override var connectTimeout: Int
        get() = connection.connectTimeout
        set(value) { connection.connectTimeout = value }
    override var readTimeout: Int
        get() = connection.readTimeout
        set(value) { connection.readTimeout = value }
    override var doOutput: Boolean
        get() = connection.doOutput
        set(value) { connection.doOutput = value }
    override val responseCode: Int get() = connection.responseCode
    override val requestProperties = mutableMapOf<String, String>()
    override fun setRequestProperty(key: String, value: String) { connection.setRequestProperty(key, value); requestProperties[key] = value }
    override fun getHeaderField(name: String): String? = connection.getHeaderField(name)
    override fun write(body: ByteArray) { connection.outputStream.use { it.write(body) } }
    override fun readBody(): String {
        val stream = if (responseCode in 200..299) connection.inputStream else connection.errorStream
        return stream?.bufferedReader()?.use { it.readText() }.orEmpty()
    }
    override fun close() { connection.disconnect() }
}

class SessionExpiredException(message: String = "XFI AI admin session expired") : IllegalStateException(message)

class XfiAiClient(
    private val baseUrl: String,
    private val session: String? = null,
    private val openConnection: (String) -> XfiConnection = { HttpUrlConnectionAdapter(URL(it).openConnection() as HttpURLConnection) }
) {
    init { require(baseUrl.trim().startsWith("https://")) { "XFI AI endpoint must use HTTPS" } }

    private fun projectPath(project: String): String {
        require(project == "connect" || project == "webapp") { "Unsupported project" }
        return project
    }

    private fun connection(path: String, method: String): XfiConnection = openConnection(baseUrl.trimEnd('/') + path).apply {
        this.method = method
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
        connection.write(JSONObject().put("key", adminKey).toString().toByteArray(Charsets.UTF_8))
        val code = connection.responseCode
        val cookieHeader = connection.getHeaderField("Set-Cookie").orEmpty()
        val cookie = cookieHeader.split(',').asSequence().map { it.substringBefore(';').trim() }.firstNotNullOfOrNull { value ->
            value.removePrefix("xfi_admin_session=").takeIf { value.startsWith("xfi_admin_session=") && it.isNotBlank() }
        }
        val text = connection.readBody()
        if (code !in 200..299) throw IllegalStateException("Login failed ($code): ${errorMessage(text)}")
        return cookie ?: throw IllegalStateException("XFI AI did not return an admin session")
    }

    fun logout() { connection("/admin/session/logout", "POST").apply { responseCode; close() } }

    fun dashboard(): DashboardStatus {
        val connection = connection("/admin/dashboard", "GET")
        val code = connection.responseCode; val text = connection.readBody(); checkResponse(code, text)
        val json = JSONObject(text); val summary = json.optJSONObject("summary") ?: JSONObject(); val contract = json.optJSONObject("contract") ?: JSONObject()
        return DashboardStatus(summary.optInt("integrations_ready"), summary.optInt("integrations_total"), summary.optInt("providers_configured"), contract.optString("version", "unknown"))
    }

    fun projectStatus(project: String): ProjectStatus {
        val connection = connection("/admin/projects/${projectPath(project)}", "GET")
        val code = connection.responseCode; val text = connection.readBody(); checkResponse(code, text)
        val json = JSONObject(text)
        return ProjectStatus(json.optString("id", project), json.optString("name", project), json.optBoolean("active", false), if (json.has("health") && !json.isNull("health")) json.optBoolean("health") else null, json.optString("status", "unknown").trim())
    }

    fun analyze(project: String, request: String): AiResult {
        require(request.isNotBlank()) { "Request is required" }
        return parseResult(connection("/admin/projects/${projectPath(project)}/analyze", "POST").jsonRequest(), JSONObject().put("request", request))
    }

    fun generate(project: String, request: String, answers: List<Answer> = emptyList()): AiResult {
        require(request.isNotBlank()) { "Request is required" }
        return parseResult(connection("/admin/projects/${projectPath(project)}/generate", "POST").jsonRequest(), JSONObject().put("request", request).put("answers", answers.toJson()))
    }

    fun apply(project: String, edits: List<EditPreview>, restart: Boolean = true): AiResult {
        require(edits.isNotEmpty()) { "No patch to apply" }
        val payload = JSONArray().apply { edits.forEach { put(JSONObject().put("path", it.path).put("content", it.content).put("reason", it.reason).put("expected_sha256", it.expectedSha256)) } }
        return parseResult(connection("/admin/projects/${projectPath(project)}/apply", "POST").jsonRequest(), JSONObject().put("confirm", true).put("restart", restart).put("edits", payload))
    }

    fun audit(project: String): List<String> {
        val connection = connection("/admin/projects/${projectPath(project)}/audit", "GET")
        val code = connection.responseCode; val text = connection.readBody(); checkResponse(code, text)
        val array = JSONObject(text).optJSONArray("audit") ?: JSONArray()
        return buildList { for (i in 0 until array.length()) add(array.optJSONObject(i)?.toString() ?: array.optString(i)) }
    }

    private fun XfiConnection.jsonRequest(): XfiConnection = apply { doOutput = true; setRequestProperty("Content-Type", "application/json") }

    private fun parseResult(connection: XfiConnection, body: JSONObject): AiResult {
        connection.write(body.toString().toByteArray(Charsets.UTF_8))
        val code = connection.responseCode; val text = connection.readBody(); checkResponse(code, text)
        val json = runCatching { JSONObject(text) }.getOrElse { return AiResult(false, "Invalid XFI AI response", raw = text) }
        val edits = json.optJSONArray("edits").toEdits(); val architecture = json.optJSONObject("architecture")
        return AiResult(json.optBoolean("ok", json.optBoolean("ready", true)), json.optString("summary", json.optString("message", "Request processed")), json.optString("stage", ""), json.optJSONArray("questions").toStringList(), json.optJSONArray("files").toStringList().ifEmpty { edits.map { it.path } }, edits, json.optJSONArray("tests").toStringList(), architecture?.optInt("node_count"), architecture?.optInt("edge_count"), text)
    }

    private fun checkResponse(code: Int, text: String) { if (code == 401) throw SessionExpiredException(); if (code !in 200..299) throw IllegalStateException(errorMessage(text)) }
    private fun errorMessage(text: String): String = runCatching { JSONObject(text).optString("detail", text) }.getOrDefault(text).ifBlank { "XFI AI request failed" }
    private fun JSONArray?.toStringList(): List<String> = if (this == null) emptyList() else buildList { for (i in 0 until length()) add(optString(i)) }
    private fun JSONArray?.toEdits(): List<EditPreview> = if (this == null) emptyList() else buildList { for (i in 0 until length()) { val item = optJSONObject(i) ?: continue; add(EditPreview(item.optString("path"), item.optString("reason"), item.optString("content"), item.optString("expected_sha256"))) } }
    private fun List<Answer>.toJson() = JSONArray().apply { forEach { put(JSONObject().put("question", it.question).put("answer", it.answer)) } }
}
