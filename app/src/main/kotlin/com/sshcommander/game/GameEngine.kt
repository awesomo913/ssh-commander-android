package com.sshcommander.game

import com.sshcommander.data.Category
import com.sshcommander.data.CommandBank
import com.sshcommander.data.SshCommand
import java.util.regex.Pattern
import kotlin.math.min
import kotlin.random.Random

// ─── Result types ─────────────────────────────────────────────────────────────

enum class AnswerStatus { CORRECT, WRONG }

data class AnswerResult(
    val status: AnswerStatus,
    val pointsEarned: Int,
    val hint: String,
    val newStreak: Int
)

data class LearnCard(
    val command: SshCommand,
    val cardIndex: Int,
    val totalCards: Int
)

data class ChallengeSession(
    val command: SshCommand,
    val startTimeMs: Long,
    val livesRemaining: Int
)

// ─── Scoring constants ────────────────────────────────────────────────────────

private const val POINTS_LEARN = 10
private const val POINTS_CHALLENGE = 20
private const val POINTS_BOSS_STEP = 50
private const val STREAK_BONUS_PER_CORRECT = 5
private const val MAX_STREAK_FOR_BONUS = 10
private const val TIME_BONUS_MAX = 15
private const val TIME_BONUS_CUTOFF_S = 8L
private const val TIME_BONUS_FADE_END_S = 30L

// ─── Boss scenarios ───────────────────────────────────────────────────────────

data class BossStep(
    val commandId: Int,
    val promptOverride: String = ""        // if blank, use command.description
)

data class BossScenario(
    val index: Int,
    val title: String,
    val story: String,
    val steps: List<BossStep>
)

object BossScenarios {

    val all: List<BossScenario> = listOf(

        BossScenario(
            index = 0,
            title = "Set Up a Fresh Pi",
            story = "You just unboxed a Raspberry Pi and need to harden it for remote access. " +
                    "Walk through generating a key pair, copying it over, logging in for the first " +
                    "time, locking down the sshd config, and restarting the daemon.",
            steps = listOf(
                BossStep(3,  "Generate a new ED25519 SSH key pair"),
                BossStep(4,  "Copy your public key to the Raspberry Pi"),
                BossStep(0,  "Log in to the Pi via SSH"),
                BossStep(47, "Open the SSH server config file for editing"),
                BossStep(48, "Restart the SSH daemon to apply your changes")
            )
        ),

        BossScenario(
            index = 1,
            title = "Deploy a Script and Run It",
            story = "You wrote a long-running data-processing script locally and need to ship it " +
                    "to a remote server, SSH in, and kick it off in the background so it keeps " +
                    "running after you disconnect.",
            steps = listOf(
                BossStep(12, "Copy your script file to the remote server"),
                BossStep(0,  "SSH into the remote server"),
                BossStep(29, "Run the script in the background with nohup so it survives disconnect")
            )
        ),

        BossScenario(
            index = 2,
            title = "Fix a Known-Hosts Problem",
            story = "A remote server was reinstalled and now SSH refuses to connect because the " +
                    "stored host key doesn't match. Clear the stale entry, fix directory permissions, " +
                    "secure the private key, then re-establish trust.",
            steps = listOf(
                BossStep(41, "Remove the stale host entry from known_hosts"),
                BossStep(43, "Set correct permissions on your ~/.ssh directory"),
                BossStep(42, "Set correct permissions on your private key file"),
                BossStep(4,  "Copy your public key to the remote host to re-establish trust")
            )
        ),

        BossScenario(
            index = 3,
            title = "Forward a Database Port",
            story = "A PostgreSQL database on a remote server listens only on localhost:5432. " +
                    "You need to create a tunnel so your local machine can reach it on port 5432 " +
                    "without opening a remote shell.",
            steps = listOf(
                BossStep(25, "Create a background local port forward for the database (no shell)")
            )
        ),

        BossScenario(
            index = 4,
            title = "Sync a Project to a Remote Server",
            story = "You finished a feature locally and need to push it to a staging server. " +
                    "First do a normal sync, then do a mirror sync that removes files deleted locally.",
            steps = listOf(
                BossStep(16, "Sync your local project directory to the remote server with rsync"),
                BossStep(17, "Mirror sync: delete remote files that no longer exist locally")
            )
        ),

        BossScenario(
            index = 5,
            title = "Investigate a Security Incident",
            story = "You suspect unauthorized SSH access to a production server. Walk through " +
                    "checking login history, current sessions, recent sshd logs, and fail2ban status.",
            steps = listOf(
                BossStep(51, "Show recent login history"),
                BossStep(52, "Show who is currently logged in"),
                BossStep(53, "Show the last 50 sshd log lines from the system journal"),
                BossStep(50, "Check fail2ban's SSH jail status and list of banned IPs")
            )
        )
    )
}

// ─── Answer checker ───────────────────────────────────────────────────────────

object AnswerChecker {

    private val placeholderPattern = Regex("""<[^>]+>""")

    /** Normalize: lowercase + collapse all whitespace to single spaces. */
    fun normalize(s: String): String =
        s.lowercase().trim().replace(Regex("""\s+"""), " ")

    /**
     * Convert a command template into a regex that accepts any non-whitespace
     * value in each placeholder slot.
     *
     * Pipeline:
     * 1. normalize
     * 2. regex-escape the entire string
     * 3. replace every escaped placeholder \<...\> with \S+
     */
    fun templateToRegex(template: String): Regex {
        val normalized = normalize(template)
        // Pattern.quote-escape each character, then fix placeholders
        val escaped = Pattern.quote(normalized)
            // Pattern.quote wraps in \Q...\E — we need to handle placeholders inside
            // Better: manually escape regex metacharacters then swap placeholders
        val manualEscape = normalized
            .replace("\\", "\\\\")
            .replace(".", "\\.")
            .replace("*", "\\*")
            .replace("+", "\\+")
            .replace("?", "\\?")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("[", "\\[")
            .replace("]", "\\]")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("^", "\\^")
            .replace("$", "\\$")
            .replace("|", "\\|")
        // Replace escaped placeholder forms: \<word\> → \S+
        val withPlaceholders = manualEscape.replace(Regex("""\\?<[^>]+>"""), """\\S+""")
        return Regex(withPlaceholders)
    }

    /**
     * Extract the non-placeholder tokens (flags, verbs, literal strings).
     * Used for the "bare flags" acceptance path.
     */
    fun nonPlaceholderTokens(template: String): List<String> {
        val stripped = placeholderPattern.replace(normalize(template), "").trim()
        return stripped.split(Regex("""\s+""")).filter { it.isNotEmpty() }
    }

    /**
     * Four acceptance paths (first match wins):
     * 1. Template regex fullmatch
     * 2. Alias regex fullmatch (for each alias)
     * 3. Exact normalized string match against template/aliases
     * 4. Non-placeholder tokens only (bare flags path, needs ≥2 tokens)
     */
    fun check(command: SshCommand, userInput: String): Boolean {
        val input = normalize(userInput)
        if (input.isEmpty()) return false

        // Path 1: template regex
        val templateRegex = templateToRegex(command.command)
        if (templateRegex.matches(input)) return true

        // Path 2: alias regex
        for (alias in command.aliases) {
            if (templateToRegex(alias).matches(input)) return true
        }

        // Path 3: exact normalized match
        if (input == normalize(command.command)) return true
        for (alias in command.aliases) {
            if (input == normalize(alias)) return true
        }
        if (command.syntaxExample.isNotEmpty() && input == normalize(command.syntaxExample)) return true

        // Path 4: bare non-placeholder tokens (≥2 tokens, all present in input)
        val bare = nonPlaceholderTokens(command.command)
        if (bare.size >= 2) {
            val inputTokens = input.split(Regex("""\s+"""))
            if (bare.all { it in inputTokens }) return true
        }

        return false
    }

    /** Generate a hint string for a failed attempt. */
    fun hint(command: SshCommand, userInput: String): String {
        val input = normalize(userInput)
        val templateTokens = normalize(command.command).split(Regex("""\s+"""))
        val inputTokens = input.split(Regex("""\s+"""))
        val firstExpected = templateTokens.firstOrNull() ?: ""
        val firstGiven = inputTokens.firstOrNull() ?: ""
        return if (firstGiven != firstExpected && firstExpected.isNotEmpty()) {
            "Starts with '${firstExpected}'"
        } else {
            "Expected: ${command.command}"
        }
    }
}

// ─── Learn mode ───────────────────────────────────────────────────────────────

class LearnSession(
    private val commands: List<SshCommand>
) {
    private val deck: MutableList<SshCommand> = commands.shuffled().toMutableList()
    private var index = 0
    var streak = 0
        private set
    var score = 0
        private set
    var correctCount = 0
        private set
    var wrongCount = 0
        private set

    val totalCards: Int get() = deck.size
    val currentIndex: Int get() = index

    fun currentCard(): SshCommand? = deck.getOrNull(index)

    fun hasNext(): Boolean = index < deck.size

    fun submit(userInput: String): AnswerResult {
        val cmd = currentCard() ?: return AnswerResult(AnswerStatus.WRONG, 0, "No card loaded", streak)
        val correct = AnswerChecker.check(cmd, userInput)
        return if (correct) {
            streak++
            val pts = POINTS_LEARN + min(streak, MAX_STREAK_FOR_BONUS) * STREAK_BONUS_PER_CORRECT
            score += pts
            correctCount++
            index++
            AnswerResult(AnswerStatus.CORRECT, pts, "", streak)
        } else {
            streak = 0
            wrongCount++
            val h = AnswerChecker.hint(cmd, userInput)
            AnswerResult(AnswerStatus.WRONG, 0, h, streak)
        }
    }

    fun skip() {
        streak = 0
        index++
    }

    fun accuracy(): Float =
        if (correctCount + wrongCount == 0) 0f
        else correctCount.toFloat() / (correctCount + wrongCount)
}

// ─── Challenge mode ───────────────────────────────────────────────────────────

data class ChallengeState(
    val command: SshCommand,
    val cardIndex: Int,
    val totalCards: Int,
    val livesTotal: Int,
    var livesRemaining: Int,
    val startTimeMs: Long
)

class ChallengeSession(
    commands: List<SshCommand>,
    val livesTotal: Int
) {
    private val deck: MutableList<SshCommand> = commands.shuffled().toMutableList()
    private var index = 0
    var streak = 0
        private set
    var score = 0
        private set
    var correctCount = 0
        private set
    var wrongCount = 0
        private set
    var lives = livesTotal
        private set
    var cardStartMs: Long = System.currentTimeMillis()
        private set

    val totalCards: Int get() = deck.size
    val currentIndex: Int get() = index

    fun isGameOver(): Boolean = lives <= 0
    fun isComplete(): Boolean = index >= deck.size

    fun currentCard(): SshCommand? = deck.getOrNull(index)

    fun advanceCard() {
        index++
        cardStartMs = System.currentTimeMillis()
    }

    fun submit(userInput: String): AnswerResult {
        val cmd = currentCard() ?: return AnswerResult(AnswerStatus.WRONG, 0, "No card", streak)
        val correct = AnswerChecker.check(cmd, userInput)
        val elapsedS = (System.currentTimeMillis() - cardStartMs) / 1000L
        return if (correct) {
            streak++
            val timePts = calcTimeBonus(elapsedS)
            val pts = POINTS_CHALLENGE + min(streak, MAX_STREAK_FOR_BONUS) * STREAK_BONUS_PER_CORRECT + timePts
            score += pts
            correctCount++
            advanceCard()
            AnswerResult(AnswerStatus.CORRECT, pts, "", streak)
        } else {
            streak = 0
            lives--
            wrongCount++
            val h = AnswerChecker.hint(cmd, userInput)
            AnswerResult(AnswerStatus.WRONG, 0, h, streak)
        }
    }

    private fun calcTimeBonus(elapsedS: Long): Int = when {
        elapsedS <= TIME_BONUS_CUTOFF_S -> TIME_BONUS_MAX
        elapsedS >= TIME_BONUS_FADE_END_S -> 0
        else -> (TIME_BONUS_MAX * (1.0 - (elapsedS - TIME_BONUS_CUTOFF_S).toDouble() /
                (TIME_BONUS_FADE_END_S - TIME_BONUS_CUTOFF_S))).toInt()
    }

    fun accuracy(): Float =
        if (correctCount + wrongCount == 0) 0f
        else correctCount.toFloat() / (correctCount + wrongCount)
}

// ─── Boss mode ────────────────────────────────────────────────────────────────

class BossSession(val scenario: BossScenario) {
    private var stepIndex = 0
    var streak = 0
        private set
    var score = 0
        private set
    var correctCount = 0
        private set
    var hintsUsed = 0
        private set

    val totalSteps: Int get() = scenario.steps.size
    val currentStepIndex: Int get() = stepIndex

    fun isComplete(): Boolean = stepIndex >= scenario.steps.size

    fun currentStep(): BossStep? = scenario.steps.getOrNull(stepIndex)

    fun currentCommand(): SshCommand? =
        currentStep()?.commandId?.let { CommandBank.findById(it) }

    fun currentPrompt(): String {
        val step = currentStep() ?: return ""
        if (step.promptOverride.isNotEmpty()) return step.promptOverride
        return currentCommand()?.description ?: ""
    }

    fun hint(): String {
        val cmd = currentCommand() ?: return ""
        hintsUsed++
        val tokens = AnswerChecker.nonPlaceholderTokens(cmd.command)
        return "Starts with '${tokens.firstOrNull() ?: ""}' — Expected: ${cmd.command}"
    }

    fun submit(userInput: String): AnswerResult {
        val cmd = currentCommand()
            ?: return AnswerResult(AnswerStatus.WRONG, 0, "No step loaded", streak)
        val correct = AnswerChecker.check(cmd, userInput)
        return if (correct) {
            streak++
            val pts = POINTS_BOSS_STEP + min(streak, MAX_STREAK_FOR_BONUS) * STREAK_BONUS_PER_CORRECT
            score += pts
            correctCount++
            stepIndex++
            AnswerResult(AnswerStatus.CORRECT, pts, "", streak)
        } else {
            // Boss: no lives lost, no streak reset on a different step (but same step retry)
            val h = AnswerChecker.hint(cmd, userInput)
            AnswerResult(AnswerStatus.WRONG, 0, h, streak)
        }
    }
}

// ─── GameEngine facade ────────────────────────────────────────────────────────

/**
 * Stateless factory / helper. The actual per-session state lives in
 * [LearnSession], [ChallengeSession], and [BossSession].
 */
object GameEngine {

    fun createLearnSession(
        category: Category? = null,
        level: Int? = null
    ): LearnSession {
        val commands = when {
            category != null && level != null ->
                CommandBank.byCategoryAndLevel(category, level)
            category != null ->
                CommandBank.byCategory(category)
            level != null ->
                CommandBank.byLevel(level)
            else ->
                CommandBank.all
        }.shuffled()
        return LearnSession(commands)
    }

    fun createChallengeSession(
        category: Category? = null,
        level: Int? = null,
        lives: Int = 3
    ): ChallengeSession {
        val commands = when {
            category != null && level != null ->
                CommandBank.byCategoryAndLevel(category, level)
            category != null ->
                CommandBank.byCategory(category)
            level != null ->
                CommandBank.byLevel(level)
            else ->
                CommandBank.all
        }.shuffled()
        return ChallengeSession(commands, lives)
    }

    fun createBossSession(scenarioIndex: Int): BossSession {
        val scenario = BossScenarios.all.getOrElse(scenarioIndex) {
            BossScenarios.all.first()
        }
        return BossSession(scenario)
    }

    /** Quick utility used by UI to show the filter counts. */
    fun countCommands(category: Category? = null, level: Int? = null): Int =
        when {
            category != null && level != null ->
                CommandBank.byCategoryAndLevel(category, level).size
            category != null ->
                CommandBank.byCategory(category).size
            level != null ->
                CommandBank.byLevel(level).size
            else ->
                CommandBank.all.size
        }
}
