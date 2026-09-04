package online.deilja.xfiai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class XfiAiClientTest {
    @Test
    fun endpointMustUseHttps() {
        assertThrows(IllegalArgumentException::class.java) {
            XfiAiClient("http://127.0.0.1:8080")
        }
    }

    @Test
    fun unsupportedProjectIsRejected() {
        val client = XfiAiClient("https://example.invalid")
        assertThrows(IllegalArgumentException::class.java) {
            client.projectStatus("unknown")
        }
    }

    @Test
    fun supportedProjectsAreAcceptedByPathContract() {
        val connect = XfiAiClient("https://example.invalid")
        val webapp = XfiAiClient("https://example.invalid")
        assertEquals("connect", connect.javaClass.getDeclaredMethod("projectPath", String::class.java).apply { isAccessible = true }.invoke(connect, "connect"))
        assertEquals("webapp", webapp.javaClass.getDeclaredMethod("projectPath", String::class.java).apply { isAccessible = true }.invoke(webapp, "webapp"))
    }

    @Test
    fun sessionExpiredExceptionHasStableType() {
        val error = SessionExpiredException()
        assertEquals("XFI AI admin session expired", error.message)
    }
}
