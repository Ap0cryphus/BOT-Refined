export interface SpinTimingRecord {
  spin_id: number;
  timestamp_iso: string;
  interval_seconds: number;
  window_bracket: string; // "60s-90s (1.0m-1.5m)" | "90s-120s (1.5m-2.0m)" | "120s-150s (2.0m-2.5m)" | "150s-180s (2.5m-3.0m)"
  phase_offset_ms: number;
  outcome: "WIN" | "JACKPOT" | "LOSS";
  gross_payout_pat: number;
  net_delta_pat: number;
  wallet_after_pat: number;
  jackpot_pool_pat: number;
}

export interface UserProfile {
  username: string;
  is_active: boolean;
  first_seen: string;
  last_seen: string;
  gender: "male (blue)" | "female (pink)" | "unknown";
  status_category: string;
  message_count: number;
  mic_grab_count: number;
  total_mic_seconds: number;
  total_chat_seconds: number;
  top_noun: string;
  top_word?: string;
  top_count?: number;
  text_tone: string;
  audio_tone: string;
  speech_patterns: string;
  biography: string;
  messages: string[];
  mic_transcripts: string[];
}

export interface PresenceEvent {
  id: string;
  username: string;
  action: "join" | "quit";
  observed_at: string;
}

export interface ModerationEvent {
  id: string;
  actor: string;
  target: string;
  action: "kicked" | "banned" | "blocked" | "punished" | "unbanned" | "unblocked" | "unpunished";
  observed_at: string;
  raw_text: string;
}

export interface MicGrab {
  id: string;
  username: string;
  started_at: string;
  duration_seconds: number;
  transcript: string;
}

export interface TerminalLine {
  id: string;
  timestamp: string;
  text: string;
  type: "incoming" | "action" | "transcribe" | "diag" | "notice" | "error";
  category?: string;
}

export interface CalibrationState {
  window_rect: [number, number, number, number];
  chat_input_rect: [number, number, number, number];
  chat_input_screen_pt: [number, number];
  talk_button_rect: [number, number, number, number];
  talk_button_screen_pt: [number, number];
  calibrated_at: string;
  allowed_admins: string[];
}

export interface HeistCharacter {
  stats: {
    STR: number;
    DEX: number;
    CON: number;
    INT: number;
    WIS: number;
    CHA: number;
  };
  unspent_points: number;
  character_class: string;
  relics: string[];
  gear: string[];
  total_stat_power: number;
  recommended_upgrade_cmd?: string;
  recommended_upgrade_reason?: string;
}

export interface PityState {
  consecutive_losses: number;
  max_loss_streak_observed: number;
  pity_trigger_threshold: number;
  detected_safety_net_bounces: number;
  pity_safety_net_active: boolean;
  sink_rate_estimate: number;
}

export interface StrategyDecision {
  command: string;
  mode_flag: string;
  expected_value_pat: number;
  rationale: string;
  wallet_balance_pat: number;
  jackpot_pool_pat: number;
  consecutive_losses: number;
  pity_safety_net_active: boolean;
  beg_cooldown_remaining_s: number;
  spin_cooldown_remaining_s: number;
  recommended_spin_interval_s: number;
}

export interface WindowBracketStats {
  [bracketName: string]: {
    spins: number;
    wins: number;
    jackpots: number;
    net_pat: number;
  };
}

export interface BotSettings {
  running: boolean;
  chat_mode: boolean;
  silent_mode: boolean;
  transcription_mode: boolean;
  post_transcripts_to_chat: boolean;
  tone: "neutral" | "happy" | "sad" | "mad";
  tts_voice: string;
  whisperx_enabled: boolean;
  gpu_acceleration: boolean;
  gpu_backend: string;
}

export type AppMode = "REGULAR" | "CLONE_ARMED" | "CLONE_SAMPLING" | "CLONE_PROCESSING" | "CLONE_READY";

export interface CloneState {
  armed: boolean;
  stage: "idle" | "armed" | "sampling" | "processing" | "ready";
  targetSpeaker: string | null;
  sampleProgress: number; // 0 - 100
  elapsedSeconds: number;
  lastClonedVoice: string | null;
  availableClones: string[];
}

