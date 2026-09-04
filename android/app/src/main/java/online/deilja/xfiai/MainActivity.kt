package online.deilja.xfiai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { XfiAiApp(XfiRepository(this), XfiSecureStore(this)) }
    }
}

private enum class Screen { Dashboard, Agent, Projects, Settings }

@Composable
private fun XfiAiApp(repository: XfiRepository, store: XfiSecureStore) {
    var screen by remember { mutableStateOf(Screen.Dashboard) }
    var project by remember { mutableStateOf("connect") }
    var request by remember { mutableStateOf("") }
    var endpoint by remember { mutableStateOf(store.loadEndpoint()) }
    var adminKey by remember { mutableStateOf("") }
    var session by remember { mutableStateOf<String?>(repository.session()) }
    var dashboard by remember { mutableStateOf<DashboardStatus?>(null) }
    var projectStatus by remember { mutableStateOf<ProjectStatus?>(null) }
    var result by remember { mutableStateOf<AiResult?>(null) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    fun api(): XfiAiClient? = if (endpoint.isBlank() || session.isNullOrBlank()) null else repository.client(endpoint)

    fun expireSession() {
        repository.run { }
        session = null
        dashboard = null
        projectStatus = null
        result = null
        message = "Admin session expired. Connect again in Settings."
        screen = Screen.Settings
    }

    fun refresh() {
        val client = api() ?: return
        busy = true
        scope.launch {
            val outcome = withContext(Dispatchers.IO) {
                runCatching { client.dashboard() to client.projectStatus(project) }
            }
            outcome.onSuccess { (d, p) ->
                dashboard = d
                projectStatus = p
                message = null
            }.onFailure { error ->
                if (error is SessionExpiredException) expireSession()
                else message = error.message ?: "Refresh failed"
            }
            busy = false
        }
    }

    LaunchedEffect(project, session, endpoint) {
        if (session != null && endpoint.isNotBlank()) refresh()
    }

    MaterialTheme {
        Scaffold(
            topBar = { TopAppBar(title = { Text("XFI AI", fontWeight = FontWeight.Bold) }) },
            bottomBar = {
                Row(Modifier.fillMaxWidth().padding(8.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                    NavButton("Home", screen == Screen.Dashboard) { screen = Screen.Dashboard }
                    NavButton("Agent", screen == Screen.Agent) { screen = Screen.Agent }
                    NavButton("Projects", screen == Screen.Projects) { screen = Screen.Projects }
                    NavButton("Settings", screen == Screen.Settings) { screen = Screen.Settings }
                }
            }
        ) { padding ->
            Surface(Modifier.fillMaxSize().padding(padding)) {
                when (screen) {
                    Screen.Dashboard -> Dashboard(dashboard, projectStatus, session != null, busy, message) { screen = Screen.Agent }
                    Screen.Agent -> Agent(
                        project, { project = it }, request, { request = it }, result, busy,
                        authenticated = session != null,
                        onAnalyze = {
                            val client = api() ?: run { message = "Connect to XFI AI in Settings first"; return@Agent }
                            busy = true
                            scope.launch {
                                val r = withContext(Dispatchers.IO) {
                                    runCatching { client.customize(project, request) }
                                        .getOrElse { AiResult(false, it.message ?: "Connection failed") }
                                }
                                if (r.raw.contains("\"stage\":\"questions\"")) {
                                    result = r.copy(ok = false)
                                } else {
                                    result = r
                                }
                                busy = false
                            }
                        },
                        onApply = {
                            val client = api() ?: run { message = "Connect to XFI AI in Settings first"; return@Agent }
                            busy = true
                            scope.launch {
                                val r = withContext(Dispatchers.IO) {
                                    runCatching { client.customize(project, request, true) }
                                        .getOrElse { AiResult(false, it.message ?: "Apply failed") }
                                }
                                if (r.raw.contains("401")) expireSession() else result = r
                                busy = false
                                if (session != null) refresh()
                            }
                        }
                    )
                    Screen.Projects -> Projects(project) { project = it }
                    Screen.Settings -> Settings(
                        endpoint, { endpoint = it; store.saveEndpoint(it) }, adminKey, { adminKey = it }, session != null,
                        onLogin = {
                            if (endpoint.isBlank() || adminKey.isBlank()) { message = "Enter XFI AI HTTPS URL and admin key"; return@Settings }
                            busy = true
                            scope.launch {
                                val r = withContext(Dispatchers.IO) { runCatching { repository.login(endpoint, adminKey) } }
                                r.onSuccess {
                                    session = it
                                    adminKey = ""
                                    message = "Connected"
                                    screen = Screen.Dashboard
                                }.onFailure { message = it.message ?: "Login failed" }
                                busy = false
                            }
                        },
                        onLogout = {
                            busy = true
                            scope.launch {
                                withContext(Dispatchers.IO) { repository.logout(endpoint) }
                                session = null
                                dashboard = null
                                projectStatus = null
                                result = null
                                message = "Disconnected"
                                busy = false
                            }
                        },
                        busy = busy,
                        message = message
                    )
                }
            }
        }
    }
}

@Composable
private fun NavButton(label: String, selected: Boolean, onClick: () -> Unit) {
    if (selected) Button(onClick = onClick) { Text(label) } else TextButton(onClick = onClick) { Text(label) }
}

@Composable
private fun Dashboard(
    dashboard: DashboardStatus?, status: ProjectStatus?, connected: Boolean, busy: Boolean, message: String?, openAgent: () -> Unit
) {
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("Command center", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold) }
        item { Text(if (connected) "Secure admin session active." else "Connect the Android client to XFI AI from Settings.") }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                StatusCard("XFI AI", if (connected) "CONNECTED" else "OFFLINE", Modifier.weight(1f))
                StatusCard("Project", if (status?.online == true) "ONLINE" else "—", Modifier.weight(1f))
            }
        }
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("AI Code Agent", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text("Natural-language changes go through architecture analysis, preview, explicit confirmation and the guarded server-side edit pipeline.")
                    Button(onClick = openAgent, enabled = connected, Modifier.fillMaxWidth()) { Text("Open Agent") }
                }
            }
        }
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("System", fontWeight = FontWeight.Bold)
                    Text("Integrations: ${dashboard?.integrationsReady ?: 0}/${dashboard?.integrationsTotal ?: 0}")
                    Text("AI providers: ${dashboard?.providersConfigured ?: 0}")
                    Text("Protocol: ${dashboard?.protocolVersion ?: "—"}")
                    Text("${status?.name ?: "Project"}: ${status?.detail ?: "not loaded"}")
                    message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
        item { if (busy) Text("Updating…") }
    }
}

@Composable
private fun StatusCard(title: String, value: String, modifier: Modifier) {
    Card(modifier) { Column(Modifier.padding(16.dp)) { Text(title); Spacer(Modifier.height(6.dp)); Text(value, fontWeight = FontWeight.Bold) } }
}

@Composable
private fun Projects(selected: String, choose: (String) -> Unit) {
    Column(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Projects", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        ProjectCard("connect", "XFI_CONNECT", "Telegram VPN backend", selected == "connect", choose)
        ProjectCard("webapp", "XFI_3XUI_WebApp", "Web VPN control plane", selected == "webapp", choose)
        Text("XFI Guard is intentionally not connected to this application.", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun ProjectCard(id: String, name: String, description: String, selected: Boolean, choose: (String) -> Unit) {
    Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp)) {
        Row(Modifier.padding(16.dp)) {
            Column(Modifier.weight(1f)) { Text(name, fontWeight = FontWeight.Bold); Text(description) }
            FilterChip(selected, onClick = { choose(id) }, label = { Text(if (selected) "Active" else "Select") })
        }
    }
}

@Composable
private fun Agent(
    project: String, chooseProject: (String) -> Unit, request: String, setRequest: (String) -> Unit,
    result: AiResult?, busy: Boolean, authenticated: Boolean, onAnalyze: () -> Unit, onApply: () -> Unit
) {
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("AI Code Agent", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(project == "connect", { chooseProject("connect") }, label = { Text("XFI_CONNECT") })
                FilterChip(project == "webapp", { chooseProject("webapp") }, label = { Text("WebApp") })
            }
        }
        item {
            OutlinedTextField(
                value = request, onValueChange = { setRequest(it.take(8000)) }, Modifier.fillMaxWidth(),
                minLines = 5, label = { Text("Describe the change") },
                placeholder = { Text("Make the start message modern and add a Support button") }
            )
        }
        item {
            Button(onClick = onAnalyze, enabled = authenticated && !busy && request.isNotBlank(), Modifier.fillMaxWidth()) {
                Text(if (busy) "Working…" else "Analyze & Preview")
            }
        }
        result?.let { r ->
            item {
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(if (r.ok) "Preview / result" else "Request failed", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text(r.summary)
                        if (r.questions.isNotEmpty()) { HorizontalDivider(); Text("Questions", fontWeight = FontWeight.Bold); r.questions.forEach { Text("• $it") } }
                        if (r.edits.isNotEmpty()) {
                            HorizontalDivider(); Text("Patch preview", fontWeight = FontWeight.Bold)
                            r.edits.forEach { edit -> Text(edit.path, fontWeight = FontWeight.Bold); if (edit.reason.isNotBlank()) Text(edit.reason, style = MaterialTheme.typography.bodySmall) }
                        } else if (r.files.isNotEmpty()) {
                            HorizontalDivider(); Text("Affected files", fontWeight = FontWeight.Bold); r.files.forEach { Text("• $it") }
                        }
                        if (r.tests.isNotEmpty()) { HorizontalDivider(); Text("Validation", fontWeight = FontWeight.Bold); r.tests.forEach { Text("• $it") } }
                        if (r.ok && r.questions.isEmpty() && r.edits.isNotEmpty()) {
                            OutlinedButton(onClick = onApply, enabled = !busy, Modifier.fillMaxWidth()) { Text("Apply approved patch") }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Settings(
    endpoint: String, setEndpoint: (String) -> Unit, adminKey: String, setAdminKey: (String) -> Unit,
    connected: Boolean, onLogin: () -> Unit, onLogout: () -> Unit, busy: Boolean, message: String?
) {
    Column(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Secure connection", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text("The app uses the existing XFI AI admin session API. The admin key is used only to obtain a short-lived session and is never persisted.")
        OutlinedTextField(endpoint, setEndpoint, Modifier.fillMaxWidth(), label = { Text("XFI AI HTTPS URL") }, placeholder = { Text("https://ai.example.com") })
        if (!connected) {
            OutlinedTextField(adminKey, setAdminKey, Modifier.fillMaxWidth(), label = { Text("Admin key") })
            Button(onClick = onLogin, enabled = !busy, Modifier.fillMaxWidth()) { Text(if (busy) "Connecting…" else "Connect securely") }
        } else {
            Text("Admin session active", fontWeight = FontWeight.Bold)
            OutlinedButton(onClick = onLogout, enabled = !busy, Modifier.fillMaxWidth()) { Text("Disconnect") }
        }
        message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        Text("Session is encrypted with Android Keystore on this device.", style = MaterialTheme.typography.bodySmall)
    }
}
