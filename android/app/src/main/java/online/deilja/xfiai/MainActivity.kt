package online.deilja.xfiai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { XfiAiApp() }
    }
}

private enum class Screen { Dashboard, Agent, Projects, Settings }

@Composable
private fun XfiAiApp() {
    var screen by remember { mutableStateOf(Screen.Dashboard) }
    var project by remember { mutableStateOf("connect") }
    var request by remember { mutableStateOf("") }
    var endpoint by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    var result by remember { mutableStateOf<AiResult?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

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
                    Screen.Dashboard -> Dashboard(project) { screen = Screen.Agent }
                    Screen.Agent -> Agent(
                        project, { project = it }, request, { request = it }, result, busy,
                        onAnalyze = {
                            if (endpoint.isBlank() || request.isBlank()) return@Agent
                            busy = true
                            scope.launch(Dispatchers.IO) {
                                val r = runCatching { XfiAiClient(endpoint, token).customize(project, request) }
                                    .getOrElse { AiResult(false, it.message ?: "Connection failed") }
                                withContext(Dispatchers.Main) { result = r; busy = false }
                            }
                        }, onApply = {
                            if (endpoint.isBlank() || request.isBlank()) return@Agent
                            busy = true
                            scope.launch(Dispatchers.IO) {
                                val r = runCatching { XfiAiClient(endpoint, token).customize(project, request, true) }
                                    .getOrElse { AiResult(false, it.message ?: "Apply failed") }
                                withContext(Dispatchers.Main) { result = r; busy = false }
                            }
                        }
                    )
                    Screen.Projects -> Projects(project) { project = it }
                    Screen.Settings -> Settings(endpoint, { endpoint = it }, token, { token = it })
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
private fun Dashboard(project: String, openAgent: () -> Unit) {
    LazyColumn(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("Command center", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold) }
        item { Text("Control XFI projects through natural language.", style = MaterialTheme.typography.bodyLarge) }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                StatusCard("XFI AI", "READY", Modifier.weight(1f))
                StatusCard("Project", if (project == "connect") "CONNECT" else "WEBAPP", Modifier.weight(1f))
            }
        }
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("AI Code Agent", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text("Describe a customization. XFI AI analyzes the architecture, prepares a minimal patch and waits for confirmation.")
                    Button(onClick = openAgent, Modifier.fillMaxWidth()) { Text("Open Agent") }
                }
            }
        }
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
    Card(Modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(name, fontWeight = FontWeight.Bold); Text(description) }
            FilterChip(selected, onClick = { choose(id) }, label = { Text(if (selected) "Active" else "Select") })
        }
    }
}

@Composable
private fun Agent(
    project: String, chooseProject: (String) -> Unit, request: String, setRequest: (String) -> Unit,
    result: AiResult?, busy: Boolean, onAnalyze: () -> Unit, onApply: () -> Unit
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
            Button(onClick = onAnalyze, enabled = !busy && request.isNotBlank(), Modifier.fillMaxWidth()) {
                Text(if (busy) "Working…" else "Analyze & Preview")
            }
        }
        result?.let { r ->
            item {
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(if (r.ok) "Preview ready" else "Request failed", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text(r.summary)
                        if (r.questions.isNotEmpty()) { HorizontalDivider(); Text("Questions", fontWeight = FontWeight.Bold); r.questions.forEach { Text("• $it") } }
                        if (r.files.isNotEmpty()) { HorizontalDivider(); Text("Affected files", fontWeight = FontWeight.Bold); r.files.forEach { Text("• $it") } }
                        if (r.ok && r.questions.isEmpty()) {
                            OutlinedButton(onClick = onApply, enabled = !busy, Modifier.fillMaxWidth()) { Text("Apply approved patch") }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Settings(endpoint: String, setEndpoint: (String) -> Unit, token: String, setToken: (String) -> Unit) {
    Column(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Connection", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text("The Android client talks only to XFI AI. Keep the API endpoint on HTTPS.")
        OutlinedTextField(endpoint, setEndpoint, Modifier.fillMaxWidth(), label = { Text("XFI AI URL") }, placeholder = { Text("https://ai.example.com") })
        OutlinedTextField(token, setToken, Modifier.fillMaxWidth(), label = { Text("XFI AI token") })
        Text("Token storage will use Android Keystore in the production build.", style = MaterialTheme.typography.bodySmall)
    }
}
