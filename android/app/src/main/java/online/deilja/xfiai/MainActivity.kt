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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { XfiAiApp() }
    }
}

@Composable
private fun XfiAiApp() {
    var request by rememberSaveable { mutableStateOf("") }
    var project by rememberSaveable { mutableStateOf("connect") }
    var status by rememberSaveable { mutableStateOf("Ready") }

    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier.fillMaxSize().padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text("XFI AI", style = MaterialTheme.typography.headlineMedium)
                Text("Mobile administrator console", style = MaterialTheme.typography.bodyMedium)

                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Project", style = MaterialTheme.typography.titleMedium)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (project == "connect") {
                                Button(onClick = { project = "connect" }) { Text("XFI_CONNECT") }
                                OutlinedButton(onClick = { project = "webapp" }) { Text("WebApp") }
                            } else {
                                OutlinedButton(onClick = { project = "connect" }) { Text("XFI_CONNECT") }
                                Button(onClick = { project = "webapp" }) { Text("WebApp") }
                            }
                        }
                    }
                }

                OutlinedTextField(
                    value = request,
                    onValueChange = { request = it.take(8000) },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 4,
                    label = { Text("What should XFI AI change?") },
                    placeholder = { Text("For example: make the start message more modern") }
                )

                Button(
                    onClick = { status = if (request.isBlank()) "Enter a request" else "Analysis requested for $project" },
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Analyze") }

                Text("Status: $status")
                Text("Changes are previewed before application. Secrets and unrestricted root access are never exposed to the app.", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
