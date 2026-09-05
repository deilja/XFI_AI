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
import androidx.compose.material3.Divider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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

private enum class Screen(val title: String) { DASHBOARD("Dashboard"), AGENT("AI Agent"), PROJECTS("Projects"), AUDIT("Audit"), SETTINGS("Settings") }

@Composable
private fun XfiAiApp(repository: XfiRepository) {
    var endpoint by remember { mutableStateOf("") }
    var adminKey by remember { mutableStateOf("") }
    var session by remember { mutableStateOf<String?>(null) }
    var screen by remember { mutableStateOf(Screen.DASHBOARD) }
    var project by remember { mutableStateOf("connect") }
    var request by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("Loading…") }
    var busy by remember { mutableStateOf(false) }
    var dashboard by remember { mutableStateOf<DashboardStatus?>(null) }
    var projectStatus by remember { mutableStateOf<ProjectStatus?>(null) }
    var result by remember { mutableStateOf<AiResult?>(null) }
    var audit by remember { mutableStateOf<List<String>>(emptyList()) }
    val scope = rememberCoroutineScope()

    fun refresh() {
        val current = session ?: return
        scope.launch {
            busy = true
            runCatching { withContext(Dispatchers.IO) { val c = XfiAiClient(endpoint, current); Triple(c.dashboard(), c.projectStatus(project), c.audit(project)) } }
                .onSuccess { (d, p, a) -> dashboard = d; projectStatus = p; audit = a; message = "Connected" }
                .onFailure { if (it is SessionExpiredException) session = null; message = it.message ?: "Refresh failed" }
            busy = false
        }
    }

    LaunchedEffect(Unit) {
        endpoint = repository.endpoint()
        session = repository.session()
        if (session != null && endpoint.isNotBlank()) refresh() else message = "Not connected"
    }

    fun connect() {
        if (endpoint.isBlank() || adminKey.isBlank()) { message = "Enter HTTPS URL and admin key"; return }
        busy = true
        scope.launch {
            runCatching { withContext(Dispatchers.IO) { repository.login(endpoint, adminKey) } }
                .onSuccess { value -> session = value; adminKey = ""; message = "Connected"; refresh() }
                .onFailure { message = it.message ?: "Login failed" }
            busy = false
        }
    }

    fun disconnect() {
        scope.launch {
            withContext(Dispatchers.IO) { repository.logout(endpoint) }
            session = null; dashboard = null; projectStatus = null; result = null; audit = emptyList(); message = "Disconnected"
        }
    }

    MaterialTheme {
        Scaffold { padding ->
            Surface(Modifier.fillMaxSize().padding(padding)) {
                Column(Modifier.fillMaxSize()) {
                    Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                        Text("XFI AI", style = MaterialTheme.typography.headlineMedium)
                        Text(message)
                    }
                    Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                        Screen.entries.forEach { item -> TextButton(onClick = { screen = item }) { Text(item.title) } }
                    }
                    Divider()
                    LazyColumn(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        when (screen) {
                            Screen.DASHBOARD -> item { DashboardScreen(dashboard, projectStatus, project, busy, ::refresh) }
                            Screen.AGENT -> item {
                                AgentScreen(project, request, result, busy, session != null, { project = it; result = null }, { request = it.take(8000) },
                                    analyze = {
                                        val current = session ?: run { message = "Connect first"; return@AgentScreen }
                                        scope.launch { busy = true; runCatching { withContext(Dispatchers.IO) { XfiAiClient(endpoint, current).analyze(project, request) } }.onSuccess { result = it; message = "Analysis completed" }.onFailure { if (it is SessionExpiredException) session = null; message = it.message ?: "Analysis failed" }; busy = false }
                                    },
                                    generate = {
                                        val current = session ?: run { message = "Connect first"; return@AgentScreen }
                                        scope.launch { busy = true; runCatching { withContext(Dispatchers.IO) { XfiAiClient(endpoint, current).generate(project, request) } }.onSuccess { result = it; message = "Patch generated" }.onFailure { if (it is SessionExpiredException) session = null; message = it.message ?: "Generation failed" }; busy = false }
                                    },
                                    apply = { edits ->
                                        val current = session ?: run { message = "Connect first"; return@AgentScreen }
                                        scope.launch { busy = true; runCatching { withContext(Dispatchers.IO) { XfiAiClient(endpoint, current).apply(project, edits, restart = true) } }.onSuccess { result = it; message = "Patch applied and validated"; refresh() }.onFailure { if (it is SessionExpiredException) session = null; message = it.message ?: "Apply failed" }; busy = false }
                                    })
                            }
                            Screen.PROJECTS -> item { ProjectsScreen(project, projectStatus, session != null, busy) { project = it; refresh() } }
                            Screen.AUDIT -> item { AuditScreen(audit, session != null, busy, ::refresh) }
                            Screen.SETTINGS -> item { SettingsScreen(endpoint, adminKey, session != null, busy, { endpoint = it }, { adminKey = it }, ::connect, ::disconnect) }
                        }
                    }
                }
            }
        }
    }
}

@Composable private fun DashboardScreen(d: DashboardStatus?, p: ProjectStatus?, project: String, busy: Boolean, refresh: () -> Unit) {
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("System dashboard", style = MaterialTheme.typography.titleLarge)
        Text("Integrations: ${d?.integrationsReady ?: 0}/${d?.integrationsTotal ?: 0}")
        Text("AI providers: ${d?.providersConfigured ?: 0}")
        Text("Protocol: ${d?.protocolVersion ?: "—"}")
        Text("Project $project: ${p?.detail ?: "—"}")
        Text("Health: ${p?.health?.let { if (it) "OK" else "FAIL" } ?: "—"}")
        Button(onClick = refresh, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Refresh") }
    } }
}

@Composable private fun ProjectsScreen(project: String, status: ProjectStatus?, connected: Boolean, busy: Boolean, onSelect: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Projects", style = MaterialTheme.typography.headlineSmall)
        listOf("connect" to "XFI_CONNECT", "webapp" to "XFI 3XUI WebApp").forEach { (id, name) ->
            Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(name, style = MaterialTheme.typography.titleMedium); Text("ID: $id")
                if (project == id && status != null) Text("Status: ${status.detail}")
                Button(onClick = { onSelect(id) }, enabled = connected && !busy, modifier = Modifier.fillMaxWidth()) { Text(if (project == id) "Selected" else "Select") }
            } }
        }
    }
}

@Composable private fun AgentScreen(project: String, request: String, result: AiResult?, busy: Boolean, connected: Boolean, onProject: (String) -> Unit, onRequest: (String) -> Unit, analyze: () -> Unit, generate: () -> Unit, apply: (List<EditPreview>) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("AI Code Agent", style = MaterialTheme.typography.headlineSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { Button(onClick = { onProject("connect") }, enabled = connected) { Text("XFI_CONNECT") }; OutlinedButton(onClick = { onProject("webapp") }, enabled = connected) { Text("WebApp") } }
        OutlinedTextField(request, onRequest, Modifier.fillMaxWidth(), minLines = 5, label = { Text("Describe the change") })
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) { Button(onClick = analyze, enabled = connected && !busy && request.isNotBlank(), modifier = Modifier.weight(1f)) { Text("Analyze") }; OutlinedButton(onClick = generate, enabled = connected && !busy && request.isNotBlank(), modifier = Modifier.weight(1f)) { Text("Generate") } }
        result?.let { r -> Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(if (r.ok) "Agent result" else "Request failed", style = MaterialTheme.typography.titleMedium); Text(r.summary)
            if (r.stage.isNotBlank()) Text("Stage: ${r.stage}"); if (r.questions.isNotEmpty()) Text("Questions: ${r.questions.joinToString("; ")}"); if (r.files.isNotEmpty()) Text("Files: ${r.files.joinToString()}"); if (r.tests.isNotEmpty()) Text("Tests: ${r.tests.joinToString("; ")}")
            if (r.architectureNodes != null) Text("Architecture: ${r.architectureNodes} nodes / ${r.architectureEdges ?: 0} edges")
            if (r.edits.isNotEmpty()) { Text("Proposed changes: ${r.edits.size}"); r.edits.forEach { edit -> Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(10.dp)) { Text(edit.path, style = MaterialTheme.typography.titleSmall); Text(edit.reason) } } }; Button(onClick = { apply(r.edits) }, enabled = connected && !busy) { Text("Apply approved patch") } }
        } } }
    }
}

@Composable private fun AuditScreen(audit: List<String>, connected: Boolean, busy: Boolean, refresh: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text("Audit log", style = MaterialTheme.typography.headlineSmall); TextButton(onClick = refresh, enabled = connected && !busy) { Text("Refresh") } }; if (audit.isEmpty()) Text("No audit entries") else audit.forEach { Text(it) } }
}

@Composable private fun SettingsScreen(endpoint: String, adminKey: String, connected: Boolean, busy: Boolean, onEndpoint: (String) -> Unit, onKey: (String) -> Unit, connect: () -> Unit, disconnect: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { Text("Settings", style = MaterialTheme.typography.headlineSmall); OutlinedTextField(endpoint, onEndpoint, Modifier.fillMaxWidth(), label = { Text("XFI AI HTTPS URL") }); OutlinedTextField(adminKey, onKey, Modifier.fillMaxWidth(), label = { Text("Admin key") }); if (!connected) Button(onClick = connect, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Connect") } else OutlinedButton(onClick = disconnect, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Disconnect") }; Text("Admin session is stored encrypted with Android Keystore.") }
}
