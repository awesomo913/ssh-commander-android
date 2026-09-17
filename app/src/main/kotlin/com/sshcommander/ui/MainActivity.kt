package com.sshcommander.ui

import android.graphics.Color
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.sshcommander.R
import com.sshcommander.data.Category
import com.sshcommander.data.CommandBank
import com.sshcommander.game.AnswerStatus
import com.sshcommander.game.BossScenarios
import com.sshcommander.game.BossSession
import com.sshcommander.game.ChallengeSession
import com.sshcommander.game.GameEngine
import com.sshcommander.game.LearnSession

// ─── Game mode enum ───────────────────────────────────────────────────────────

private enum class GameMode { LEARN, CHALLENGE, BOSS }

// ─── Activity ─────────────────────────────────────────────────────────────────

class MainActivity : AppCompatActivity() {

    // ── Screen containers (each is a top-level view in activity_main.xml) ──
    private lateinit var screenMenu: View
    private lateinit var screenLearnSetup: View
    private lateinit var screenChallengeSetup: View
    private lateinit var screenBossSetup: View
    private lateinit var screenGameplay: View
    private lateinit var screenResult: View

    // ── Current active sessions (at most one non-null at a time) ──────────
    private var learnSession: LearnSession? = null
    private var challengeSession: ChallengeSession? = null
    private var bossSession: BossSession? = null
    private var activeMode: GameMode = GameMode.LEARN

    // ── Gameplay view references (inside screenGameplay) ──────────────────
    private lateinit var tvCardCounter: TextView
    private lateinit var tvScore: TextView
    private lateinit var tvStreak: TextView
    private lateinit var tvLives: TextView
    private lateinit var tvCategoryBadge: TextView
    private lateinit var tvBossStory: TextView
    private lateinit var tvPrompt: TextView
    private lateinit var tvFeedback: TextView
    private lateinit var tvHintText: TextView
    private lateinit var etAnswer: com.google.android.material.textfield.TextInputEditText
    private lateinit var btnSubmit: android.widget.Button
    private lateinit var btnSkip: android.widget.Button
    private lateinit var btnHint: android.widget.Button
    private lateinit var btnQuit: android.widget.Button

    // ── Result view references ────────────────────────────────────────────
    private lateinit var tvResultTitle: TextView
    private lateinit var tvResultMode: TextView
    private lateinit var tvResultScore: TextView
    private lateinit var tvResultCorrect: TextView
    private lateinit var tvResultWrong: TextView
    private lateinit var tvResultAccuracy: TextView
    private lateinit var tvResultHints: TextView
    private lateinit var rowResultHints: View

    // ─────────────────────────────────────────────────────────────────────
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        bindScreenContainers()
        bindGameplayViews()
        bindResultViews()
        wireMenuButtons()
        wireLearnSetup()
        wireChallengeSetup()
        wireBossSetup()
        wireGameplayButtons()
        wireResultButtons()
        populateBossScenarios()

        showScreen(screenMenu)
    }

    // ─── Back press: navigate up through screens ──────────────────────────
    @Deprecated("Using onBackPressed for compatibility")
    override fun onBackPressed() {
        when {
            screenGameplay.visibility == View.VISIBLE -> {
                // Treat back as Quit
                onQuit()
            }
            screenLearnSetup.visibility == View.VISIBLE ||
            screenChallengeSetup.visibility == View.VISIBLE ||
            screenBossSetup.visibility == View.VISIBLE ||
            screenResult.visibility == View.VISIBLE -> {
                showScreen(screenMenu)
            }
            else -> super.onBackPressed()
        }
    }

    // ─── View binding ─────────────────────────────────────────────────────

    private fun bindScreenContainers() {
        screenMenu = findViewById(R.id.screenMenu)
        screenLearnSetup = findViewById(R.id.screenLearnSetup)
        screenChallengeSetup = findViewById(R.id.screenChallengeSetup)
        screenBossSetup = findViewById(R.id.screenBossSetup)
        screenGameplay = findViewById(R.id.screenGameplay)
        screenResult = findViewById(R.id.screenResult)
    }

    private fun bindGameplayViews() {
        tvCardCounter = screenGameplay.findViewById(R.id.tvCardCounter)
        tvScore = screenGameplay.findViewById(R.id.tvScore)
        tvStreak = screenGameplay.findViewById(R.id.tvStreak)
        tvLives = screenGameplay.findViewById(R.id.tvLives)
        tvCategoryBadge = screenGameplay.findViewById(R.id.tvCategoryBadge)
        tvBossStory = screenGameplay.findViewById(R.id.tvBossStory)
        tvPrompt = screenGameplay.findViewById(R.id.tvPrompt)
        tvFeedback = screenGameplay.findViewById(R.id.tvFeedback)
        tvHintText = screenGameplay.findViewById(R.id.tvHintText)
        etAnswer = screenGameplay.findViewById(R.id.etAnswer)
        btnSubmit = screenGameplay.findViewById(R.id.btnSubmit)
        btnSkip = screenGameplay.findViewById(R.id.btnSkip)
        btnHint = screenGameplay.findViewById(R.id.btnHint)
        btnQuit = screenGameplay.findViewById(R.id.btnQuit)
    }

    private fun bindResultViews() {
        tvResultTitle = screenResult.findViewById(R.id.tvResultTitle)
        tvResultMode = screenResult.findViewById(R.id.tvResultMode)
        tvResultScore = screenResult.findViewById(R.id.tvResultScore)
        tvResultCorrect = screenResult.findViewById(R.id.tvResultCorrect)
        tvResultWrong = screenResult.findViewById(R.id.tvResultWrong)
        tvResultAccuracy = screenResult.findViewById(R.id.tvResultAccuracy)
        tvResultHints = screenResult.findViewById(R.id.tvResultHints)
        rowResultHints = screenResult.findViewById(R.id.rowResultHints)
    }

    // ─── Button wiring ────────────────────────────────────────────────────

    private fun wireMenuButtons() {
        screenMenu.findViewById<TextView>(R.id.tvCommandCount).text =
            getString(R.string.commands_count, CommandBank.all.size)

        screenMenu.findViewById<android.widget.Button>(R.id.btnLearn).setOnClickListener {
            showScreen(screenLearnSetup)
        }
        screenMenu.findViewById<android.widget.Button>(R.id.btnChallenge).setOnClickListener {
            showScreen(screenChallengeSetup)
        }
        screenMenu.findViewById<android.widget.Button>(R.id.btnBoss).setOnClickListener {
            showScreen(screenBossSetup)
        }
    }

    private fun wireLearnSetup() {
        screenLearnSetup.findViewById<android.widget.Button>(R.id.btnLearnBack).setOnClickListener {
            showScreen(screenMenu)
        }
        screenLearnSetup.findViewById<android.widget.Button>(R.id.btnLearnStart).setOnClickListener {
            startLearn()
        }
    }

    private fun wireChallengeSetup() {
        screenChallengeSetup.findViewById<android.widget.Button>(R.id.btnChallengeBack)
            .setOnClickListener { showScreen(screenMenu) }
        screenChallengeSetup.findViewById<android.widget.Button>(R.id.btnChallengeStart)
            .setOnClickListener { startChallenge() }
    }

    private fun wireBossSetup() {
        screenBossSetup.findViewById<android.widget.Button>(R.id.btnBossBack)
            .setOnClickListener { showScreen(screenMenu) }
        screenBossSetup.findViewById<android.widget.Button>(R.id.btnBossStart)
            .setOnClickListener { startBoss() }
    }

    private fun wireGameplayButtons() {
        btnSubmit.setOnClickListener { onSubmit() }
        btnSkip.setOnClickListener { onSkip() }
        btnHint.setOnClickListener { onHint() }
        btnQuit.setOnClickListener { onQuit() }

        // Submit on keyboard "Done" / Enter
        etAnswer.setOnEditorActionListener { _, actionId, event ->
            if (actionId == EditorInfo.IME_ACTION_DONE ||
                (event?.keyCode == KeyEvent.KEYCODE_ENTER && event.action == KeyEvent.ACTION_DOWN)
            ) {
                onSubmit()
                true
            } else false
        }
    }

    private fun wireResultButtons() {
        screenResult.findViewById<android.widget.Button>(R.id.btnPlayAgain).setOnClickListener {
            when (activeMode) {
                GameMode.LEARN -> showScreen(screenLearnSetup)
                GameMode.CHALLENGE -> showScreen(screenChallengeSetup)
                GameMode.BOSS -> showScreen(screenBossSetup)
            }
        }
        screenResult.findViewById<android.widget.Button>(R.id.btnResultMenu).setOnClickListener {
            showScreen(screenMenu)
        }
    }

    // ─── Boss setup: build RadioButtons for each scenario ─────────────────

    private fun populateBossScenarios() {
        val rg = screenBossSetup.findViewById<RadioGroup>(R.id.rgBossScenario)
        rg.removeAllViews()
        BossScenarios.all.forEachIndexed { idx, scenario ->
            val rb = RadioButton(this).apply {
                id = View.generateViewId()
                tag = idx
                text = "${scenario.title}\n(${scenario.steps.size} steps)"
                textSize = 14f
                setTextColor(ContextCompat.getColor(context, R.color.fg))
                typeface = android.graphics.Typeface.MONOSPACE
                buttonTintList = android.content.res.ColorStateList.valueOf(
                    ContextCompat.getColor(context, R.color.red)
                )
                isChecked = idx == 0
                val pad = resources.getDimensionPixelSize(R.dimen.radio_padding)
                setPadding(pad, 12, pad, 12)
                layoutParams = RadioGroup.LayoutParams(
                    RadioGroup.LayoutParams.MATCH_PARENT,
                    RadioGroup.LayoutParams.WRAP_CONTENT
                ).apply { bottomMargin = 4 }
                setBackgroundColor(ContextCompat.getColor(context, R.color.bg2))
            }
            rg.addView(rb)
        }
    }

    // ─── Start sessions ───────────────────────────────────────────────────

    private fun startLearn() {
        activeMode = GameMode.LEARN
        val category = selectedLearnCategory()
        val level = selectedLearnLevel()
        learnSession = GameEngine.createLearnSession(category, level)
        challengeSession = null
        bossSession = null

        // Mode-specific button visibility
        btnSkip.visibility = View.VISIBLE
        btnHint.visibility = View.GONE
        tvLives.visibility = View.GONE

        showScreen(screenGameplay)
        renderLearnCard()
    }

    private fun startChallenge() {
        activeMode = GameMode.CHALLENGE
        val lives = selectedChallengeLives()
        val category = selectedChallengeCategory()
        challengeSession = GameEngine.createChallengeSession(category = category, lives = lives)
        learnSession = null
        bossSession = null

        btnSkip.visibility = View.GONE
        btnHint.visibility = View.GONE
        tvLives.visibility = View.VISIBLE

        showScreen(screenGameplay)
        renderChallengeCard()
    }

    private fun startBoss() {
        activeMode = GameMode.BOSS
        val scenarioIdx = selectedBossScenario()
        bossSession = GameEngine.createBossSession(scenarioIdx)
        learnSession = null
        challengeSession = null

        btnSkip.visibility = View.GONE
        btnHint.visibility = View.VISIBLE
        tvLives.visibility = View.GONE

        showScreen(screenGameplay)
        renderBossStep(firstStep = true)
    }

    // ─── Gameplay actions ─────────────────────────────────────────────────

    private fun onSubmit() {
        val input = etAnswer.text?.toString() ?: ""
        when (activeMode) {
            GameMode.LEARN -> {
                val session = learnSession ?: return
                val result = session.submit(input)
                tvFeedback.text = if (result.status == AnswerStatus.CORRECT)
                    "✓  Correct! +${result.pointsEarned} pts"
                else
                    "✗  ${result.hint}"
                tvFeedback.setTextColor(
                    ContextCompat.getColor(this,
                        if (result.status == AnswerStatus.CORRECT) R.color.green else R.color.red)
                )
                updateLearnHeader()
                if (result.status == AnswerStatus.CORRECT) {
                    etAnswer.postDelayed({
                        if (session.hasNext()) {
                            etAnswer.text?.clear()
                            tvFeedback.text = ""
                            renderLearnCard()
                        } else {
                            showLearnResult()
                        }
                    }, 800)
                }
            }

            GameMode.CHALLENGE -> {
                val session = challengeSession ?: return
                val result = session.submit(input)
                tvFeedback.text = if (result.status == AnswerStatus.CORRECT)
                    "✓  Correct! +${result.pointsEarned} pts"
                else
                    "✗  ${result.hint}"
                tvFeedback.setTextColor(
                    ContextCompat.getColor(this,
                        if (result.status == AnswerStatus.CORRECT) R.color.green else R.color.red)
                )
                updateChallengeHeader()
                when {
                    session.isGameOver() -> {
                        etAnswer.postDelayed({ showChallengeResult(defeated = true) }, 700)
                    }
                    session.isComplete() -> {
                        etAnswer.postDelayed({ showChallengeResult(defeated = false) }, 700)
                    }
                    result.status == AnswerStatus.CORRECT -> {
                        etAnswer.postDelayed({
                            etAnswer.text?.clear()
                            tvFeedback.text = ""
                            renderChallengeCard()
                        }, 700)
                    }
                }
            }

            GameMode.BOSS -> {
                val session = bossSession ?: return
                val result = session.submit(input)
                tvFeedback.text = if (result.status == AnswerStatus.CORRECT)
                    "✓  Step cleared! +${result.pointsEarned} pts"
                else
                    "✗  ${result.hint}"
                tvFeedback.setTextColor(
                    ContextCompat.getColor(this,
                        if (result.status == AnswerStatus.CORRECT) R.color.green else R.color.red)
                )
                updateBossHeader()
                if (result.status == AnswerStatus.CORRECT) {
                    tvHintText.visibility = View.GONE
                    if (session.isComplete()) {
                        etAnswer.postDelayed({ showBossResult(defeated = false) }, 900)
                    } else {
                        etAnswer.postDelayed({
                            etAnswer.text?.clear()
                            tvFeedback.text = ""
                            renderBossStep(firstStep = false)
                        }, 900)
                    }
                }
            }
        }
        hideKeyboard()
    }

    private fun onSkip() {
        val session = learnSession ?: return
        session.skip()
        etAnswer.text?.clear()
        tvFeedback.text = ""
        if (session.hasNext()) {
            renderLearnCard()
        } else {
            showLearnResult()
        }
        hideKeyboard()
    }

    private fun onHint() {
        val session = bossSession ?: return
        val hint = session.hint()
        tvHintText.text = hint
        tvHintText.visibility = View.VISIBLE
    }

    private fun onQuit() {
        when (activeMode) {
            GameMode.LEARN -> showLearnResult()
            GameMode.CHALLENGE -> showChallengeResult(defeated = false)
            GameMode.BOSS -> showBossResult(defeated = true)
        }
    }

    // ─── Card rendering ───────────────────────────────────────────────────

    private fun renderLearnCard() {
        val session = learnSession ?: return
        val cmd = session.currentCard() ?: return
        tvCardCounter.text = "Card ${session.currentIndex + 1} / ${session.totalCards}"
        tvCategoryBadge.text = cmd.category.displayName
        applyCategoryBadgeColor(cmd.category)
        tvPrompt.text = cmd.description
        tvBossStory.visibility = View.GONE
        tvHintText.visibility = View.GONE
        updateLearnHeader()
    }

    private fun renderChallengeCard() {
        val session = challengeSession ?: return
        val cmd = session.currentCard() ?: return
        tvCardCounter.text = "Card ${session.currentIndex + 1} / ${session.totalCards}"
        tvCategoryBadge.text = cmd.category.displayName
        applyCategoryBadgeColor(cmd.category)
        tvPrompt.text = cmd.description
        tvBossStory.visibility = View.GONE
        tvHintText.visibility = View.GONE
        updateChallengeHeader()
    }

    private fun renderBossStep(firstStep: Boolean) {
        val session = bossSession ?: return
        tvCardCounter.text = "Step ${session.currentStepIndex + 1} / ${session.totalSteps}"
        tvPrompt.text = session.currentPrompt()
        val cmd = session.currentCommand()
        if (cmd != null) {
            tvCategoryBadge.text = cmd.category.displayName
            applyCategoryBadgeColor(cmd.category)
        }
        if (firstStep) {
            tvBossStory.text = session.scenario.story
            tvBossStory.visibility = View.VISIBLE
        } else {
            tvBossStory.visibility = View.GONE
        }
        updateBossHeader()
    }

    // ─── Header updates ───────────────────────────────────────────────────

    private fun updateLearnHeader() {
        val s = learnSession ?: return
        tvScore.text = "${s.score} pts"
        tvStreak.text = if (s.streak > 0) "🔥${s.streak}" else "—"
    }

    private fun updateChallengeHeader() {
        val s = challengeSession ?: return
        tvScore.text = "${s.score} pts"
        tvStreak.text = if (s.streak > 0) "🔥${s.streak}" else "—"
        tvLives.text = "❤".repeat(s.lives) + "♡".repeat(s.livesTotal - s.lives)
    }

    private fun updateBossHeader() {
        val s = bossSession ?: return
        tvScore.text = "${s.score} pts"
        tvStreak.text = if (s.streak > 0) "🔥${s.streak}" else "—"
    }

    // ─── Category badge colors ────────────────────────────────────────────

    private fun applyCategoryBadgeColor(category: Category) {
        val colorRes = when (category) {
            Category.CONNECT -> R.color.blue
            Category.FILES -> R.color.green
            Category.TUNNELS -> R.color.purple
            Category.MANAGE -> R.color.yellow
            Category.HARDEN -> R.color.red
        }
        tvCategoryBadge.setTextColor(ContextCompat.getColor(this, colorRes))
    }

    // ─── Result screens ───────────────────────────────────────────────────

    private fun showLearnResult() {
        val s = learnSession ?: return
        tvResultTitle.text = "COMPLETE"
        tvResultTitle.setTextColor(ContextCompat.getColor(this, R.color.green))
        tvResultMode.text = "LEARN MODE"
        tvResultScore.text = s.score.toString()
        tvResultCorrect.text = s.correctCount.toString()
        tvResultWrong.text = s.wrongCount.toString()
        tvResultAccuracy.text = "%.0f%%".format(s.accuracy() * 100)
        rowResultHints.visibility = View.GONE
        showScreen(screenResult)
    }

    private fun showChallengeResult(defeated: Boolean) {
        val s = challengeSession ?: return
        tvResultTitle.text = if (defeated) "GAME OVER" else "COMPLETE"
        tvResultTitle.setTextColor(
            ContextCompat.getColor(this, if (defeated) R.color.red else R.color.green)
        )
        tvResultMode.text = "CHALLENGE MODE"
        tvResultScore.text = s.score.toString()
        tvResultCorrect.text = s.correctCount.toString()
        tvResultWrong.text = s.wrongCount.toString()
        tvResultAccuracy.text = "%.0f%%".format(s.accuracy() * 100)
        rowResultHints.visibility = View.GONE
        showScreen(screenResult)
    }

    private fun showBossResult(defeated: Boolean) {
        val s = bossSession ?: return
        tvResultTitle.text = if (!defeated) "BOSS DEFEATED!" else "MISSION FAILED"
        tvResultTitle.setTextColor(
            ContextCompat.getColor(this, if (!defeated) R.color.green else R.color.red)
        )
        tvResultMode.text = "BOSS MODE — ${s.scenario.title}"
        tvResultScore.text = s.score.toString()
        tvResultCorrect.text = s.correctCount.toString()
        tvResultWrong.text = "${s.scenario.steps.size - s.currentStepIndex} remaining"
        tvResultAccuracy.text = "${s.currentStepIndex} / ${s.totalSteps} steps"
        rowResultHints.visibility = View.VISIBLE
        tvResultHints.text = s.hintsUsed.toString()
        showScreen(screenResult)
    }

    // ─── Setup option readers ─────────────────────────────────────────────

    private fun selectedLearnCategory(): Category? {
        return when (screenLearnSetup.findViewById<RadioGroup>(R.id.rgLearnCategory)
            .checkedRadioButtonId) {
            R.id.rbLearnCatConnect -> Category.CONNECT
            R.id.rbLearnCatFiles -> Category.FILES
            R.id.rbLearnCatTunnels -> Category.TUNNELS
            R.id.rbLearnCatManage -> Category.MANAGE
            R.id.rbLearnCatHarden -> Category.HARDEN
            else -> null
        }
    }

    private fun selectedLearnLevel(): Int? {
        return when (screenLearnSetup.findViewById<RadioGroup>(R.id.rgLearnLevel)
            .checkedRadioButtonId) {
            R.id.rbLearnLvl1 -> 1
            R.id.rbLearnLvl2 -> 2
            R.id.rbLearnLvl3 -> 3
            else -> null
        }
    }

    private fun selectedChallengeLives(): Int {
        return when (screenChallengeSetup.findViewById<RadioGroup>(R.id.rgChallengeLives)
            .checkedRadioButtonId) {
            R.id.rbLives1 -> 1
            R.id.rbLives5 -> 5
            else -> 3
        }
    }

    private fun selectedChallengeCategory(): Category? {
        return when (screenChallengeSetup.findViewById<RadioGroup>(R.id.rgChallengeCategory)
            .checkedRadioButtonId) {
            R.id.rbChallCatConnect -> Category.CONNECT
            R.id.rbChallCatFiles -> Category.FILES
            R.id.rbChallCatTunnels -> Category.TUNNELS
            R.id.rbChallCatManage -> Category.MANAGE
            R.id.rbChallCatHarden -> Category.HARDEN
            else -> null
        }
    }

    private fun selectedBossScenario(): Int {
        val rg = screenBossSetup.findViewById<RadioGroup>(R.id.rgBossScenario)
        val selectedId = rg.checkedRadioButtonId
        val rb = rg.findViewById<RadioButton>(selectedId)
        return rb?.tag as? Int ?: 0
    }

    // ─── Screen navigation ────────────────────────────────────────────────

    private val allScreens: List<() -> View> by lazy {
        listOf(
            { screenMenu },
            { screenLearnSetup },
            { screenChallengeSetup },
            { screenBossSetup },
            { screenGameplay },
            { screenResult }
        )
    }

    private fun showScreen(target: View) {
        listOf(screenMenu, screenLearnSetup, screenChallengeSetup,
               screenBossSetup, screenGameplay, screenResult)
            .forEach { it.visibility = if (it === target) View.VISIBLE else View.GONE }
        // Focus input when gameplay starts
        if (target === screenGameplay) {
            etAnswer.requestFocus()
            etAnswer.text?.clear()
            tvFeedback.text = ""
        }
    }

    // ─── Keyboard helper ──────────────────────────────────────────────────

    private fun hideKeyboard() {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        currentFocus?.let { imm.hideSoftInputFromWindow(it.windowToken, 0) }
    }
}
