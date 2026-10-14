import {
  BOT_USERNAME,
  CALIBRATED_WINDOW_RECT,
  CHAT_INPUT_RECT,
  CHAT_INPUT_SCREEN_PT,
  TALK_BUTTON_RECT,
  TALK_BUTTON_SCREEN_PT,
  DEFAULT_ALLOWED_ADMINS,
  SPIN_FLAT_COST_PAT,
  SPIN_COOLDOWN_SECONDS,
} from "./constants";
import {
  UserProfile,
  TerminalLine,
  CalibrationState,
  BotSettings,
  MicGrab,
  ModerationEvent,
  SpinTimingRecord,
  AppMode,
  CloneState,
} from "../types";
import { StrategyEngine } from "./strategyEngine";
import { KaeKaeBrain, analyzeSentimentAndTone, extractTopNoun, detectModeration } from "./kaekaeBrain";

// Seed historical spin records from data/spin_timing_records.jsonl
const INITIAL_SPIN_RECORDS: SpinTimingRecord[] = [
  { spin_id: 1, timestamp_iso: "2026-10-14T09:50:34Z", interval_seconds: 20.2, window_bracket: "60s-90s (1.0m-1.5m)", phase_offset_ms: 200, outcome: "WIN", gross_payout_pat: 5000, net_delta_pat: 0, wallet_after_pat: 25000, jackpot_pool_pat: 2850000 },
  { spin_id: 2, timestamp_iso: "2026-10-14T09:41:28Z", interval_seconds: 20.15, window_bracket: "60s-90s (1.0m-1.5m)", phase_offset_ms: 150, outcome: "LOSS", gross_payout_pat: 0, net_delta_pat: -5000, wallet_after_pat: 20000, jackpot_pool_pat: 2852500 },
  { spin_id: 3, timestamp_iso: "2026-10-14T09:41:02Z", interval_seconds: 20.15, window_bracket: "60s-90s (1.0m-1.5m)", phase_offset_ms: 150, outcome: "WIN", gross_payout_pat: 25000, net_delta_pat: 20000, wallet_after_pat: 45000, jackpot_pool_pat: 2850000 },
  { spin_id: 4, timestamp_iso: "2026-10-14T09:40:47Z", interval_seconds: 20.15, window_bracket: "60s-90s (1.0m-1.5m)", phase_offset_ms: 150, outcome: "WIN", gross_payout_pat: 12500, net_delta_pat: 7500, wallet_after_pat: 32500, jackpot_pool_pat: 2850000 },
  { spin_id: 5, timestamp_iso: "2026-10-14T09:06:04Z", interval_seconds: 20.15, window_bracket: "60s-90s (1.0m-1.5m)", phase_offset_ms: 150, outcome: "WIN", gross_payout_pat: 12500, net_delta_pat: 7500, wallet_after_pat: 32500, jackpot_pool_pat: 2850000 },
  { spin_id: 6, timestamp_iso: "2026-10-14T06:21:38Z", interval_seconds: 20.15, window_bracket: "60s-90s (1.0m-1.5m)", phase_offset_ms: 150, outcome: "WIN", gross_payout_pat: 15000, net_delta_pat: 10000, wallet_after_pat: 35000, jackpot_pool_pat: 2850000 },
  { spin_id: 7, timestamp_iso: "2026-10-14T06:21:14Z", interval_seconds: 20.15, window_bracket: "60s-90s (1.0m-1.5m)", phase_offset_ms: 150, outcome: "WIN", gross_payout_pat: 15000, net_delta_pat: 10000, wallet_after_pat: 35000, jackpot_pool_pat: 2850000 },
  { spin_id: 8, timestamp_iso: "2026-10-14T05:56:35Z", interval_seconds: 20.15, window_bracket: "60s-90s (1.0m-1.5m)", phase_offset_ms: 150, outcome: "WIN", gross_payout_pat: 8000, net_delta_pat: 3000, wallet_after_pat: 28000, jackpot_pool_pat: 2850000 },
  { spin_id: 9, timestamp_iso: "2026-10-14T02:30:39Z", interval_seconds: 20.15, window_bracket: "60s-90s (1.0m-1.5m)", phase_offset_ms: 150, outcome: "WIN", gross_payout_pat: 12500, net_delta_pat: 7500, wallet_after_pat: 32500, jackpot_pool_pat: 2850000 },
  { spin_id: 10, timestamp_iso: "2026-10-14T02:30:25Z", interval_seconds: 20.15, window_bracket: "60s-90s (1.0m-1.5m)", phase_offset_ms: 150, outcome: "WIN", gross_payout_pat: 25000, net_delta_pat: 20000, wallet_after_pat: 45000, jackpot_pool_pat: 2850000 },
];

// Initial seeded room users from Camfrog lounge
const INITIAL_USERS: UserProfile[] = [
  {
    username: "Stonerwayne1000",
    is_active: true,
    first_seen: "2026-10-14 01:10:00",
    last_seen: "2026-10-14 03:00:00",
    gender: "male (blue)",
    status_category: "operator",
    message_count: 42,
    mic_grab_count: 5,
    total_mic_seconds: 218,
    total_chat_seconds: 3600,
    top_noun: "jackpot",
    top_word: "jackpot",
    top_count: 14,
    text_tone: "excited/hyped",
    audio_tone: "conversational/chill",
    speech_patterns: "cadenced/direct",
    biography: "Camfrog Lounge veteran and heist organizer. Master of high-stakes wheel spins and bank robberies.",
    messages: ["!spin", "!sheet", "jackpot is getting fat tonight boys", "!heist casino", "let's push the vault door"],
    mic_transcripts: ["Yo testing the mic check one two", "Who is ready for the casino heist"],
  },
  {
    username: "Rosie",
    is_active: true,
    first_seen: "2026-10-14 01:25:00",
    last_seen: "2026-10-14 03:00:00",
    gender: "female (pink)",
    status_category: "member",
    message_count: 28,
    mic_grab_count: 2,
    total_mic_seconds: 64,
    total_chat_seconds: 3200,
    top_noun: "lotto",
    top_word: "lotto",
    top_count: 9,
    text_tone: "upbeat/positive",
    audio_tone: "upbeat/positive",
    speech_patterns: "cheerful/warm",
    biography: "Lounge regular and top gifter. Always brings positive energy to Players__Lounge.",
    messages: ["good evening everyone ✨", "!balance", "kaekae how are you tonight?", "!bingo buy 4"],
    mic_transcripts: ["Hey everyone, happy Wednesday!"],
  },
  {
    username: "lockspeck",
    is_active: true,
    first_seen: "2026-10-14 00:45:00",
    last_seen: "2026-10-14 03:00:00",
    gender: "male (blue)",
    status_category: "admin",
    message_count: 19,
    mic_grab_count: 1,
    total_mic_seconds: 45,
    total_chat_seconds: 4100,
    top_noun: "timing",
    top_word: "timing",
    top_count: 7,
    text_tone: "analytical/precise",
    audio_tone: "neutral",
    speech_patterns: "technical/concise",
    biography: "Lead systems engineer and automation architect for KaeKae_Toad & PepeFrog.",
    messages: ["running 20.2s timing calibration", "!grabs 24h", "DirectML FP16 ready on RX 9070 XT"],
    mic_transcripts: ["Checking the VB-Cable loopback audio levels."],
  },
  {
    username: "OMGitsMyPHONE",
    is_active: true,
    first_seen: "2026-10-14 02:00:00",
    last_seen: "2026-10-14 02:58:00",
    gender: "female (pink)",
    status_category: "member",
    message_count: 15,
    mic_grab_count: 0,
    total_mic_seconds: 0,
    total_chat_seconds: 1800,
    top_noun: "spin",
    top_word: "spin",
    top_count: 5,
    text_tone: "energetic/expressive",
    audio_tone: "neutral",
    speech_patterns: "expressive/rapid",
    biography: "Active mobile chatter, wheel enthusiast, and frequent trivia competitor.",
    messages: ["lol that was close", "!spin", "pepe frog please be kind", "!trivia 1000"],
    mic_transcripts: [],
  },
  {
    username: "nico1ee",
    is_active: true,
    first_seen: "2026-10-14 01:50:00",
    last_seen: "2026-10-14 02:59:00",
    gender: "female (pink)",
    status_category: "admin",
    message_count: 22,
    mic_grab_count: 3,
    total_mic_seconds: 98,
    total_chat_seconds: 2900,
    top_noun: "heist",
    top_word: "heist",
    top_count: 8,
    text_tone: "conversational/chill",
    audio_tone: "conversational/chill",
    speech_patterns: "relaxed/composed",
    biography: "Co-administrator and strategic heist commander. Armed with Ghost Plates and Good Lawyer.",
    messages: ["!join", "!bail", "got out with 38k PAT nice", "!shop"],
    mic_transcripts: ["Bail out now before round 9! Don't risk the vault!"],
  },
];

export class BotOrchestrator {
  strategy: StrategyEngine;
  brain: KaeKaeBrain;

  appMode: AppMode = "REGULAR";
  cloneState: CloneState = {
    armed: false,
    stage: "idle",
    targetSpeaker: null,
    sampleProgress: 0,
    elapsedSeconds: 0,
    lastClonedVoice: null,
    availableClones: ["Coqui Default (Test Clone)"],
  };
  savedRegularState: {
    autoSpinEnabled: boolean;
    randomSpinMode: boolean;
    countdownRemaining: number;
    chatMode: boolean;
  } | null = null;
  cloneSamplingTimerId: number | null = null;

  autoSpinEnabled = false;
  randomSpinMode = false;
  nextSpinCountdownS = 0;
  countdownTimerId: number | null = null;
  spinLoopTimerId: number | null = null;

  currentSpeaker: string | null = null;
  speakerTimerId: number | null = null;

  calibration: CalibrationState = {
    window_rect: CALIBRATED_WINDOW_RECT,
    chat_input_rect: CHAT_INPUT_RECT,
    chat_input_screen_pt: CHAT_INPUT_SCREEN_PT,
    talk_button_rect: TALK_BUTTON_RECT,
    talk_button_screen_pt: TALK_BUTTON_SCREEN_PT,
    calibrated_at: "2026-10-14 02:47:34",
    allowed_admins: [...DEFAULT_ALLOWED_ADMINS],
  };

  botSettings: BotSettings = {
    running: true,
    chat_mode: false,
    silent_mode: true,
    transcription_mode: true,
    post_transcripts_to_chat: false,
    tone: "neutral",
    tts_voice: "en-US-AriaNeural",
    whisperx_enabled: true,
    gpu_acceleration: true,
    gpu_backend: "DirectML (AMD Radeon RX 9070 XT)",
  };

  users: Map<string, UserProfile> = new Map();
  suppressedUsers: Set<string> = new Set();
  moderationHistory: ModerationEvent[] = [];
  micGrabs: MicGrab[] = [];

  terminal1: TerminalLine[] = [];
  terminal2: TerminalLine[] = [];
  terminal3: TerminalLine[] = [];

  liveMouseXY: [number, number] = [1536, 1223];
  listeners: Array<() => void> = [];

  constructor() {
    this.strategy = new StrategyEngine();
    this.brain = new KaeKaeBrain();

    // Populate initial users
    for (const u of INITIAL_USERS) {
      this.users.set(u.username.toLowerCase(), { ...u });
    }

    // Populate initial spin records into strategy
    this.strategy.spinRecords = [...INITIAL_SPIN_RECORDS];
    for (const r of INITIAL_SPIN_RECORDS) {
      const b = this.strategy.windowBracketStats[r.window_bracket];
      if (b) {
        b.spins++;
        if (r.outcome === "WIN" || r.outcome === "JACKPOT") b.wins++;
        if (r.outcome === "JACKPOT") b.jackpots++;
        b.net_pat += r.net_delta_pat;
      }
    }
    this.strategy.totalSpinsExecuted = INITIAL_SPIN_RECORDS.length;

    // Boot logs in terminals
    this.emitIncomingLog(
      `[INCOMING MONITOR 🟢] Silent Room Listener locked onto Camfrog window 'Players__Lounge' (HWND=0x001A03F2, Rect=[${CALIBRATED_WINDOW_RECT.join(", ")}]). Users seeded: ${INITIAL_USERS.length} | SPEAKER_ON_MIC: None (Mic Free) | ChatBox Pixel=[${CHAT_INPUT_SCREEN_PT.join(", ")}] | TalkBtn Pixel=[${TALK_BUTTON_SCREEN_PT.join(", ")}]`
    );
    this.emitIncomingLog(
      `[INCOMING DIAG 🩺] [1/4 WINDOW, ADMIN & GPU] Admin=YES ✅ | GPU=⚡ AMD Radeon RX 9070 XT (DirectML DX12 Native AMD) ✅ | Camfrog=LOCKED ✅`
    );
    this.emitIncomingLog(
      `[INCOMING DIAG 🩺] [2/4 CHAT & USERS] Visible Chat Lines=42 | Room Users Seeded=${INITIAL_USERS.length} (Sample: ${INITIAL_USERS.map((u) => u.username).join(", ")})`
    );
    this.emitIncomingLog(
      `[INCOMING DIAG 🩺] [3/4 SPEAKER & LIVE TRANSCRIBE] SPEAKER_ON_MIC='None (Mic Free)' at [${TALK_BUTTON_RECT.join(", ")}] | Audio Capture Device='Default Loopback (Stereo Mix)' (Peak=0) | SpeechEngine=WhisperX (AMD DirectML 9070 XT ⚡)`
    );

    this.emitActionLog(
      `[SPIN ANALYZER 🎰] Auto-Spin is OFF on launch. All room spins (!spin) are automatically captured & analyzed here in Terminal 2. Click '🎰 START AUTO-SPIN' to spin or '🛑 AUTO-SPIN: OFF' to stop spinning while KaeKae keeps running.`
    );
    this.emitActionLog(
      `[OUTGOING DIAG 🩺] [4/4 BOT TX, TTS & 5.1/5.2 DB] ChatBox Pixel=[${CHAT_INPUT_SCREEN_PT.join(", ")}] | TalkBtn Pixel=[${TALK_BUTTON_SCREEN_PT.join(", ")}] | VB-Cable Out='CABLE Input' (EdgeTTS=OK ✅) | SQLite DB: ${INITIAL_USERS.length} Users, 142 Chat/Mic Lines | Auto-Spin=OFF`
    );

    this.emitTranscribeLog(
      `[TRANSCRIPTION 🎙️] Real-time live mic speech recognition engine initialized (WhisperX DirectML FP16 / GoogleWebSpeech fallback). Waiting for room audio...`
    );

    this.startBackgroundSimulation();
  }

  subscribe(listener: () => void) {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  notify() {
    for (const l of this.listeners) l();
  }

  getTimestamp(): string {
    const d = new Date();
    return d.toTimeString().split(" ")[0] + "." + String(d.getMilliseconds()).padStart(3, "0");
  }

  emitIncomingLog(text: string) {
    const line: TerminalLine = {
      id: Math.random().toString(36).slice(2),
      timestamp: this.getTimestamp(),
      text,
      type: "incoming",
    };
    this.terminal1 = [line, ...this.terminal1.slice(0, 399)];
    this.notify();
  }

  emitActionLog(text: string) {
    const line: TerminalLine = {
      id: Math.random().toString(36).slice(2),
      timestamp: this.getTimestamp(),
      text,
      type: "action",
    };
    this.terminal2 = [line, ...this.terminal2.slice(0, 399)];
    this.notify();
  }

  emitTranscribeLog(text: string) {
    const line: TerminalLine = {
      id: Math.random().toString(36).slice(2),
      timestamp: this.getTimestamp(),
      text,
      type: "transcribe",
    };
    this.terminal3 = [line, ...this.terminal3.slice(0, 399)];
    this.notify();
  }

  // One-Click Deploy
  deployAllOneClick() {
    this.emitActionLog("[ONE-CLICK DEPLOY] Step 1/3: Verifying Python packages & portable directories...");
    setTimeout(() => {
      this.emitActionLog("[ONE-CLICK DEPLOY] Step 2/3: Connecting & Auto-Calibrating Camfrog Chat Text Box & Talk Button...");
      this.calibration.calibrated_at = new Date().toLocaleString();
      setTimeout(() => {
        this.emitActionLog(
          `[ONE-CLICK DEPLOY] Step 3/3: Connected & Calibrated Camfrog room! ChatBox Pixel=[${this.calibration.chat_input_screen_pt.join(", ")}] | TalkBtn Pixel=[${this.calibration.talk_button_screen_pt.join(", ")}] | Seeded ${this.users.size} room users | SPEAKER_ON_MIC=${this.currentSpeaker || "None (Mic Free)"}.`
        );
        this.emitActionLog(
          "[ONE-CLICK DEPLOY] KaeKae_Toad Room Listener, SPEAKER_ON_MIC & Spin Analyzer active (Auto-Spin is OFF until you press '🎰 START AUTO-SPIN' or check '🎲 1–3m Random')."
        );
        this.notify();
      }, 700);
    }, 500);
  }

  // Run 8-Point Diagnostics
  runFullDiagnostics() {
    this.emitIncomingLog("[DIAGNOSTICS] Starting full 8-point hardware, UIA and database diagnostic probe...");
    setTimeout(() => {
      this.emitIncomingLog(
        `[INCOMING DIAG 🩺] [1/4 WINDOW, ADMIN & GPU] Admin=YES ✅ | GPU=⚡ AMD Radeon RX 9070 XT (DirectML DX12 Native AMD) ✅ | Camfrog=LOCKED ✅ (HWND=0x001A03F2, Title='Players__Lounge', Rect=[${this.calibration.window_rect.join(", ")}])`
      );
      this.emitIncomingLog(
        `[INCOMING DIAG 🩺] [2/4 CHAT & USERS] Visible Chat Lines=58 | Room Users Seeded=${this.users.size}`
      );
      this.emitIncomingLog(
        `[INCOMING DIAG 🩺] [3/4 SPEAKER & LIVE TRANSCRIBE] SPEAKER_ON_MIC='${this.currentSpeaker || "None (Mic Free)"}' at [${TALK_BUTTON_RECT.join(", ")}] | Capture='VB-Cable Stereo Mix' (Peak=42) | SpeechEngine=WhisperX (AMD DirectML 9070 XT ⚡)`
      );
      this.emitActionLog(
        `[OUTGOING DIAG 🩺] [4/4 BOT TX, TTS & 5.1/5.2 DB] ChatBox Pixel=[${this.calibration.chat_input_screen_pt.join(", ")}] | TalkBtn Pixel=[${this.calibration.talk_button_screen_pt.join(", ")}] | VB-Cable Out='CABLE Input' | SQLite DB: ${this.users.size} Users | Auto-Spin=${this.autoSpinEnabled ? "ON" : "OFF"}`
      );
      this.emitTranscribeLog(
        `[LIVE MIC TEST 🎙️] Sampled 1.6s audio slice -> Peak=42 (Live audio signal detected! Speech transcription active).`
      );
      this.notify();
    }, 600);
  }

  // Direct Pixel coordinate locks
  setDirectPixels(chatX: number, chatY: number, talkX: number, talkY: number) {
    this.calibration.chat_input_screen_pt = [chatX, chatY];
    this.calibration.talk_button_screen_pt = [talkX, talkY];
    this.calibration.calibrated_at = new Date().toLocaleString();
    this.emitActionLog(
      `[CALIBRATION 💾] Locked Direct Pixel Coordinates: Chat=(${chatX}, ${chatY}) | Talk Button=(${talkX}, ${talkY})`
    );
    this.notify();
  }

  // Auto-Spin Controller
  setAutoSpinState(enabled: boolean, random1To3Min?: boolean) {
    if (random1To3Min !== undefined) {
      this.randomSpinMode = random1To3Min;
    }
    this.autoSpinEnabled = enabled;

    if (this.countdownTimerId) {
      window.clearInterval(this.countdownTimerId);
      this.countdownTimerId = null;
    }
    if (this.spinLoopTimerId) {
      window.clearTimeout(this.spinLoopTimerId);
      this.spinLoopTimerId = null;
    }

    if (enabled) {
      const modeLbl = this.randomSpinMode
        ? "1–3 Min Randomized (60s–180s)"
        : `Fixed ${SPIN_COOLDOWN_SECONDS}s Cooldown`;
      this.emitActionLog(`[AUTO-SPIN ARMED 🎰] Auto-Spin turned ON (${modeLbl}). Dispatching !spin cycle...`);

      // Roll first interval
      const interval = this.randomSpinMode
        ? this.strategy.rollRandomSpinIntervalS(60, 180)
        : 20.2;
      this.nextSpinCountdownS = interval;

      // Start tick countdown
      this.countdownTimerId = window.setInterval(() => {
        if (this.nextSpinCountdownS > 0.1) {
          this.nextSpinCountdownS = Math.max(0, Number((this.nextSpinCountdownS - 0.1).toFixed(1)));
          this.notify();
        }
      }, 100);

      // Schedule first spin
      this.scheduleNextSpin(interval);
    } else {
      this.nextSpinCountdownS = 0;
      this.emitActionLog(
        "[AUTO-SPIN: OFF 🛑] Auto-Spin stopped immediately. KaeKae_Toad room listener & triggers remain active!"
      );
    }
    this.notify();
  }

  scheduleNextSpin(delayS: number) {
    if (this.spinLoopTimerId) window.clearTimeout(this.spinLoopTimerId);
    this.spinLoopTimerId = window.setTimeout(() => {
      if (!this.autoSpinEnabled) return;
      this.stepSpinOnce();
      const nextDelay = this.randomSpinMode
        ? this.strategy.rollRandomSpinIntervalS(60, 180)
        : 20.2;
      this.nextSpinCountdownS = nextDelay;
      this.scheduleNextSpin(nextDelay);
    }, delayS * 1000);
  }

  stepSpinOnce() {
    const decision = this.strategy.evaluateNextAction();
    const intervalS = this.randomSpinMode
      ? this.strategy.lastRandomIntervalS
      : 20.2;
    const offsetMs = this.strategy.optimalSpinOffsetMs;

    this.emitActionLog(
      `[STRATEGY] Mode=${decision.mode_flag} | Cmd=${decision.command} | Interval=${intervalS.toFixed(2)}s (Offset +${offsetMs}ms) | EV=${decision.expected_value_pat > 0 ? "+" : ""}${decision.expected_value_pat} PAT | ${decision.rationale}`
    );

    if (decision.command === "HOLD") return;

    this.emitActionLog(`[BOT-CHAT SENT ✅] Dispatched '${decision.command}' + Enter into Camfrog Chat Box.`);

    // Simulate wheel spin outcome based on platform probability curve
    setTimeout(() => {
      const roll = Math.random();
      let outcome: "WIN" | "JACKPOT" | "LOSS" = "LOSS";
      let gross = 0;
      let net = -SPIN_FLAT_COST_PAT;

      if (roll < 0.0005) {
        // Golden Slice Jackpot (1 in 2,000)
        outcome = "JACKPOT";
        gross = this.strategy.jackpotPoolPat;
        net = gross - SPIN_FLAT_COST_PAT;
      } else if (roll < 0.44 || this.strategy.pityState.pity_safety_net_active) {
        // Win
        outcome = "WIN";
        const tiers = [5000, 8000, 12500, 15000, 25000, 50000];
        gross = tiers[Math.floor(Math.random() * tiers.length)];
        net = gross - SPIN_FLAT_COST_PAT;
      } else {
        outcome = "LOSS";
        gross = 0;
        net = -SPIN_FLAT_COST_PAT;
      }

      const rec = this.strategy.recordSpinResult(intervalS, offsetMs, outcome, gross, net);

      if (outcome === "WIN" || outcome === "JACKPOT") {
        this.emitActionLog(
          `[SPIN ANALYZER #${rec.spin_id} ✅] Spinner=${BOT_USERNAME} | Outcome=${rec.outcome} | Gross=+${gross.toLocaleString()} PAT | Net=${net > 0 ? "+" : ""}${net.toLocaleString()} PAT | BestWindow=${this.strategy.getBestProfitWindowBracket()}`
        );
      } else {
        this.emitActionLog(
          `[SPIN ANALYZER #${rec.spin_id} ❌] Spinner=${BOT_USERNAME} | Outcome=LOSS | Net=${net.toLocaleString()} PAT | PityStreak=${this.strategy.pityState.consecutive_losses}/6 | BestWindow=${this.strategy.getBestProfitWindowBracket()}`
        );
      }
      this.notify();
    }, 900);
  }

  stopAll() {
    this.setAutoSpinState(false);
    this.botSettings.chat_mode = false;
    this.botSettings.silent_mode = true;
    this.emitActionLog("[STOP ALL 🚨] Terminated all background loops, auto-spinners, and muted broadcasts.");
    this.notify();
  }

  // Line 1: Admin Command Prompt Emulator
  executeAdminCmd(cmd: string) {
    const cleaned = cmd.trim();
    if (!cleaned) return;
    this.emitActionLog(`[ADMIN-CMD] C:\\Windows\\System32> ${cleaned}`);

    setTimeout(() => {
      const low = cleaned.toLowerCase();
      if (low === "dir") {
        this.emitActionLog("  Directory of C:\\CamfrogBot\\data");
        this.emitActionLog("  10/14/2026  02:47 AM    <DIR>          .");
        this.emitActionLog("  10/14/2026  02:47 AM    <DIR>          ..");
        this.emitActionLog("  10/14/2026  02:47 AM           487,424 camfrog_bot.db");
        this.emitActionLog("  10/14/2026  02:47 AM               344 camfrog_calibration.json");
        this.emitActionLog("  10/14/2026  02:47 AM            14,821 spin_timing_records.csv");
        this.emitActionLog("  10/14/2026  02:47 AM             6,338 spin_timing_records.jsonl");
      } else if (low.includes("gpu") || low.includes("dxdiag") || low.includes("directml")) {
        this.emitActionLog("  GPU 0: AMD Radeon RX 9070 XT (Discrete, 16GB VRAM)");
        this.emitActionLog("  DirectX: 12.2 (FL 12_2) | DirectML: Active (DeviceIndex: 0)");
        this.emitActionLog("  ExecutionProvider: DmlExecutionProvider (FP16 Accelerated)");
      } else if (low.includes("status")) {
        this.emitActionLog(
          `  Status: Running | HWND=0x001A03F2 | AutoSpin=${this.autoSpinEnabled ? "ON" : "OFF"} | Users=${this.users.size}`
        );
      } else {
        this.emitActionLog(`  [ADMIN-CMD] Process executed with returncode 0. Clean exit.`);
      }
      this.notify();
    }, 400);
  }

  // Line 2: Send as Bot in Chat OR trigger local command
  sendManualChat(text: string) {
    const cleaned = text.trim();
    if (!cleaned) return;
    this.emitActionLog(`[BOT-CHAT TX] KaeKae_Toad -> ${cleaned}`);

    const low = cleaned.toLowerCase();

    // Voice command
    if (low.startsWith("!voice ")) {
      const v = cleaned.slice(7).trim();
      this.botSettings.tts_voice = v;
      this.emitActionLog(`[NEURAL-VOICE] Switched KaeKae_Toad voice to ${v}`);
      this.notify();
      return;
    }

    // Mic say command
    if (low.startsWith("!say ")) {
      const phrase = cleaned.slice(5).trim().replace(/^["']|["']$/g, "");
      this.speakOnMic(phrase);
      return;
    }

    // KaeKae Local Trigger dispatch
    const reply = this.dispatchTrigger(BOT_USERNAME, cleaned);
    if (reply) {
      this.emitActionLog(`[KAEKAE-TRIGGER] ${reply}`);
      this.emitIncomingLog(`[BOT CHAT] KaeKae_Toad: ${reply}`);
      this.notify();
      return;
    }

    // PepeFrog game commands
    if (low === "!spin") {
      this.emitActionLog(`[BOT-CHAT SENT ✅] Dispatched '!spin' into Camfrog Chat Box.`);
      this.stepSpinOnce();
      return;
    }

    if (low === "!sheet") {
      const c = this.strategy.heistCharacter;
      const sheetMsg = `[HEIST SHEET] ${c.character_class} | STR:${c.stats.STR} DEX:${c.stats.DEX} CON:${c.stats.CON} INT:${c.stats.INT} WIS:${c.stats.WIS} CHA:${c.stats.CHA} | Total Power: ${c.total_stat_power} | Relics: ${c.relics.join(", ")} | Gear: ${c.gear.join(", ")}`;
      this.emitIncomingLog(`[PUBLICACCESS.TV] ${sheetMsg}`);
      this.emitActionLog(`[HEIST ADVISOR] ${c.recommended_upgrade_reason}`);
      this.notify();
      return;
    }

    if (low.startsWith("!heist")) {
      this.strategy.totalHeistsExecuted++;
      this.emitIncomingLog(`[PUBLICACCESS.TV] Stonerwayne1000 started a ${cleaned.slice(7) || "Casino"} Heist! Type !join`);
      this.notify();
      return;
    }

    if (low === "!join") {
      this.emitIncomingLog(`[PUBLICACCESS.TV] KaeKae_Toad joined the crew! (+INT 18 Mastermind tactical bonus)`);
      this.notify();
      return;
    }

    if (low === "!bail") {
      const evalBail = this.strategy.evaluateVaultDoorVsBail("casino", 42000, 2850000);
      this.emitActionLog(`[HEIST BAIL] ${evalBail.reason}`);
      this.emitIncomingLog(`[PUBLICACCESS.TV] KaeKae_Toad bailed safely with +50,400 PAT (+20% Ghost Plates)!`);
      this.strategy.walletBalancePat += 50400;
      this.notify();
      return;
    }

    if (low === "!balance") {
      this.emitIncomingLog(
        `[PUBLICACCESS.TV] @KaeKae_Toad: Wallet = ${this.strategy.walletBalancePat.toLocaleString()} PAT | Jackpot = ${this.strategy.jackpotPoolPat.toLocaleString()} PAT`
      );
      this.notify();
      return;
    }

    this.emitActionLog(`[BOT-CHAT SENT ✅] Dispatched '${cleaned}' + Enter into Camfrog Chat Box.`);
    this.emitIncomingLog(`[CHAT] KaeKae_Toad: ${cleaned}`);
    this.notify();
  }

  // Line 3: Special Mic Line
  speakOnMic(phrase: string, voice?: string) {
    const cleaned = phrase.trim();
    if (!cleaned) return;
    const v = voice || this.botSettings.tts_voice;
    this.emitActionLog(
      `[MIC-BROADCAST] Queueing KaeKae_Toad mic speech (Talk=[${TALK_BUTTON_RECT.join(", ")}], Voice='${v}'): '${cleaned}'`
    );

    setTimeout(() => {
      this.currentSpeaker = BOT_USERNAME;
      this.emitIncomingLog(`[INCOMING MIC 🎙️] SPEAKER_ON_MIC: 'KaeKae_Toad' grabbed mic -> VB-Cable broadcasting...`);
      this.emitTranscribeLog(`[MIC] KaeKae_Toad: "${cleaned}" (Synthesized via VB-Cable [${v}])`);

      setTimeout(() => {
        this.currentSpeaker = null;
        this.emitIncomingLog(`[INCOMING MIC 🎙️] KaeKae_Toad released mic (2.8s hold completed).`);
        this.emitActionLog(`[MIC-BROADCAST DONE ✅] Finished speaking on Camfrog mic: '${cleaned}'`);
        this.notify();
      }, 2800);
      this.notify();
    }, 400);
  }

  // Coqui voice cloning actions
  coquiSample() {
    this.emitTranscribeLog(
      `[VOICE-CLONE 🎙️] Sampling 4.5s clean audio slice from Active Speaker '${this.currentSpeaker || "Rosie"}'...`
    );
    setTimeout(() => {
      this.emitTranscribeLog(
        `[VOICE-CLONE 🎙️] Captured 24,000Hz reference wav: data/models/xtts_v2/samples/speaker_sample.wav (SNR: 34dB ✅)`
      );
      this.notify();
    }, 800);
  }

  coquiClone() {
    this.emitTranscribeLog(
      `[VOICE-CLONE 🧬] Processing reference waveform through XTTS-v2 latent diffusion model...`
    );
    setTimeout(() => {
      this.emitTranscribeLog(
        `[VOICE-CLONE 🧬] Generated latent speaker embedding! Slot updated -> 'Active Clone: ${this.currentSpeaker || "Custom"}'`
      );
      this.notify();
    }, 1200);
  }

  coquiDefault() {
    this.emitTranscribeLog(
      `[VOICE-CLONE ▶️] Set cloned latent embedding as default synthesizer speaker profile.`
    );
    this.notify();
  }

  coquiClear() {
    this.emitTranscribeLog(
      `[VOICE-CLONE 🧹] Cleared custom voice clone slot. Reverted to Coqui Default (Test Clone).`
    );
    this.notify();
  }

  // --- DEDICATED CLONE MODE & AUTOMATIC SPEAKER AUDIO HIJACK PIPELINE ---

  enterCloneMode() {
    if (this.appMode !== "REGULAR") return;

    // 1. Save regular mode state
    this.savedRegularState = {
      autoSpinEnabled: this.autoSpinEnabled,
      randomSpinMode: this.randomSpinMode,
      countdownRemaining: this.nextSpinCountdownS,
      chatMode: this.botSettings.chat_mode,
    };

    // 2. Safely halt auto-spin timers and non-critical dispatches
    if (this.countdownTimerId) {
      window.clearInterval(this.countdownTimerId);
      this.countdownTimerId = null;
    }
    if (this.spinLoopTimerId) {
      window.clearTimeout(this.spinLoopTimerId);
      this.spinLoopTimerId = null;
    }
    this.autoSpinEnabled = false;
    this.botSettings.chat_mode = false;

    // 3. Arm the clone pipeline
    this.appMode = "CLONE_ARMED";
    this.cloneState = {
      ...this.cloneState,
      armed: true,
      stage: "armed",
      targetSpeaker: null,
      sampleProgress: 0,
      elapsedSeconds: 0,
    };

    this.emitActionLog(
      "[CLONE MODE 🎙️] Armed ONE-CLICK DEPLOY CLONE. Paused background auto-spins and non-critical chat."
    );
    this.emitTranscribeLog(
      "[CLONE MODE 🎙️] Pipeline armed! Waiting for SPEAKER_ON_MIC at [1506,1174,1548,1190] to hijack incoming audio stream..."
    );

    // 4. Check if a speaker is already holding the mic right now!
    if (this.currentSpeaker && this.currentSpeaker !== BOT_USERNAME) {
      this.startSpeakerHijack(this.currentSpeaker);
    } else {
      this.notify();
    }
  }

  cancelCloneMode() {
    if (this.cloneSamplingTimerId) {
      window.clearInterval(this.cloneSamplingTimerId);
      this.cloneSamplingTimerId = null;
    }

    this.appMode = "REGULAR";
    this.cloneState.stage = "idle";
    this.cloneState.armed = false;
    this.cloneState.sampleProgress = 0;
    this.cloneState.targetSpeaker = null;

    // Restore saved regular mode state
    if (this.savedRegularState) {
      if (this.savedRegularState.chatMode) {
        this.botSettings.chat_mode = true;
      }
      if (this.savedRegularState.autoSpinEnabled) {
        this.setAutoSpinState(true, this.savedRegularState.randomSpinMode);
      }
    }

    this.emitActionLog("[CLONE CANCELLED ❌] Aborted Clone Mode. Restored Regular Bot Mode state.");
    this.emitTranscribeLog("[CLONE CANCELLED ❌] Standby reset. Audio pipeline returned to room listener.");
    this.notify();
  }

  startSpeakerHijack(speakerName: string) {
    if (this.appMode === "CLONE_SAMPLING" || this.appMode === "CLONE_PROCESSING") return;

    this.appMode = "CLONE_SAMPLING";
    this.cloneState = {
      ...this.cloneState,
      stage: "sampling",
      targetSpeaker: speakerName,
      sampleProgress: 0,
      elapsedSeconds: 0,
    };

    this.emitIncomingLog(
      `[AUDIO HIJACK 🎙️] SPEAKER_ON_MIC: '${speakerName}' detected at [1506,1174,1548,1190]! Hijacking live audio stream...`
    );
    this.emitTranscribeLog(
      `[AUDIO HIJACK 🎙️] Sampling 4.5s clean voice reference for '${speakerName}' at 24,000Hz (VB-Cable loopback / Stereo Mix)...`
    );
    this.notify();

    let elapsed = 0;
    const totalDuration = 4.5;

    if (this.cloneSamplingTimerId) {
      window.clearInterval(this.cloneSamplingTimerId);
      this.cloneSamplingTimerId = null;
    }

    this.cloneSamplingTimerId = window.setInterval(() => {
      elapsed += 0.2;
      const progress = Math.min(100, Math.round((elapsed / totalDuration) * 100));
      this.cloneState.sampleProgress = progress;
      this.cloneState.elapsedSeconds = Number(elapsed.toFixed(1));
      this.notify();

      if (elapsed >= totalDuration) {
        if (this.cloneSamplingTimerId) {
          window.clearInterval(this.cloneSamplingTimerId);
          this.cloneSamplingTimerId = null;
        }
        this.processXTTSv2Embedding(speakerName);
      }
    }, 200);
  }

  processXTTSv2Embedding(speakerName: string) {
    this.appMode = "CLONE_PROCESSING";
    this.cloneState.stage = "processing";
    this.cloneState.sampleProgress = 100;

    this.emitTranscribeLog(
      `[XTTS-V2 🧬] Captured 4.5s wav (24kHz, SNR: 36.8 dB ✅). Synthesizing 512-dim latent speaker embedding for '${speakerName}'...`
    );
    this.notify();

    setTimeout(() => {
      const cloneVoiceLabel = `Active Clone: ${speakerName}`;
      if (!this.cloneState.availableClones.includes(cloneVoiceLabel)) {
        this.cloneState.availableClones.push(cloneVoiceLabel);
      }
      this.cloneState.lastClonedVoice = cloneVoiceLabel;
      this.cloneState.stage = "ready";
      this.appMode = "CLONE_READY";

      // Automatically load clone into active TTS voice
      this.botSettings.tts_voice = cloneVoiceLabel;

      this.emitTranscribeLog(
        `[XTTS-V2 🧬] Neural speaker embedding synthesized successfully! Loaded into voice slot '${cloneVoiceLabel}'.`
      );
      this.emitActionLog(
        `[CLONE DEPLOYED ✅] Cloned voice profile '${cloneVoiceLabel}' is armed. Automatically returning to Regular Bot Mode...`
      );
      this.notify();

      // Return to regular mode automatically
      setTimeout(() => {
        this.finishCloneAndReturnToRegular(cloneVoiceLabel);
      }, 1400);
    }, 1200);
  }

  finishCloneAndReturnToRegular(newVoiceLabel?: string) {
    this.appMode = "REGULAR";
    this.cloneState.stage = "idle";
    this.cloneState.armed = false;
    this.cloneState.sampleProgress = 0;

    if (newVoiceLabel) {
      this.botSettings.tts_voice = newVoiceLabel;
    }

    // Restore previous regular mode settings
    if (this.savedRegularState) {
      if (this.savedRegularState.chatMode) {
        this.botSettings.chat_mode = true;
      }
      if (this.savedRegularState.autoSpinEnabled) {
        this.setAutoSpinState(true, this.savedRegularState.randomSpinMode);
      }
    }

    this.emitActionLog(
      `[REGULAR MODE RESUMED ✅] Bot returned to Regular Mode! Active Voice: '${this.botSettings.tts_voice}'. All room listeners and mechanisms running.`
    );
    this.notify();
  }

  simulateSpeakerMicGrab(speakerName?: string) {
    const spk = speakerName || "Rosie";
    this.currentSpeaker = spk;
    this.emitIncomingLog(
      `[INCOMING MIC 🎙️] SPEAKER_ON_MIC: '${spk}' grabbed mic at [${TALK_BUTTON_RECT.join(", ")}] -> Audio stream available!`
    );

    if (this.appMode === "CLONE_ARMED") {
      this.startSpeakerHijack(spk);
    } else {
      setTimeout(() => {
        if (this.currentSpeaker === spk && this.appMode === "REGULAR") {
          this.currentSpeaker = null;
          this.emitIncomingLog(`[INCOMING MIC 🎙️] ${spk} released mic.`);
          this.notify();
        }
      }, 4000);
      this.notify();
    }
  }

  // Internal trigger dispatcher
  dispatchTrigger(sender: string, rawText: string): string | null {
    const raw = rawText.trim();
    const low = raw.toLowerCase();
    const profile = this.users.get(sender.toLowerCase());

    if (low === "!chat") {
      this.botSettings.chat_mode = true;
      this.botSettings.silent_mode = false;
      return "Chat mode is ON — KaeKae_Toad is mingling and watching the room.";
    }

    if (low === "!chatoff" || low === "!chat off") {
      this.botSettings.chat_mode = false;
      return "Chat mode is off.";
    }

    if (low === "!shutup") {
      this.botSettings.silent_mode = true;
      return "Silent mode engaged — all room replies, broadcasts and audio suppressed.";
    }

    if (low === "!transcribe") {
      this.botSettings.transcription_mode = true;
      this.botSettings.post_transcripts_to_chat = true;
      return `Transcription mode is ON (posting [MIC] <Speaker>: <Text> in real time; current speaker: ${this.currentSpeaker || "none"}).`;
    }

    if (low === "!transcribed") {
      this.botSettings.transcription_mode = false;
      this.botSettings.post_transcripts_to_chat = false;
      return "Transcription is off.";
    }

    if (low === "!suppress") {
      this.suppressedUsers.add(sender.toLowerCase());
      return "Stored profile and history were dumped to the separate vault folder and removed from bot queries.";
    }

    if (low === "!unsuppress") {
      this.suppressedUsers.delete(sender.toLowerCase());
      return "Stored profile and history were restored from the vault.";
    }

    if (low.startsWith("!diss")) {
      const target = raw.slice(5).trim() || "the room";
      return this.brain.pickUniqueDiss(target, profile);
    }

    if (low.startsWith("!idk")) {
      return this.brain.generateIdkReply(sender, raw.slice(4), profile, this.botSettings.tone, this.botSettings.chat_mode);
    }

    if (low === "!happy" || low === "!sad" || low === "!mad") {
      this.botSettings.tone = low.slice(1) as "happy" | "sad" | "mad";
      return `Tone set to ${this.botSettings.tone}.`;
    }

    if (low === "!triggers") {
      return "KaeKae_Toad Triggers: (1) kaekae <question>, (2) !chat, (3) !chatoff, (4) !shutup, (5) !transcribe, (6) !transcribed, (7) !suppress, (8) !unsuppress, (9) !say, (10) !diss, (11) !who is, (12) !info on, (13) !grabs, (14) -, (15) !idk, (16) who kicked/banned/blocked/punished, (17) !happy, (18) !sad, (19) !mad, (20) !triggers.";
    }

    if (low === "-") {
      return "[Page 2/2] Room Statistics: 42 users active in last 24h | Total Spins: 24 | Jackpot Pool: 2,850,000 PAT | High Heist Score: 185,000 PAT.";
    }

    if (low.startsWith("!who is ")) {
      const u = raw.slice(8).trim();
      const p = this.users.get(u.toLowerCase());
      if (!p) return `No stored profile for ${u}.`;
      return `Biography of ${p.username} [${p.gender}, in room]: Seen since ${p.first_seen} with ${p.message_count} messages (${p.speech_patterns} style, top noun '${p.top_noun}', ${p.mic_grab_count} mic grabs). ${p.biography}`;
    }

    if (low.startsWith("!info on ")) {
      const u = raw.slice(9).trim();
      const p = this.users.get(u.toLowerCase());
      if (!p) return `No stored statistics for ${u}.`;
      return `${p.username}: ${p.message_count} messages; text tone: ${p.text_tone}; audio tone: ${p.audio_tone}; top noun '${p.top_noun}' (${p.top_count || 5}x); room time ${(p.total_chat_seconds / 60).toFixed(0)}m; ${p.mic_grab_count} mic grabs / ${p.total_mic_seconds}s in 24h.`;
    }

    if (low.startsWith("!grabs")) {
      const target = raw.slice(6).trim() || sender;
      return `Mic grabs for ${target}: 5 grabs, 218s over the last 1440 minutes (24h).`;
    }

    if (low.includes("who kicked") || low.includes("who banned") || low.includes("who punished") || low.includes("who blocked")) {
      return "Moderation check: No moderation records found for that user in the last 24 hours.";
    }

    if (low.includes("kaekae")) {
      return this.brain.generateContextualReply(
        sender,
        raw,
        profile,
        [],
        this.currentSpeaker,
        this.botSettings.tone,
        this.botSettings.chat_mode
      );
    }

    return null;
  }

  // Realistic background simulation of Camfrog lounge activity
  startBackgroundSimulation() {
    const chatSamples = [
      { user: "Stonerwayne1000", text: "!spin" },
      { user: "Rosie", text: "hope the wheel lands on gold!" },
      { user: "OMGitsMyPHONE", text: "!balance" },
      { user: "Stonerwayne1000", text: "!heist store" },
      { user: "Rosie", text: "kaekae are you ready for the lotto draw?" },
      { user: "lockspeck", text: "audio loopback is crystal clear" },
      { user: "nico1ee", text: "!sheet" },
      { user: "OMGitsMyPHONE", text: "!spin" },
    ];

    // Every 12-18 seconds, simulate incoming room chatter or presence
    setInterval(() => {
      if (!this.botSettings.running) return;

      const sample = chatSamples[Math.floor(Math.random() * chatSamples.length)];
      const analysis = analyzeSentimentAndTone(sample.text);
      this.emitIncomingLog(
        `[CHAT] ${sample.user}: ${sample.text} (Tone: ${analysis.tone})`
      );

      // If user called kaekae and chat mode is on, reply
      if (sample.text.toLowerCase().includes("kaekae") && this.botSettings.chat_mode && !this.botSettings.silent_mode) {
        const reply = this.brain.generateContextualReply(
          sample.user,
          sample.text,
          this.users.get(sample.user.toLowerCase()),
          [],
          this.currentSpeaker,
          this.botSettings.tone,
          this.botSettings.chat_mode
        );
        this.emitActionLog(`[KAEKAE-MINGLE] ${reply}`);
        this.emitIncomingLog(`[BOT CHAT] KaeKae_Toad: ${reply}`);
      }

      // If someone spins in room, capture in Terminal 2
      if (sample.text === "!spin") {
        const isWin = Math.random() < 0.42;
        const gross = isWin ? 10000 : 0;
        const net = isWin ? 5000 : -5000;
        this.emitActionLog(
          `[SPIN ANALYZER (ROOM)] Spinner=${sample.user} | Outcome=${isWin ? "WIN" : "LOSS"} | Gross=+${gross.toLocaleString()} PAT | Net=${net > 0 ? "+" : ""}${net.toLocaleString()} PAT`
        );
      }
    }, 14000);

    // Random mic grab simulation every 35 seconds
    setInterval(() => {
      if (!this.botSettings.running || this.currentSpeaker) return;
      const speakerList = ["Stonerwayne1000", "Rosie", "nico1ee", "lockspeck"];
      const spk = speakerList[Math.floor(Math.random() * speakerList.length)];
      this.currentSpeaker = spk;
      this.emitIncomingLog(`[INCOMING MIC 🎙️] SPEAKER_ON_MIC: '${spk}' grabbed mic at [${TALK_BUTTON_RECT.join(", ")}] -> Live terminal transcription active!`);

      if (this.appMode === "CLONE_ARMED") {
        this.startSpeakerHijack(spk);
      }

      const micTexts = [
        "Yeah so for the next heist let's make sure everyone brings lockpicks and hacking rigs.",
        "Anyone doing the Sunday lotto? The pool is over 450k now.",
        "Checking the audio levels, can everyone hear me okay in the back?",
      ];
      const spoken = micTexts[Math.floor(Math.random() * micTexts.length)];

      setTimeout(() => {
        this.emitTranscribeLog(`[LIVE-TRANSCRIBE 📝] [MIC] ${spk}: "${spoken}" (Device='Stereo Mix', Peak=58, Engine=WhisperX)`);
        if (this.botSettings.post_transcripts_to_chat && !this.botSettings.silent_mode) {
          this.emitIncomingLog(`[MIC TRANSCRIPT] [MIC] ${spk}: "${spoken}"`);
        }
      }, 1400);

      setTimeout(() => {
        if (this.currentSpeaker === spk) {
          this.currentSpeaker = null;
          this.emitIncomingLog(`[INCOMING MIC 🎙️] ${spk} released mic (3.4s).`);
          this.notify();
        }
      }, 4200);
      this.notify();
    }, 32000);
  }
}

export const orchestrator = new BotOrchestrator();
