package online.deilja.xfiai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { XfiAiApp(XfiRepository(this)) }
    }
}

@Composable
private fun XfiAiApp(repository: XfiRepository) {
    var endpoint by remember { mutableStateOf("") }
    var adminKey by remember { mutableStateOf("") }
    var session by remember { mutableStateOf<String?>(null) }
    var project by remember { mutableStateOf("connect") }
    var request by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("Not connected") }
    var result by remember { mutableStateOf<AiResult?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun client(): XfiAiClient? = session?.takeIf { endpoint.isNotBlank() }?.let { XfiAiClient(endpoint, it) }

    MaterialTheme {
        Scaffold { padding ->
            Surface(Modifier.fillMaxSize().padding(padding)) {
                LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    item { Text("XFI AI", style = MaterialTheme.typography.headlineMedium) }
                    item { Text(message) }
                    item { OutlinedTextField(endpoint, { endpoint = it }, Modifier.fillMaxWidth(), label = { Text("XFI AI HTTPS URL") }) }
                    item { OutlinedTextField(adminKey, { adminKey = it }, Modifier.fillMaxWidth(), label = { Text("Admin key") }) }
                    item {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                onClick = {
                                    if (endpoint.isBlank() || adminKey.isBlank()) {
                                        message = "Enter HTTPS URL and admin key"
                                    } else {
                                        busy = true
                                        scope.launch {
                                            runCatching { withContext(Dispatchers.IO) { repository.login(endpoint, adminKey) } }
                                                .onSuccess { value -> session = value; adminKey = ""; message = "Connected" }
                                                .onFailure { message = it.message ?: "Login failed" }
                                            busy = false
                                        }
                                    }
                                },
                                enabled = !busy && session == null,
                                modifier = Modifier.weight(1f)
                            ) { Text(if (busy) "Connecting…" else "Connect") }
                            OutlinedButton(
                                onClick = { session = null; result = null; message = "Disconnected" },
                                enabled = session != null,
                                modifier = Modifier.weight(1f)
                            ) { Text("Disconnect") }
                        }
                    }
                    item {
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                Text("AI Code Agent", style = MaterialTheme.typography.titleLarge)
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Button(onClick = { project = "connect" }, enabled = session != null) { Text("XFI_CONNECT") }
                                    OutlinedButton(onClick = { project = "webapp" }, enabled = session != null) { Text("WebApp") }
                                }
                                OutlinedTextField(
                                    request,
                                    { request = it.take(8000) },
                                    Modifier.fillMaxWidth(),
                                    minLines = 4,
                                    label = { Text("Describe the change") }
                                )
                                Button(
                                    onClick = {
                                        val c = client()
                                        if (c == null) {
                                            message = "Connect first"
                                        } else {
                                            busy = true
                                            scope.launch {
                                                runCatching { withContext(Dispatchers.IO) { c.analyze(project, request) } }
                                                    .onSuccess { result = it; message = "Analysis completed" }
                                                    .onFailure { message = it.message ?: "Analysis failed" }
                                                busy = false
                                            }
                                        }
                                    },
                                    enabled = session != null && !busy && request.isNotBlank(),
                                    modifier = Modifier.fillMaxWidth()
                                ) { Text("Analyze architecture") }
                            }
                        }
                    }
                    result?.let { r ->
                        item {
                            Card(Modifier.fillMaxWidth()) {
                                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(if (r.ok) "Agent result" else "Request failed", style = MaterialTheme.typography.titleLarge)
                                    Text(r.summary)
                                    if (r.questions.isNotEmpty()) Text("Clarification required: ${r.questions.size} question(s)")
                                    if (r.edits.isNotEmpty()) {
                                        Text("Patch: ${r.edits.size} edit(s)")
                                        Button(
                                            onClick = {
                                                val c = client()
                                                if (c == null) message = "Connect first" else {
                                                    busy = true
                                                    scope.launch {
                                                        runCatching { withContext(Dispatchers.IO) { c.apply(project, r.edits, restart = true) } }
                                                            .onSuccess { result = it; message = "Patch applied and validated" }
                                                            .onFailure { message = it.message ?: "Apply failed" }
                                                        busy = false
                                                    }
                                                }
                                            },
                                            enabled = session != null && !busy
                                        ) { Text("Apply approved patch") }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
