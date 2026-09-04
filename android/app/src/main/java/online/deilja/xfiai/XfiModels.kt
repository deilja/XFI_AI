package online.deilja.xfiai

data class ProjectStatus(
    val id: String,
    val name: String,
    val online: Boolean,
    val health: Boolean?,
    val detail: String
)

data class DashboardStatus(
    val integrationsReady: Int,
    val integrationsTotal: Int,
    val providersConfigured: Int,
    val protocolVersion: String
)

data class AiResult(
    val ok: Boolean,
    val summary: String,
    val questions: List<String> = emptyList(),
    val files: List<String> = emptyList(),
    val edits: List<EditPreview> = emptyList(),
    val tests: List<String> = emptyList(),
    val raw: String = ""
)

data class EditPreview(val path: String, val reason: String)
