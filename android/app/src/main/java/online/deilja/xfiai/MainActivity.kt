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
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
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

private enum class Screen { Dashboard, Agent, Projects, Audit, Settings }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun XfiAiApp(repository: XfiRepository) {
    val context = LocalContext.current.applicationContext
    val store = remember { XfiSecureStore(context) }
    var screen by remember { mutableStateOf(Screen.Dashboard) }
    var project by remember { mutableStateOf("connect") }
    var request by remember { mutableStateOf("") }
    var endpoint by remember { mutableStateOf(store.loadEndpoint()) }
    var adminKey by remember { mutableStateOf("") }
    var session by remember { mutableStateOf<String?>(null) }
    var dashboard by remember { mutableStateOf<DashboardStatus?>(null) }
    var status by remember { mutableStateOf<ProjectStatus?>(null) }
    var result by remember { mutableStateOf<AiResult?>(null) }
    var answers by remember { mutableStateOf<List<Answer>>(emptyList()) }
    var audit by remember { mutableStateOf<List<String>>(emptyList()) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    fun client(): XfiAiClient? = if (endpoint.isBlank() || session.isNullOrBlank()) null else XfiAiClient(endpoint, session)
    fun expired() {
        session = null; store.clearSession(); dashboard = null; status = null; result = null; answers = emptyList(); audit = emptyList()
        message = "Admin session expired. Connect again in Settings."; screen = Screen.Settings
    }
    fun refresh() {
        val c = client() ?: return
        busy = true
        scope.launch {
            val r = withContext(Dispatchers.IO) { runCatching { c.dashboard() to c.projectStatus(project) } }
            r.onSuccess { (d, p) -> dashboard = d; status = p; message = null }
                .onFailure { e -> if (e is SessionExpiredException) expired() else message = e.message ?: "Refresh failed" }
            busy = false
        }
    }
    fun reloadAudit() {
        val c = client() ?: return
        busy = true
        scope.launch {
            val r = withContext(Dispatchers.IO) { runCatching { c.audit(project) } }
            r.onSuccess { audit = it; message = null }
                .onFailure { e -> if (e is SessionExpiredException) expired() else message = e.message ?: "Audit failed" }
            busy = false
        }
    }

    LaunchedEffect(Unit) {
        val saved = withContext(Dispatchers.IO) { store.loadSession() }
        if (!saved.isNullOrBlank()) session = saved
    }
    LaunchedEffect(project, session, endpoint) { if (session != null && endpoint.isNotBlank()) refresh() }

    MaterialTheme {
        Scaffold(
            topBar = { TopAppBar(title = { Text("XFI AI", fontWeight = FontWeight.Bold) }) },
            bottomBar = { Row(Modifier.fillMaxWidth().padding(6.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                NavButton("Home", screen == Screen.Dashboard) { screen = Screen.Dashboard }
                NavButton("Agent", screen == Screen.Agent) { screen = Screen.Agent }
                NavButton("Projects", screen == Screen.Projects) { screen = Screen.Projects }
                NavButton("Audit", screen == Screen.Audit) { screen = Screen.Audit; reloadAudit() }
                NavButton("Settings", screen == Screen.Settings) { screen = Screen.Settings }
            } }
        ) { padding ->
            Surface(Modifier.fillMaxSize().padding(padding)) {
                when (screen) {
                    Screen.Dashboard -> Dashboard(dashboard, status, session != null, busy, message) { screen = Screen.Agent }
                    Screen.Agent -> Agent(
                        project, { project = it; result = null; answers = emptyList() }, request, { request = it }, result, answers, busy, session != null,
                        onAnalyze = {
                            val c = client()
                            if (c == null) message = "Connect to XFI AI in Settings first" else {
                                busy = true
                                scope.launch {
                                    val r = withContext(Dispatchers.IO) { runCatching { c.analyze(project, request) } }
                                    r.onSuccess { value ->
                                        result = value
                                        answers = value.questions.map { q -> Answer(q, answers.firstOrNull { a -> a.question == q }?.answer.orEmpty()) }
                                        message = if (value.questions.isEmpty()) null else "Answer the questions before building the patch"
                                    }.onFailure { e -> if (e is SessionExpiredException) expired() else result = AiResult(false, e.message ?: "Analysis failed") }
                                    busy = false
                                }
                            }
                        },
                        onGenerate = {
                            val c = client()
                            when {
                                c == null -> message = "Connect to XFI AI in Settings first"
                                answers.any { it.answer.isBlank() } -> message = "Answer every clarification question"
                                else -> {
                                    busy = true
                                    scope.launch {
                                        val r = withContext(Dispatchers.IO) { runCatching { c.generate(project, request, answers) } }
                                        r.onSuccess { result = it; message = null }
                                            .onFailure { e -> if (e is SessionExpiredException) expired() else message = e.message ?: "Patch generation failed" }
                                        busy = false
                                    }
                                }
                            }
                        },
                        onAnswer = { q, a -> answers = answers.map { if (it.question == q) it.copy(answer = a) else it } },
                        onApply = {
                            val patch = result?.edits.orEmpty(); val c = client()
                            when {
                                c == null -> message = "Connect to XFI AI in Settings first"
                                patch.isEmpty() -> message = "No approved patch available"
                                else -> {
                                    busy = true
                                    scope.launch {
                                        val r = withContext(Dispatchers.IO) { runCatching { c.apply(project, patch, restart = true) } }
                                        r.onSuccess { result = it; message = "Patch applied and validated" }
                                            .onFailure { e -> if (e is SessionExpiredException) expired() else message = e.message ?: "Apply failed" }
                                        busy = false
                                        if (session != null) refresh()
                                    }
                                }
                            }
                        }
                    )
                    Screen.Projects -> Projects(project) { project = it }
                    Screen.Audit -> Audit(project, audit, busy, session != null, ::reloadAudit)
                    Screen.Settings -> Settings(
                        endpoint, { endpoint = it; store.saveEndpoint(it) }, adminKey, { adminKey = it }, session != null,
                        onLogin = {
                            if (endpoint.isBlank() || adminKey.isBlank()) message = "Enter XFI AI HTTPS URL and admin key" else {
                                busy = true
                                scope.launch {
                                    val r = withContext(Dispatchers.IO) { runCatching { repository.login(endpoint, adminKey) } }
                                    r.onSuccess { session = it; adminKey = ""; message = "Connected"; screen = Screen.Dashboard }
                                        .onFailure { message = it.message ?: "Login failed" }
                                    busy = false
                                }
                            }
                        },
                        onLogout = {
                            busy = true
                            scope.launch {
                                withContext(Dispatchers.IO) { repository.logout(endpoint) }
                                session = null; dashboard = null; status = null; result = null; answers = emptyList(); audit = emptyList()
                                message = "Disconnected"; busy = false
                            }
                        }, busy, message
                    )
                }
            }
        )
    }
}

@Composable private fun NavButton(label: String, selected: Boolean, onClick: () -> Unit) {
    if (selected) Button(onClick = onClick) { Text(label) } else TextButton(onClick = onClick) { Text(label) }
}

@Composable private fun Dashboard(dashboard: DashboardStatus?, status: ProjectStatus?, connected: Boolean, busy: Boolean, message: String?, openAgent: () -> Unit) {
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("Command center", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold) }
        item { Text(if (connected) "Secure admin session active." else "Connect the Android client to XFI AI from Settings.") }
        item { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatusCard("XFI AI", if (connected) "CONNECTED" else "OFFLINE", Modifier.weight(1f))
            StatusCard("Project", if (status?.online == true) "ONLINE" else "—", Modifier.weight(1f))
        } }
        item { Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("AI Code Agent", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text("Natural-language changes are analyzed against project architecture, previewed, explicitly confirmed and validated with rollback protection.")
            Button(onClick = openAgent, enabled = connected, modifier = Modifier.fillMaxWidth()) { Text("Open Agent") }
        } } }
        item { Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("System", fontWeight = FontWeight.Bold)
            Text("Integrations: ${dashboard?.integrationsReady ?: 0}/${dashboard?.integrationsTotal ?: 0}")
            Text("AI providers: ${dashboard?.providersConfigured ?: 0}")
            Text("Protocol: ${dashboard?.protocolVersion ?: "—"}")
            Text("${status?.name ?: "Project"}: ${status?.detail ?: "not loaded"}")
            message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        } } }
        if (busy) item { Text("Updating…") }
    }
}

@Composable private fun StatusCard(title: String, value: String, modifier: Modifier) {
    Card(modifier) { Column(Modifier.padding(16.dp)) { Text(title); Spacer(Modifier.height(6.dp)); Text(value, fontWeight = FontWeight.Bold) } }
}

@Composable private fun Projects(selected: String, choose: (String) -> Unit) {
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("Projects", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold) }
        item { ProjectCard("connect", "XFI_CONNECT", "Telegram VPN backend", selected == "connect", choose) }
        item { ProjectCard("webapp", "XFI_3XUI_WebApp", "Web VPN control plane", selected == "webapp", choose) }
        item { Text("XFI Guard is intentionally not connected to this application.", style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable private fun ProjectCard(id: String, name: String, description: String, selected: Boolean, choose: (String) -> Unit) {
    Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp)) { Row(Modifier.padding(16.dp)) {
        Column(Modifier.weight(1f)) { Text(name, fontWeight = FontWeight.Bold); Text(description) }
        FilterChip(selected = selected, onClick = { choose(id) }, label = { Text(if (selected) "Active" else "Select") })
    } }
}

@Composable private fun Agent(project: String, chooseProject: (String) -> Unit, request: String, setRequest: (String) -> Unit,
                              result: AiResult?, answers: List<Answer>, busy: Boolean, authenticated: Boolean,
                              onAnalyze: () -> Unit, onGenerate: () -> Unit, onAnswer: (String, String) -> Unit, onApply: () -> Unit) {
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("AI Code Agent", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold) }
        item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(project == "connect", { chooseProject("connect") }, label = { Text("XFI_CONNECT") })
            FilterChip(project == "webapp", { chooseProject("webapp") }, label = { Text("WebApp") })
        } }
        item { OutlinedTextField(request, { setRequest(it.take(8000)) }, Modifier.fillMaxWidth(), minLines = 5, label = { Text("Describe the change") }, placeholder = { Text("Make the start message modern and add a Support button") }) }
        item { Button(onClick = onAnalyze, enabled = authenticated && !busy && request.isNotBlank(), modifier = Modifier.fillMaxWidth()) { Text(if (busy) "Analyzing…" else "Analyze architecture") } }
        result?.let { r ->
            item { Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(if (r.ok) "Agent result" else "Request failed", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text(r.summary)
                if (r.architectureNodes != null) Text("Architecture: ${r.architectureNodes} nodes / ${r.architectureEdges ?: 0} edges", style = MaterialTheme.typography.bodySmall)
                if (r.questions.isNotEmpty()) {
                    HorizontalDivider(); Text("Clarification required", fontWeight = FontWeight.Bold)
                    r.questions.forEach { q ->
                        val a = answers.firstOrNull { it.question == q }?.answer.orEmpty()
                        OutlinedTextField(a, { onAnswer(q, it.take(2000)) }, Modifier.fillMaxWidth(), label = { Text(q) })
                    }
                    Button(onClick = onGenerate, enabled = !busy && answers.all { it.answer.isNotBlank() }, modifier = Modifier.fillMaxWidth()) { Text(if (busy) "Building patch…" else "Build patch") }
                }
                if (r.edits.isNotEmpty()) {
                    HorizontalDivider(); Text("Patch preview", fontWeight = FontWeight.Bold)
                    r.edits.forEach { e ->
                        Text(e.path, fontWeight = FontWeight.Bold)
                        if (e.reason.isNotBlank()) Text(e.reason, style = MaterialTheme.typography.bodySmall)
                        if (e.content.isNotBlank()) { Text("New content", style = MaterialTheme.typography.labelMedium); Text(e.content.take(1600), style = MaterialTheme.typography.bodySmall) }
                    }
                }
                if (r.tests.isNotEmpty()) { HorizontalDivider(); Text("Validation", fontWeight = FontWeight.Bold); r.tests.forEach { Text("• $it") } }
                if (r.ok && r.questions.isEmpty() && r.edits.isNotEmpty() && r.stage != "apply") OutlinedButton(onClick = onApply, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Apply approved patch") }
            } } }
        }
    }
}

@Composable private fun Audit(project: String, entries: List<String>, busy: Boolean, authenticated: Boolean, reload: () -> Unit) {
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("Audit — $project", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold) }
        item { Button(onClick = reload, enabled = authenticated && !busy, modifier = Modifier.fillMaxWidth()) { Text(if (busy) "Loading…" else "Refresh audit") } }
        if (entries.isEmpty()) item { Text("No audit events loaded.") }
        entries.forEach { e -> item { Card(Modifier.fillMaxWidth()) { Text(e, Modifier.padding(14.dp), style = MaterialTheme.typography.bodySmall) } } }
    }
}

@Composable private fun Settings(endpoint: String, setEndpoint: (String) -> Unit, adminKey: String, setAdminKey: (String) -> Unit,
                                connected: Boolean, onLogin: () -> Unit, onLogout: () -> Unit, busy: Boolean, message: String?) {
    Column(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Secure connection", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text("The admin key is used only to obtain a session and is never persisted. The session is encrypted with Android Keystore.")
        OutlinedTextField(endpoint, setEndpoint, Modifier.fillMaxWidth(), label = { Text("XFI AI HTTPS URL") }, placeholder = { Text("https://ai.example.com") })
        if (!connected) {
            OutlinedTextField(adminKey, setAdminKey, Modifier.fillMaxWidth(), label = { Text("Admin key") })
            Button(onClick = onLogin, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text(if (busy) "Connecting…" else "Connect securely") }
        } else {
            Text("Admin session active", fontWeight = FontWeight.Bold)
            OutlinedButton(onClick = onLogout, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Disconnect") }
        }
        message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
    }
}
