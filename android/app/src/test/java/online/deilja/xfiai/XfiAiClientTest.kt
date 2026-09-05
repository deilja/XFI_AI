package online.deilja.xfiai

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

private class FakeConnection(
    override val responseCode: Int,
    private val responseBody: String,
    private val headers: Map<String, String> = emptyMap()
) : XfiConnection {
    override var method: String = "GET"
    override var connectTimeout: Int = 0
    override var readTimeout: Int = 0
    override var doOutput: Boolean = false
    override val requestProperties = linkedMapOf<String, String>()
    val requestBody = StringBuilder()

    override fun setRequestProperty(key: String, value: String) { requestProperties[key] = value }
    override fun getHeaderField(name: String): String? = headers.entries.firstOrNull { it.key.equals(name, true) }?.value
    override fun write(body: ByteArray) { requestBody.append(body.toString(Charsets.UTF_8)) }
    override fun readBody(): String = responseBody
    override fun close() = Unit
}

class XfiAiClientTest {
    @Test
    fun endpointMustUseHttps() {
        org.junit.Assert.assertThrows(IllegalArgumentException::class.java) { XfiAiClient("http://127.0.0.1:8080") }
    }

    @Test
    fun unsupportedProjectIsRejected() {
        val client = XfiAiClient("https://example.invalid")
        org.junit.Assert.assertThrows(IllegalArgumentException::class.java) { client.projectStatus("unknown") }
    }

    @Test
    fun loginDashboardProjectAnalyzeGenerateApplyAuditContract() {
        val connections = mutableListOf<FakeConnection>()
        var loginCalls = 0
        val factory: (String) -> XfiConnection = { target ->
            val path = target.substringAfter("https://example.invalid")
            val response = when (path) {
                "/admin/session" -> { loginCalls++; FakeConnection(200, "{\"ok\":true}", mapOf("Set-Cookie" to "xfi_admin_session=session-123; Path=/; HttpOnly")) }
                "/admin/dashboard" -> FakeConnection(200, "{\"summary\":{\"integrations_ready\":2,\"integrations_total\":2,\"providers_configured\":3},\"contract\":{\"version\":\"v1\"}}")
                "/admin/projects/connect" -> FakeConnection(200, "{\"id\":\"connect\",\"name\":\"XFI_CONNECT\",\"active\":true,\"status\":\"active\",\"health\":true}")
                "/admin/projects/connect/analyze" -> FakeConnection(200, "{\"ready\":true,\"questions\":[],\"summary\":\"analysis\",\"files\":[\"app.py\"],\"architecture\":{\"node_count\":4,\"edge_count\":3}}")
                "/admin/projects/connect/generate" -> FakeConnection(200, "{\"summary\":\"patch\",\"edits\":[{\"path\":\"app.py\",\"reason\":\"request\",\"content\":\"print(1)\",\"expected_sha256\":\"abc\"}],\"tests\":[\"python -m py_compile app.py\"]}")
                "/admin/projects/connect/apply" -> FakeConnection(200, "{\"ok\":true,\"project\":\"connect\",\"changed\":[\"app.py\"],\"backup\":\"/backup/id\",\"validation\":{\"ok\":true}}")
                "/admin/projects/connect/audit" -> FakeConnection(200, "{\"project\":\"connect\",\"audit\":[{\"action\":\"анализ\"},{\"action\":\"применение\"}]}")
                else -> FakeConnection(404, "{\"detail\":\"Unexpected endpoint: $path\"}")
            }
            connections += response
            response
        }

        val session = XfiAiClient("https://example.invalid", openConnection = factory).login("admin-key")
        assertEquals("session-123", session)
        assertEquals(1, loginCalls)
        val client = XfiAiClient("https://example.invalid", session, factory)
        val dashboard = client.dashboard()
        assertEquals(2, dashboard.integrationsReady)
        assertEquals(2, dashboard.integrationsTotal)
        assertEquals(3, dashboard.providersConfigured)
        assertEquals("v1", dashboard.protocolVersion)
        val project = client.projectStatus("connect")
        assertTrue(project.online)
        assertEquals(true, project.health)
        assertEquals("active", project.detail)
        val analysis = client.analyze("connect", "change UI")
        assertTrue(analysis.ok)
        assertEquals(listOf("app.py"), analysis.files)
        assertEquals(4, analysis.architectureNodes)
        assertEquals(3, analysis.architectureEdges)
        val generated = client.generate("connect", "change UI", listOf(Answer("style?", "modern")))
        assertEquals("app.py", generated.edits.single().path)
        assertEquals("abc", generated.edits.single().expectedSha256)
        assertEquals("print(1)", generated.edits.single().content)
        assertEquals(1, generated.tests.size)
        val applied = client.apply("connect", generated.edits, restart = false)
        assertTrue(applied.ok)
        assertEquals("app.py", applied.files.single())
        val audit = client.audit("connect")
        assertEquals(2, audit.size)
        assertTrue(audit[0].contains("анализ"))
        val bodies = connections.map { it.requestBody.toString() }
        assertTrue(bodies.any { JSONObject(it).optString("key") == "admin-key" })
        assertTrue(bodies.any { JSONObject(it).optString("request") == "change UI" })
        assertTrue(bodies.any { val json = JSONObject(it); json.optBoolean("confirm") && !json.optBoolean("restart") && json.optJSONArray("edits")?.length() == 1 })
        val generateBody = bodies.first { it.contains("\"answers\"") }
        assertEquals("modern", JSONObject(generateBody).getJSONArray("answers").getJSONObject(0).getString("answer"))
    }

    @Test
    fun unauthorizedResponseBecomesSessionExpiredException() {
        val factory: (String) -> XfiConnection = { FakeConnection(401, "{\"detail\":\"expired\"}") }
        val client = XfiAiClient("https://example.invalid", "expired-session", factory)
        org.junit.Assert.assertThrows(SessionExpiredException::class.java) { client.dashboard() }
    }

    @Test
    fun missingLoginCookieIsRejected() {
        val factory: (String) -> XfiConnection = { FakeConnection(200, "{\"ok\":true}") }
        org.junit.Assert.assertThrows(IllegalStateException::class.java) { XfiAiClient("https://example.invalid", openConnection = factory).login("admin-key") }
    }

    @Test
    fun invalidJsonResponseIsReportedWithoutCrashing() {
        val factory: (String) -> XfiConnection = { FakeConnection(200, "not-json") }
        val result = XfiAiClient("https://example.invalid", "session", factory).analyze("connect", "test")
        assertFalse(result.ok)
        assertEquals("Invalid XFI AI response", result.summary)
        assertEquals("not-json", result.raw)
    }
}
