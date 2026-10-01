# CHANGES — KaeKae Bot, Phase 1-7 rework

Every change below is applied and compiles. Verification status per item is in
`TEST_RUNBOOK.md`; faults go in `FAULTS.md`.

Baseline commit: `bc1d29f` (pre-change originals also kept in `_presync_backup/`).
Pre-evaluation build snapshot: `_prefeval_backup/` (11 files).

---

## The root-cause bugs that made the bot "not work fluidly"

| # | Bug | Why it hurt | Fix |
|---|---|---|---|
| **R1** | `ocr_scan_camfrog_chat()` dereferenced `state.watching_ocr_enabled`, `state.ocr_paused_until`, `state.last_ocr_time` — **none of which existed** in `BotState.__init__` | `AttributeError` on **every** main-loop iteration, caught by the loop's `except` → `[MAIN LOOP ERROR]` + traceback + 2 s sleep. The loop crawled and spammed errors. | Function deleted entirely (211 lines) |
| **R2** | `state.ocr_recent_events_cache` (2 sites) had been renamed to `mod_recent_events_cache` | Second `AttributeError` whenever a moderation keyword appeared in chat | References corrected |
| **R3** | `pytesseract` referenced but never imported | `NameError` on the legacy mic path | Legacy path deleted |
| **R4** | `kaekae/kaekae_toad` were in `IGNORED_NAMES`, so the probe **filtered out the bot's own name** | `verify_bot_won_mic()` could *never* see our own name → always "didn't confirm clean name display" | Bot names removed from the ignore list; separate `is_bot_name()` / `is_unknown_speaker()` helpers |
| **R5** | `verify_bot_won_mic` had a fallback that reported success from local flags | Verified nothing; produced false "grabbed" results | Fallback deleted; **our name must hold the speaker slot a full 1.0 s** |
| **R6** | `locked_update()` locked, then `read_json()` locked the **same** file again — Windows `_locking()` refuses a same-process re-lock | **Every store operation stalled the full 8 s timeout** — the bot would appear frozen | `FileLock` is now re-entrant per process (100 claims now take 0.16 s) |

---

## Phase 1 — OCR removed completely

- `kaekae_bot.py`: deleted `ocr_scan_camfrog_chat()` (211 lines) + call site,
  `get_talk_button_region()`, `check_talk_button_state_fast()` (used an
  unimported `pytesseract`), the legacy calibrated-hold body of
  `speak_on_camfrog_microphone()`, `OCR_MIN/MAX/PAUSE_*`, all `OCR_*` state.
- `cef_probe.py`: deleted `query_speaker_micro_roi()` (screenshot + Tesseract
  speaker guessing), its pipeline stage, and the `pytesseract`/`PIL` imports.
- `calibrate_camfrog.py`: OCR region capture removed; **`run_calibration_wizard`
  alias added** (both `--calibrate` and the diagnostics menu called a function
  that did not exist). `calibrate.py` deleted (unreferenced OCR wizard).
- **Result: OCR grep across all `*.py` returns zero hits.** CEF/UIA is the only
  source of chat and speaker information.

## Phase 2 — Truthful mic state + verified grab

- Tri-state `mic_state()` → `free` / `busy(name)` / `held_by_bot` /
  `unconfirmable`. Unknown is **no longer** treated as free.
- Mic battle = **name-change rate** (≥3 flips), not "2 names seen in 2 s", so
  two people talking one after the other is not a battle.
- `verify_bot_won_mic()` → structured verdict, requires our name stable for
  `talk_stable_seconds` (1.0 s), **no success fallback**.
- **New `acquire_talk()`** — rapidly re-presses Talk, rotating patterns
  (`mouse_hold → cef_hwnd → uia → f10`) with 30-90 ms jitter, until our name
  holds the speaker slot. On timeout: always releases, returns
  `{ok:false, attempts, patterns, observed_speaker, reason}`. Hands-free
  toggling is excluded (it latches).
- `release_mic()`: unconditional `mouseUp()` (no-args, survives cursor drift) +
  always `WM_LBUTTONUP`; hands-free clicked **only** if that is the method used.
- `speak_and_hold()` → `{ok, acquired, playback_ok, engine, observed_speaker,
  stability_seconds, attempts, method, reason}`; **aborts the broadcast** on a
  failed grab; always releases in `finally`.
- Windows named mutex `Global\KaeKaeTalkLock` + `talk_state.json` mirror so T1
  and T2 can never hold Talk simultaneously.
## Phase 3 — One ingestion path, durable claims

- **New `claim_and_dispatch()`** is the single entry point: validate sender →
  claim → *then* record and dispatch. `record_chat_message()` and
  `process_chat_message()` are now reachable **only** through it.
- Signature is **timestamp-free** (`room|sender|normalized text`) and persisted
  to `dedupe_claims.json` **before** dispatch, so a message left on screen cannot
  fire twice — and survives a restart. Old `recent_signatures` are no longer
  saved or restored.
- Control commands made **idempotent**: `!transcribe`, `!transcribed`,
  `!listen`, `!mute` announce only on an actual state change.

## Phase 4 — Durable one-hour no-repeat gate

- `claim_or_suppress(kind, text)` over `outbound_gate.json`,
  `dup_reply_seconds = 3600`, shared by **chat sends and mic speech**.
- Timestamped control confirmations (`(09/30I22:14:05) Listening is ON.`) and
  `[CEF Talk]`/`[Mic Broadcast]` notices bypass the gate so commands always
  answer.
- Checked **after** the Camfrog window attaches, so a failed attach never burns
  the claim.

## Phase 5 — One config, one voice/persona/brain

- `synthesize_speech_to_wav()` honours `engine` explicitly
  (`qwen -> elevenlabs -> edge -> system`) and returns **which** engine produced
  the audio, or `""`. The old 587 Hz sine tone is **gone** — it is no longer
  reported as speech.
- New `synthesize_with_qwen()` (warm model singleton), `synthesize_with_edge()`,
  `synthesize_with_system()`.
- `query_local_llm()` uses `brain_model` / `brain_fallback` /
  `brain_timeout_s` (cold-load allowance) / `brain_keep_alive` / `ollama_url`
  instead of hardcoded `llama3.2`.
- `!say` enqueues for Terminal 2 instead of blocking the chat loop, carrying the
  saved persona/voice/rate/pitch.
- Diagnostics **option [7]** = Voice/Engine/Persona picker that **persists** to
  `config.json` (engines, 9 Qwen speakers, 3 ElevenLabs personas, API key,
  synth-only test).

## Phase 6/7 — Terminal split, single writers, durability

- **T1 `chat_worker.py`** = the only process that types in the chat box; drains
  `chat_outbox.jsonl` (from T2/T3) and `command_inbox.jsonl` (silent T3 console,
  same claim path as chat).
- **T2 `audio_worker.py`** rewritten: consumes `broadcast_queue.json`, applies
  the mic gate, prints the **real** broadcast result, starts the CEF probe,
  adopts T1's control flags from `bot_state.json`, publishes heartbeats, sets
  `CHAT_SEND_MODE = "outbox"`.
- **T3 `master_dashboard.py`** rewritten: HUD shows real liveness (heartbeats),
  real room/speaker/diss state, engine + queue + gate counts; console is
  `[1] Speak  [2] Voice/Engine  [3] Send command  [4] Grab/Release  [5] Stop
  transcription`. All writes go through `kaekae_core`.
- **Queue schema collision fixed**: `pending_speech_queue.json` held *both* STT
  audio-backlog entries and broadcast tasks, and T2's consumer popped index 0
  blindly — silently destroying backlog entries. Broadcasts now use a separate
  `broadcast_queue.json`; `!mo` pagination moved to shared `pagination.json`.
- Heartbeats (`terminal_heartbeats.json`) replace the hardcoded `ACTIVE` HUD
  lines; HUD keys that were read but never written are now persisted.

## Shared foundation — `kaekae_core.py`

Anchored paths (`KAEKAE_HOME`), cross-process `FileLock` + atomic
`write_json_atomic` + `locked_update`, `load_config`/`save_config`,
`claim_or_suppress`, `claim_message`/`make_chat_signature`, telemetry
`log_event`, heartbeats, talk-state mirror, broadcast queue, chat outbox,
command inbox, shared pagination.

## Step C — test harness closed

- `cef_eval.py --observe` (read-only capture), `--replay` (proves one-dispatch;
  runs in a throwaway store and verifies the real store is untouched),
  `--talktest` (traced verified grab).
- `cef_explorer.py` now uses `acquire_talk()` and reports the real engine and a
  split *audio played* vs *mic verified* result.
- `Master Triggers & Command List.txt` and the in-chat `!triggers` output
  rebuilt against the real handlers (all 9 tones, missing commands, and the new
  repeat-protection rules).
- `_test_core.py` (31 checks) made **hermetic** — it previously wrote to the
  live `config.json`; it now runs in a scratch store.