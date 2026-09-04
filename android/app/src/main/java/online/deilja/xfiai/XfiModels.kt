package online.deilja.xfiai

data class ProjectStatus(
    val id: String,
    val name: String,
    val online: Boolean,
    val detail: String
)

data class AiResult(
    val ok: Boolean,
    val summary: String,
    val questions: List<String> = emptyList(),
    val files: List<String> = emptyList(),
    val raw: String = ""
)
