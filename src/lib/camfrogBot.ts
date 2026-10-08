/**
 * Faithful TypeScript port of config.py, ui_automation.py, camfrog_bot.py,
 * room_data_processor.py, and test_bot.py — updated with exact calibrated
 * UIA coordinates and continuous audio transcription storage.
 */

export const CAPTURE_BACKEND = 'uia';
export const OCR_ENABLED = false;
export const DXCAM_ENABLED = false;
export const TESSERACT_ENABLED = false;
export const IMAGE_CAPTURE_ENABLED = false;

export const CAMFROG_WINDOW_TITLE_RE = '(?i).*Players__Lounge([,:].*?)?\\s*Video Chat Room.*';
export const POLL_INTERVAL_SECONDS = 0.75;
export const UIA_CACHE_SECONDS = 0.30;
export const MAX_CHAT_MESSAGE_LENGTH = 425;
export const CHAT_HISTORY_LIMIT = 10;

export type RoomName = 'Room List' | 'Players__Lounge' | 'Drama_Central';

/**
 * Fixed tab click coordinates & bounding boxes (independent of dynamic window title/topic):
 * (1390, 50) -> Room List
 * (1550, 50) -> Players__Lounge
 */
export const ROOM_TAB_CLICK_POINTS: Record<RoomName, [number, number]> = {
  'Room List': [1390, 50],
  'Players__Lounge': [1550, 50],
  'Drama_Central': [1710, 50],
};

export const ROOM_TAB_POSITIONS: Record<RoomName, [number, number, number, number]> = {
  'Room List': [1313, 37, 1473, 71],
  'Players__Lounge': [1473, 37, 1633, 71],
  'Drama_Central': [1633, 37, 1793, 71],
};

/**
 * Exact calibrated UIA Control BoundingRectangles [left, top, right, bottom]:
 * - Chat Window: Pane(50033) [l=1281,t=170,r=2299,b=1160]
 * - Talk Button: Button(50000) [l=1291,t=1169,r=1361,b=1195]
 * - User List: List(50008) [l=2303,t=141,r=2559,b=1160]
 */
export const CALIBRATED_UIA_RECTS = {
  chat_window: {
    control_type: 'Pane(50033)',
    rect: [1281, 170, 2299, 1160] as [number, number, number, number],
  },
  talk_button: {
    control_type: 'Button(50000)',
    rect: [1291, 1169, 1361, 1195] as [number, number, number, number],
  },
  user_list: {
    control_type: 'List(50008)',
    rect: [2303, 141, 2559, 1160] as [number, number, number, number],
  },
};

/**
 * Specific ListItem(50007) bounding rectangles in the User List (r=2559)
 * that represent section headers/separators and MUST be ignored when extracting usernames:
 */
export const IGNORED_USER_LIST_RECTS: Array<[number, number, number, number]> = [
  [2303, 141, 2559, 163],
  [2303, 207, 2559, 229],
  [2303, 867, 2559, 889],
];

export function isIgnoredUserListItemRect(rect: [number, number, number, number]): boolean {
  const [l, t, r, b] = rect;
  return IGNORED_USER_LIST_RECTS.some(
    ([il, it, ir, ib]) => l === il && t === it && r === ir && b === ib
  );
}

export const VB_CABLE_CONFIG = {
  playback_device: 'CABLE Input (VB-Audio Virtual Cable)',
  recording_device: 'CABLE Output (VB-Audio Virtual Cable)',
  talk_button_center: [1326, 1182] as [number, number],
  talk_button_rect: [1291, 1169, 1361, 1195] as [number, number, number, number],
};

export interface BotSettings {
  chat_mode: boolean;
  silent_mode: boolean;
  transcription_mode: boolean;
  continuous_audio_store: boolean;
  vb_cable_tts_enabled: boolean;
  vb_cable_device_name: string;
  running: boolean;
  dry_run: boolean;
  tone: 'neutral' | 'happy' | 'sad' | 'mad';
}

export const INITIAL_BOT_SETTINGS: BotSettings = {
  chat_mode: false,
  silent_mode: false,
  transcription_mode: true,
  continuous_audio_store: true,
  vb_cable_tts_enabled: true,
  vb_cable_device_name: 'CABLE Input (VB-Audio Virtual Cable)',
  running: true,
  dry_run: true,
  tone: 'neutral',
};

export const NATIVE_MODERATION_COMMANDS = new Set([
  'unpunish',
  'unblockmic',
  'unban',
  'topic',
  'watchlist',
]);

export const TRIGGER_NAMES = [
  'kaekae',
  '!chat',
  '!chatoff',
  '!shutup',
  '!transcribe',
  '!transcribed',
  '!suppress',
  '!unsuppress',
  '!say',
  '!diss',
  '!who is',
  '!info on',
  '!grabs',
  '-',
  '!idk',
  'who kicked/blocked/banned/punished',
  '!happy',
  '!sad',
  '!mad',
  '!triggers',
] as const;

const CLOCK_RE = /^\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?$/i;
const COMPACT_CLOCK_RE = /^\d{3,4}(?:AM|PM)$/i;
const USERNAME_RE = /^[A-Za-z0-9_$-]{2,32}$/;
const PANEL_LABELS = new Set([
  'talk',
  'push-to-talk',
  'camfrog',
  'users',
  'user',
  'members',
  'lurkers',
  'youareviewing',
  'search',
  'gifts',
  'giftusers',
  'yourvideo',
  'room',
  'chat',
]);

const WORD_RE = /[A-Za-z][A-Za-z'-]{2,}/g;
const MOD_RE =
  /^\s*(?<actor>[A-Za-z0-9_$-]{2,32})\s+(?:was\s+)?(?<action>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\s+(?<target>[A-Za-z0-9_$-]{2,32})(?:\s+microphone)?\s*[.!]?\s*$/i;
const MOD_BY_RE =
  /^\s*(?<target>[A-Za-z0-9_$-]{2,32})\s+was\s+(?<action>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\s+by\s+(?<actor>[A-Za-z0-9_$-]{2,32})\s*[.!]?\s*$/i;
const HISTORY_RE =
  /^who\s+(?<action>kicked|blocked|unblocked|banned|unbanned|punished|unpunished)\s+(?<target>[A-Za-z0-9_$-]{2,32})\s*\??$/i;

/**
 * Return a valid Camfrog username, or an empty string for UI chrome or ignored ListItem rects.
 */
export function cleanUsername(value: string, rect?: [number, number, number, number]): string {
  if (rect && isIgnoredUserListItemRect(rect)) {
    return '';
  }
  const raw = String(value || '').trim();
  if (CLOCK_RE.test(raw) || COMPACT_CLOCK_RE.test(raw)) {
    return '';
  }
  const name = raw.replace(/[^A-Za-z0-9_$-]/g, '').slice(0, 32);
  const lower = name.toLowerCase();
  if (lower === 'giftusers2') {
    return '';
  }
  return USERNAME_RE.test(name) && !PANEL_LABELS.has(lower) ? name : '';
}

export interface ModerationNotice {
  actor: string;
  target: string;
  action: string;
}

export function detectModeration(text: string): ModerationNotice | null {
  const input = String(text || '');
  for (const pattern of [MOD_BY_RE, MOD_RE]) {
    const match = pattern.exec(input);
    if (!match || !match.groups) continue;
    const actor = cleanUsername(match.groups.actor);
    const target = cleanUsername(match.groups.target);
    if (actor && target) {
      return {
        actor,
        target,
        action: match.groups.action.toLowerCase(),
      };
    }
  }
  return null;
}

export function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, '+00:00');
}

export function normalizeMessage(text: string): string {
  return String(text || '')
    .toLowerCase()
    .trim()
    .split(/\s+/)
    .join(' ');
}

export function messageKey(user: string, text: string, timestamp = ''): string {
  const source = `${user.toLowerCase()}|${normalizeMessage(text)}|${timestamp.toLowerCase()}`;
  let h1 = 0xdeadbeef ^ source.length;
  let h2 = 0x41c6ce57 ^ source.length;
  for (let i = 0; i < source.length; i++) {
    const ch = source.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (h2 >>> 0).toString(16).padStart(8, '0') + (h1 >>> 0).toString(16).padStart(8, '0');
}

export interface BotUserRow {
  username: string;
  first_seen: string;
  last_seen: string;
  message_count: number;
  active: number;
}

export interface BotMessageRow {
  id: number;
  event_key: string;
  username: string;
  body: string;
  observed_at: string;
  room_time: string;
  room?: RoomName;
  is_bot_reply?: boolean;
  dry_run?: boolean;
  source?: 'chat' | 'audio_transcript';
}

export interface PresenceEventRow {
  id: number;
  event_key: string;
  username: string;
  action: 'join' | 'quit';
  observed_at: string;
  room?: RoomName;
}

export interface ModerationEventRow {
  id: number;
  event_key: string;
  actor: string;
  target: string;
  action: string;
  observed_at: string;
  raw_text: string;
}

export interface MicGrabRow {
  id: number;
  username: string;
  started_at: string;
  duration_seconds: number;
  transcript?: string;
}

export interface AudioTranscriptRow {
  id: number;
  speaker: string;
  transcript: string;
  duration_seconds: number;
  observed_at: string;
  room: RoomName;
}

export interface SuppressedVaultPayload {
  username: string;
  suppressed_at: string;
  vault_file: string;
  user: BotUserRow | null;
  messages: BotMessageRow[];
  mic_grabs: MicGrabRow[];
  audio_transcripts: AudioTranscriptRow[];
}

export interface UserProfileResult extends BotUserRow {
  messages: string[];
  transcripts: string[];
  top_word: string;
  top_count: number;
}

export interface UIANode {
  id: string;
  control_type: string;
  name: string;
  class_name: string;
  left: number;
  top: number;
  right: number;
  bottom: number;
  ignored_reason?: string;
}

/**
 * In-memory port of CamfrogStore (SQLite tables + non-queryable suppression vault + audio transcripts)
 */
export class CamfrogStore {
  users: Map<string, BotUserRow> = new Map();
  messages: BotMessageRow[] = [];
  presenceEvents: PresenceEventRow[] = [];
  moderationEvents: ModerationEventRow[] = [];
  micGrabs: MicGrabRow[] = [];
  audioTranscripts: AudioTranscriptRow[] = [];
  suppressedVault: Map<string, SuppressedVaultPayload> = new Map();
  private nextMsgId = 1;
  private nextPresenceId = 1;
  private nextModId = 1;
  private nextGrabId = 1;
  private nextTranscriptId = 1;

  constructor(seedInitialData = true) {
    if (seedInitialData) {
      this.seedFromExistingDb();
    }
  }

  private seedFromExistingDb(): void {
    const initialMessages: Array<{ username: string; body: string; room_time: string; observed_at: string; room: RoomName }> = [
      { username: 'irreplacable', body: 'seem one good way do like that as their meant', room_time: '6:36 PM', observed_at: '2026-10-08T01:37:04+00:00', room: 'Players__Lounge' },
      { username: 'Stonerwayne1000', body: 'back', room_time: '6:36 PM', observed_at: '2026-10-08T01:37:04+00:00', room: 'Players__Lounge' },
      { username: 'Stonerwayne1000', body: 'sup nico1ee', room_time: '6:36 PM', observed_at: '2026-10-08T01:37:04+00:00', room: 'Players__Lounge' },
      { username: 'Stonerwayne1000', body: 'su tsyko', room_time: '6:37 PM', observed_at: '2026-10-08T01:37:32+00:00', room: 'Players__Lounge' },
      { username: 'Players_Lounge1', body: 'Welcome Back Friend, WutUpWattz', room_time: '6:37 PM', observed_at: '2026-10-08T01:37:53+00:00', room: 'Players__Lounge' },
      { username: 'Players_Lounge1', body: 'Welcome Back Admin, skracH_iLL_Man_', room_time: '5:56 PM', observed_at: '2026-10-08T01:38:13+00:00', room: 'Players__Lounge' },
      { username: 'gmoney165', body: 'Monica ur camera not working', room_time: '5:56 PM', observed_at: '2026-10-08T01:38:13+00:00', room: 'Players__Lounge' },
      { username: 'nico1ee', body: 'Welcome Back Admin, nico1ee', room_time: '6:32 PM', observed_at: '2026-10-08T01:38:13+00:00', room: 'Players__Lounge' },
      { username: 'Nick73', body: 'WE DO NOT PUNISH OR BAN ANY OF OUR REGULAR USERS.', room_time: '6:33 PM', observed_at: '2026-10-08T01:38:13+00:00', room: 'Players__Lounge' },
      { username: 'Stonerwayne1000', body: 'Welcome Back Moderator, Stonerwayne1000', room_time: '6:35 PM', observed_at: '2026-10-08T01:38:13+00:00', room: 'Players__Lounge' },
      { username: 'Stonerwayne1000', body: 'BX AND DARREN ARE NOT TO BE BLOCKED.', room_time: '6:36 PM', observed_at: '2026-10-08T01:38:13+00:00', room: 'Players__Lounge' },
      { username: 'Rosie', body: 'yea i am', room_time: '6:38 PM', observed_at: '2026-10-08T01:39:12+00:00', room: 'Players__Lounge' },
      { username: 'CYBERBABY2', body: 'thats of camfrog', room_time: '6:39 PM', observed_at: '2026-10-08T01:39:12+00:00', room: 'Drama_Central' },
    ];

    for (const msg of initialMessages) {
      this.recordMessage(msg.username, msg.body, msg.room_time, msg.observed_at, msg.room);
    }

    this.recordModeration(
      { actor: 'Stonerwayne1000', target: 'WutUpWattz', action: 'unpunished' },
      'WutUpWattz was unpunished by Stonerwayne1000.',
      '2026-10-08T01:35:00+00:00'
    );
    this.recordModeration(
      { actor: 'nico1ee', target: 'tedi4300', action: 'kicked' },
      'tedi4300 was kicked by nico1ee.',
      '2026-10-08T01:36:10+00:00'
    );
    this.recordModeration(
      { actor: 'skracH_iLL_Man_', target: 'CYBERBABY2', action: 'blocked' },
      'skracH_iLL_Man_ blocked CYBERBABY2 microphone.',
      '2026-10-08T01:37:45+00:00'
    );
    // Note: No fake mic_grabs or audio_transcripts are seeded; only real captured active-speaker events are stored.
  }

  isSuppressed(username: string): boolean {
    return this.suppressedVault.has(username.toLowerCase());
  }

  suppress(username: string): boolean {
    const cleaned = cleanUsername(username);
    if (!cleaned || this.isSuppressed(cleaned)) {
      return false;
    }
    const key = cleaned.toLowerCase();
    const user = this.users.get(key) || null;
    const userMessages = this.messages.filter((m) => m.username.toLowerCase() === key && !m.is_bot_reply);
    const userGrabs = this.micGrabs.filter((g) => g.username.toLowerCase() === key);
    const userTranscripts = this.audioTranscripts.filter((t) => t.speaker.toLowerCase() === key);
    const suppressedAt = nowIso();

    const payload: SuppressedVaultPayload = {
      username: cleaned,
      suppressed_at: suppressedAt,
      vault_file: `data/suppressed/${key}.json`,
      user: user ? { ...user } : null,
      messages: userMessages.map((m) => ({ ...m })),
      mic_grabs: userGrabs.map((g) => ({ ...g })),
      audio_transcripts: userTranscripts.map((t) => ({ ...t })),
    };

    this.suppressedVault.set(key, payload);
    this.messages = this.messages.filter((m) => m.username.toLowerCase() !== key || m.is_bot_reply);
    this.micGrabs = this.micGrabs.filter((g) => g.username.toLowerCase() !== key);
    this.audioTranscripts = this.audioTranscripts.filter((t) => t.speaker.toLowerCase() !== key);
    this.users.delete(key);
    return true;
  }

  unsuppress(username: string): boolean {
    const cleaned = cleanUsername(username);
    const key = cleaned.toLowerCase();
    const payload = this.suppressedVault.get(key);
    if (!payload) {
      return false;
    }
    if (payload.user) {
      this.users.set(key, { ...payload.user });
    }
    for (const msg of payload.messages) {
      if (!this.messages.some((existing) => existing.event_key === msg.event_key)) {
        this.messages.push({ ...msg });
      }
    }
    this.messages.sort((a, b) => a.id - b.id);
    for (const grab of payload.mic_grabs) {
      this.micGrabs.push({ ...grab, id: this.nextGrabId++ });
    }
    for (const tr of payload.audio_transcripts || []) {
      this.audioTranscripts.push({ ...tr, id: this.nextTranscriptId++ });
    }
    this.suppressedVault.delete(key);
    return true;
  }

  recordMessage(
    username: string,
    body: string,
    roomTime: string,
    observedAt = nowIso(),
    room: RoomName = 'Players__Lounge',
    isBotReply = false,
    dryRun = false,
    source: 'chat' | 'audio_transcript' = 'chat'
  ): BotMessageRow | null {
    if (!isBotReply && this.isSuppressed(username)) {
      return null;
    }
    const key = messageKey(username, body, `${roomTime}:${isBotReply ? this.nextMsgId : ''}:${source}`);
    if (!isBotReply && this.messages.some((m) => m.event_key === key)) {
      return null;
    }
    const row: BotMessageRow = {
      id: this.nextMsgId++,
      event_key: key,
      username,
      body,
      observed_at: observedAt,
      room_time: roomTime,
      room,
      is_bot_reply: isBotReply,
      dry_run: dryRun,
      source,
    };
    this.messages.push(row);

    if (!isBotReply) {
      const userKey = username.toLowerCase();
      const existing = this.users.get(userKey);
      if (existing) {
        existing.last_seen = observedAt;
        existing.message_count += 1;
        existing.active = 1;
      } else {
        this.users.set(userKey, {
          username,
          first_seen: observedAt,
          last_seen: observedAt,
          message_count: 1,
          active: 1,
        });
      }
    }
    return row;
  }

  recordPresence(username: string, action: 'join' | 'quit', eventKey: string, room: RoomName = 'Players__Lounge'): void {
    if (this.isSuppressed(username)) {
      return;
    }
    if (this.presenceEvents.some((e) => e.event_key === eventKey)) {
      return;
    }
    const observedAt = nowIso();
    this.presenceEvents.push({
      id: this.nextPresenceId++,
      event_key: eventKey,
      username,
      action,
      observed_at: observedAt,
      room,
    });
    const userKey = username.toLowerCase();
    const existing = this.users.get(userKey);
    if (existing) {
      existing.last_seen = observedAt;
      existing.active = action === 'join' ? 1 : 0;
    } else {
      this.users.set(userKey, {
        username,
        first_seen: observedAt,
        last_seen: observedAt,
        message_count: 0,
        active: action === 'join' ? 1 : 0,
      });
    }
  }

  recordModeration(event: ModerationNotice, rawText: string, observedAt = nowIso()): void {
    const key = messageKey(event.actor, `${event.action}:${event.target}:${rawText}`);
    if (this.moderationEvents.some((e) => e.event_key === key)) {
      return;
    }
    this.moderationEvents.push({
      id: this.nextModId++,
      event_key: key,
      actor: event.actor,
      target: event.target,
      action: event.action,
      observed_at: observedAt,
      raw_text: rawText,
    });
  }

  recordMicGrab(
    username: string,
    durationSeconds: number,
    startedAt = nowIso(),
    transcript?: string,
    room: RoomName = 'Players__Lounge',
    indexIntoMessages = false
  ): void {
    if (this.isSuppressed(username)) return;
    this.micGrabs.push({
      id: this.nextGrabId++,
      username,
      started_at: startedAt,
      duration_seconds: durationSeconds,
      transcript,
    });

    if (transcript && transcript.trim()) {
      this.audioTranscripts.push({
        id: this.nextTranscriptId++,
        speaker: username,
        transcript: transcript.trim(),
        duration_seconds: durationSeconds,
        observed_at: startedAt,
        room,
      });

      if (indexIntoMessages) {
        const timeStr = new Date().toLocaleTimeString('en-US', {
          hour: 'numeric',
          minute: '2-digit',
        });
        this.recordMessage(
          username,
          `[Mic Audio] ${transcript.trim()}`,
          timeStr,
          startedAt,
          room,
          false,
          false,
          'audio_transcript'
        );
      }
    }
  }

  userProfile(username: string): UserProfileResult | null {
    const cleaned = cleanUsername(username);
    if (!cleaned) return null;
    const user = this.users.get(cleaned.toLowerCase());
    if (!user) return null;

    const recentMessages = this.messages
      .filter((m) => m.username.toLowerCase() === cleaned.toLowerCase() && !m.is_bot_reply)
      .slice(-20)
      .reverse();

    const recentTranscripts = this.audioTranscripts
      .filter((t) => t.speaker.toLowerCase() === cleaned.toLowerCase())
      .slice(-10)
      .reverse();

    const wordCounts = new Map<string, number>();
    for (const row of recentMessages) {
      const matches = row.body.replace(/^\[Mic Audio\]\s*/i, '').match(WORD_RE) || [];
      for (const word of matches) {
        const w = word.toLowerCase();
        wordCounts.set(w, (wordCounts.get(w) || 0) + 1);
      }
    }
    for (const tr of recentTranscripts) {
      const matches = tr.transcript.match(WORD_RE) || [];
      for (const word of matches) {
        const w = word.toLowerCase();
        wordCounts.set(w, (wordCounts.get(w) || 0) + 1);
      }
    }

    let topWord = 'n/a';
    let topCount = 0;
    for (const [word, count] of wordCounts.entries()) {
      if (count > topCount) {
        topWord = word;
        topCount = count;
      }
    }

    return {
      ...user,
      messages: recentMessages.map((r) => r.body),
      transcripts: recentTranscripts.map((t) => t.transcript),
      top_word: topWord,
      top_count: topCount,
    };
  }

  micStats(username: string | null, seconds: number): [number, number] {
    const cutoffMs = Date.now() - seconds * 1000;
    let count = 0;
    let duration = 0;
    for (const grab of this.micGrabs) {
      const grabMs = Date.parse(grab.started_at);
      if (!Number.isNaN(grabMs) && grabMs < cutoffMs) continue;
      if (username && grab.username.toLowerCase() !== username.toLowerCase()) continue;
      count += 1;
      duration += grab.duration_seconds;
    }
    return [count, duration];
  }

  moderationHistory(action: string, target: string): ModerationEventRow[] {
    return this.moderationEvents
      .filter(
        (e) =>
          e.action.toLowerCase() === action.toLowerCase() &&
          e.target.toLowerCase() === target.toLowerCase()
      )
      .slice(-10)
      .reverse();
  }
}

export const ROOM_COMMANDS: Record<RoomName, string[]> = {
  Players__Lounge: ['!players', '!lounge', '!room info'],
  Drama_Central: ['!drama', '!central', '!showtime'],
  'Room List': ['!rooms', '!list', '!switch'],
};

export const ROOM_TRIGGERS: Partial<
  Record<RoomName, { trigger_words: string[]; response_template: string; action: string }>
> = {
  Players__Lounge: {
    trigger_words: ['game', 'play', 'match'],
    response_template: "@{user} Let's play some games in the lounge!",
    action: 'send_to_room',
  },
  Drama_Central: {
    trigger_words: ['drama', 'argument', 'fight'],
    response_template: '@{user} This is a drama central - keep it civil!',
    action: 'send_to_room',
  },
};

export class CamfrogBotEngine {
  store: CamfrogStore;
  settings: BotSettings;
  allowedModerationSenders: Set<string>;
  currentRoom: RoomName = 'Players__Lounge';
  activeSpeaker: string | null = 'Stonerwayne1000';
  private recentMessages: Array<[string, string]> = [];
  private pages: Map<string, string[]> = new Map();
  dissJobs: Map<string, number> = new Map();
  sentReplies: Array<{ recipient: string; text: string; dryRun: boolean; timestamp: string; room: RoomName }> = [];

  constructor(store?: CamfrogStore, settings?: Partial<BotSettings>) {
    this.store = store || new CamfrogStore(true);
    this.settings = { ...INITIAL_BOT_SETTINGS, ...settings };
    this.allowedModerationSenders = new Set(['skrach_ill_man_', 'nico1ee']);
  }

  handleMessage(senderRaw: string, text: string, roomTime?: string, room: RoomName = this.currentRoom): string[] {
    const sender = cleanUsername(senderRaw);
    const timeStr =
      roomTime ||
      new Date().toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
      });

    if (!sender || (this.store.isSuppressed(sender) && text.trim().toLowerCase() !== '!unsuppress')) {
      return [];
    }

    this.store.recordMessage(sender, text, timeStr, nowIso(), room, false, false);
    this.recentMessages.push([sender, text]);
    if (this.recentMessages.length > CHAT_HISTORY_LIMIT) {
      this.recentMessages.shift();
    }

    const moderation = detectModeration(text);
    if (moderation) {
      this.store.recordModeration(moderation, text);
      return [];
    }

    const replies = this.dispatch(sender, text, room);
    const delivered: string[] = [];
    for (const reply of replies) {
      if (this.sendReply(sender, reply, timeStr, room)) {
        delivered.push(reply);
      }
    }
    return delivered;
  }

  dispatch(sender: string, text: string, room: RoomName = this.currentRoom): string[] {
    const raw = text.trim();
    const normalized = raw.toLowerCase();

    if (raw === '-') {
      return this.nextPage(sender);
    }

    const historyMatch = HISTORY_RE.exec(raw);
    if (historyMatch && historyMatch.groups) {
      return this.historyReply(sender, historyMatch.groups.action.toLowerCase(), historyMatch.groups.target);
    }

    if (normalized === '!chat') {
      this.settings.chat_mode = true;
      return ['Chat mode is on.'];
    }

    if (normalized === '!chatoff' || normalized === '!chat off') {
      this.settings.chat_mode = false;
      this.dissJobs.clear();
      return ['Chat mode is off.'];
    }

    if (normalized === '!shutup') {
      this.settings.silent_mode = true;
      return ['Silent mode is on; I will keep monitoring without replying.'];
    }

    if (normalized === '!transcribe') {
      this.settings.transcription_mode = true;
      this.settings.continuous_audio_store = true;
      return ['Continuous audio transcription is ON; active speaker audio is transcribed and stored to user profiles.'];
    }

    if (normalized === '!transcribed') {
      this.settings.transcription_mode = false;
      this.settings.continuous_audio_store = false;
      return ['Continuous audio transcription is OFF.'];
    }

    if (normalized === '!suppress') {
      return [
        this.store.suppress(sender)
          ? 'Your stored profile was moved out of normal bot queries.'
          : 'Your profile is already suppressed.',
      ];
    }

    if (normalized === '!unsuppress') {
      return [
        this.store.unsuppress(sender)
          ? 'Your stored profile was restored.'
          : 'No recoverable suppressed profile was found.',
      ];
    }

    if (normalized.startsWith('!who is ')) {
      return this.whoIs(raw.slice(8).trim());
    }

    if (normalized.startsWith('!info on ')) {
      return this.infoOn(raw.slice(9).trim());
    }

    if (normalized.startsWith('!grabs')) {
      return this.grabs(raw.slice(6).trim());
    }

    if (normalized.startsWith('!idk ')) {
      const question = raw.slice(5).trim();
      return [`@${sender}, no answer engine is configured yet, so I cannot answer: ${question.slice(0, 220)}`];
    }

    if (normalized.startsWith('!say')) {
      const speechText = raw.slice(4).trim();
      if (!speechText) {
        return ['Usage: !say <phrase to broadcast over VB-Cable + Talk Button>'];
      }
      if (!this.settings.vb_cable_tts_enabled) {
        return ['VB-Cable TTS is currently disabled in runtime switches.'];
      }
      const estimatedSeconds = Math.max(2, Math.ceil(speechText.split(/\s+/).length * 0.45));
      if (typeof window !== 'undefined' && 'speechSynthesis' in window && !this.settings.silent_mode) {
        try {
          window.speechSynthesis.cancel();
          const utter = new SpeechSynthesisUtterance(speechText);
          window.speechSynthesis.speak(utter);
        } catch {
          // Ignore browser speech synthesis errors
        }
      }
      return [
        `[VB-Cable TTS -> ${this.settings.vb_cable_device_name}] Holding Talk Button(50000) at (1326, 1182) for ~${estimatedSeconds}s: "${speechText.slice(0, 160)}"`,
      ];
    }

    if (normalized.startsWith('!diss')) {
      const target = cleanUsername(raw.slice(5).trim()) || 'the room';
      this.dissJobs.set(target, Date.now());
      return [`Light roast mode is on for ${target}; !chatoff stops it.`];
    }

    if (normalized === '!happy' || normalized === '!sad' || normalized === '!mad') {
      if (!this.settings.chat_mode) {
        return ['Turn on chat mode first with !chat.'];
      }
      const nextTone = normalized.slice(1) as 'happy' | 'sad' | 'mad';
      this.settings.tone = nextTone;
      return [`Tone set to ${nextTone}.`];
    }

    if (normalized === '!triggers' || normalized === '!help') {
      return [
        'Triggers: !chat, !chatoff, !shutup, !transcribe, !transcribed, !suppress, !unsuppress, !who is, !info on, !grabs, !idk, !diss, !say, moderation history, and - for next page.',
      ];
    }

    if (room === 'Players__Lounge' && (normalized === '!players' || normalized === '!lounge' || normalized === '!room info')) {
      return [`[Players__Lounge] Active roster: ${this.store.users.size} tracked users in UIA List(50008).`];
    }
    if (room === 'Drama_Central' && (normalized === '!drama' || normalized === '!central' || normalized === '!showtime')) {
      return [`[Drama_Central] Moderation monitor active (${this.store.moderationEvents.length} logged notices).`];
    }
    if (room === 'Room List' && (normalized === '!rooms' || normalized === '!list' || normalized === '!switch')) {
      return [`Available UIA tabs: Room List (1390, 50), Players__Lounge (1550, 50).`];
    }

    const nativeMatch = /^!(unpunish|unblockmic|unban|topic|watchlist)\s+(.+)$/i.exec(raw);
    if (nativeMatch) {
      return this.nativeModeration(sender, nativeMatch[1].toLowerCase(), nativeMatch[2].trim());
    }

    if (normalized.includes('kaekae') && this.settings.chat_mode) {
      const context = this.recentMessages.length > 0 ? this.recentMessages[this.recentMessages.length - 1][1] : '';
      return [`@${sender}, I'm here. I caught: ${context.slice(0, 180)}`];
    }

    const roomTrigger = ROOM_TRIGGERS[room];
    if (roomTrigger && this.settings.chat_mode) {
      for (const word of roomTrigger.trigger_words) {
        if (normalized.includes(word)) {
          return [roomTrigger.response_template.replace('{user}', sender)];
        }
      }
    }

    return [];
  }

  private nativeModeration(sender: string, action: string, argument: string): string[] {
    if (!NATIVE_MODERATION_COMMANDS.has(action)) {
      return [];
    }
    if (!this.allowedModerationSenders.has(sender.toLowerCase())) {
      return ['Native moderation commands are disabled until an operator is added to MODERATION_ALLOWED_SENDERS.'];
    }
    return [`/${action} ${argument}`.trim()];
  }

  private whoIs(usernameRaw: string): string[] {
    const username = cleanUsername(usernameRaw);
    const profile = this.store.userProfile(username);
    if (!profile) {
      return [`No stored profile for ${username || 'that user'}.`];
    }
    const samples = profile.messages.slice(0, 3);
    const sampleText = samples.length > 0 ? samples.join(' | ') : 'no saved chat yet';
    const voiceNote =
      profile.transcripts.length > 0 ? ` | Latest mic audio: "${profile.transcripts[0]}"` : '';
    return [
      `${profile.username}: seen since ${profile.first_seen}; ${profile.message_count} messages. Recent chat: ${sampleText}${voiceNote}`,
    ];
  }

  private infoOn(usernameRaw: string): string[] {
    const username = cleanUsername(usernameRaw);
    const profile = this.store.userProfile(username);
    if (!profile) {
      return [`No stored statistics for ${username || 'that user'}.`];
    }
    const [grabs, seconds] = this.store.micStats(profile.username, 24 * 3600);
    return [
      `${profile.username}: ${profile.message_count} messages; top word '${profile.top_word}' (${profile.top_count}x); ${grabs} mic grabs / ${Math.round(seconds)}s in 24h.`,
    ];
  }

  private grabs(argumentsRaw: string): string[] {
    const parts = argumentsRaw.split(/\s+/).filter(Boolean);
    const durationMap: Record<string, number> = {
      '5m': 300,
      '30m': 1800,
      '1h': 3600,
      '24h': 86400,
      '72h': 259200,
    };
    let username: string | null = null;
    let seconds = 86400;
    for (const part of parts) {
      const lower = part.toLowerCase();
      if (lower in durationMap) {
        seconds = durationMap[lower];
      } else {
        username = cleanUsername(part) || username;
      }
    }
    const [count, duration] = this.store.micStats(username, seconds);
    const label = username || 'room';
    return [
      `Mic grabs for ${label}: ${count} grabs, ${Math.round(duration)}s over the last ${Math.floor(seconds / 60)} minutes.`,
    ];
  }

  private historyReply(requester: string, action: string, targetRaw: string): string[] {
    const target = cleanUsername(targetRaw);
    if (!target) return [];
    const rows = this.store.moderationHistory(action, target);
    if (rows.length === 0) {
      return [`No ${action} record for ${target}.`];
    }
    const lines = rows.map((row) => `${row.observed_at}: ${row.actor} ${row.action} ${row.target}`);
    return this.paginate(`Moderation history for ${target}`, lines, requester);
  }

  private paginate(title: string, lines: string[], recipient: string): string[] {
    const pages: string[] = [];
    let current = title;
    for (const line of lines) {
      const candidate = `${current}\n${line}`;
      if (candidate.length > MAX_CHAT_MESSAGE_LENGTH && current !== title) {
        pages.push(current);
        current = `${title}\n${line}`;
      } else {
        current = candidate;
      }
    }
    pages.push(current);
    this.pages.set(recipient.toLowerCase(), pages.slice(1));
    return pages.slice(0, 1);
  }

  private nextPage(sender: string): string[] {
    const queue = this.pages.get(sender.toLowerCase());
    if (!queue || queue.length === 0) {
      return ['No queued page for you.'];
    }
    const nextMessage = queue.shift()!;
    if (queue.length === 0) {
      this.pages.delete(sender.toLowerCase());
    }
    return [nextMessage];
  }

  sendReply(recipient: string, message: string, roomTime: string, room: RoomName): boolean {
    if (this.settings.silent_mode && !message.startsWith('Silent mode is on')) {
      return false;
    }
    const chunks = CamfrogBotEngine.splitForChat(message);
    for (const page of chunks) {
      this.sentReplies.push({
        recipient,
        text: page,
        dryRun: this.settings.dry_run,
        timestamp: roomTime,
        room,
      });
      this.store.recordMessage(
        'kaekae_bot',
        this.settings.dry_run ? `[dry-run -> ${recipient}] ${page}` : page,
        roomTime,
        nowIso(),
        room,
        true,
        this.settings.dry_run
      );
    }
    return true;
  }

  static splitForChat(message: string): string[] {
    const text = String(message).trim();
    if (!text) return [''];
    const chunks: string[] = [];
    for (let i = 0; i < text.length; i += MAX_CHAT_MESSAGE_LENGTH) {
      chunks.push(text.slice(i, i + MAX_CHAT_MESSAGE_LENGTH));
    }
    return chunks;
  }
}

export interface TestCaseResult {
  name: string;
  description: string;
  passed: boolean;
  details: string;
}

export function runOfflineBotTests(): TestCaseResult[] {
  const results: TestCaseResult[] = [];

  // Test 1: test_records_message_and_serves_info
  try {
    const store = new CamfrogStore(false);
    const bot = new CamfrogBotEngine(store, { dry_run: false });
    bot.handleMessage('Alice_1', 'Python Python testing', '1:00 PM');
    const profile = store.userProfile('Alice_1');
    const msgCountOk = profile !== null && profile.message_count === 1;
    bot.handleMessage('Alice_1', '!info on Alice_1', '1:01 PM');
    const infoSent = bot.sentReplies.some((r) => r.text.includes('Alice_1: 2 messages') && r.text.includes("top word 'python' (2x)"));
    results.push({
      name: 'test_records_message_and_serves_info',
      description: 'Records UIA message, computes word frequency, and responds to !info on <user>',
      passed: Boolean(msgCountOk && infoSent),
      details: bot.sentReplies[0]?.text || 'No reply emitted',
    });
  } catch (err) {
    results.push({
      name: 'test_records_message_and_serves_info',
      description: 'Records UIA message, computes word frequency, and responds to !info on <user>',
      passed: false,
      details: String(err),
    });
  }

  // Test 2: test_suppression_can_be_reversed_by_the_same_user
  try {
    const store = new CamfrogStore(false);
    const bot = new CamfrogBotEngine(store, { dry_run: false });
    bot.handleMessage('Alice_1', 'A stored line', '1:00 PM');
    bot.handleMessage('Alice_1', '!suppress', '1:01 PM');
    const isSuppressedAfterSuppress = store.isSuppressed('Alice_1') && store.userProfile('Alice_1') === null;
    bot.handleMessage('Alice_1', '!unsuppress', '1:02 PM');
    const isRestoredAfterUnsuppress = !store.isSuppressed('Alice_1') && store.userProfile('Alice_1') !== null;
    results.push({
      name: 'test_suppression_can_be_reversed_by_the_same_user',
      description: 'Moves user data to non-queryable vault on !suppress and restores on !unsuppress',
      passed: Boolean(isSuppressedAfterSuppress && isRestoredAfterUnsuppress),
      details: `suppressed=${isSuppressedAfterSuppress}, restored=${isRestoredAfterUnsuppress}`,
    });
  } catch (err) {
    results.push({
      name: 'test_suppression_can_be_reversed_by_the_same_user',
      description: 'Moves user data to non-queryable vault on !suppress and restores on !unsuppress',
      passed: false,
      details: String(err),
    });
  }

  // Test 3: test_moderation_parser_rejects_prose
  try {
    const valid = detectModeration('Mod_1 unbanned User_2');
    const validMatch =
      valid !== null && valid.actor === 'Mod_1' && valid.target === 'User_2' && valid.action === 'unbanned';
    const proseRejected = detectModeration('Please do not ban User_2') === null;
    results.push({
      name: 'test_moderation_parser_rejects_prose',
      description: 'Parses strict Camfrog moderation notices while rejecting conversational prose',
      passed: Boolean(validMatch && proseRejected),
      details: `valid=${JSON.stringify(valid)}, proseRejected=${proseRejected}`,
    });
  } catch (err) {
    results.push({
      name: 'test_moderation_parser_rejects_prose',
      description: 'Parses strict Camfrog moderation notices while rejecting conversational prose',
      passed: false,
      details: String(err),
    });
  }

  // Test 4: test_ui_text_is_not_guessed_as_a_username + ignored ListItem rects
  try {
    const clockRejected = cleanUsername('8:13 AM') === '';
    const toolbarRejected = cleanUsername('GIFTUsers2') === '';
    const ignoredRectRejected = cleanUsername('SomeHeader', [2303, 141, 2559, 163]) === '';
    const validAccepted = cleanUsername('Alice_1', [2303, 240, 2559, 262]) === 'Alice_1';
    results.push({
      name: 'test_ui_text_and_ignored_listitem_rects_filtered',
      description:
        'Filters clock strings, GIFTUsers2, and ignored User List ListItem(50007) rects [t=141..163, 207..229, 867..889]',
      passed: Boolean(clockRejected && toolbarRejected && ignoredRectRejected && validAccepted),
      details: `ignoredRect(2303,141,2559,163)="${cleanUsername('SomeHeader', [2303, 141, 2559, 163])}", valid="Alice_1"`,
    });
  } catch (err) {
    results.push({
      name: 'test_ui_text_and_ignored_listitem_rects_filtered',
      description:
        'Filters clock strings, GIFTUsers2, and ignored User List ListItem(50007) rects [t=141..163, 207..229, 867..889]',
      passed: false,
      details: String(err),
    });
  }

  return results;
}
