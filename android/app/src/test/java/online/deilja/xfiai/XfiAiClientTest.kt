package online.deilja.xfiai

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
}
