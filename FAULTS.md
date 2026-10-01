# FAULTS — KaeKae bot test ledger

**If something has gone badly wrong, get back to a working build first:**
`rollback.bat list` → `rollback.bat verify` → then level `1`, `2` or `3`.
Copies of both backup folders also live outside the project at
`C:\Users\newbe\AIBot_rollback\`.

**How to use this file**

1. Run one test from `TEST_RUNBOOK.md`.
2. Record the result in the tracker below — one line, even when it PASSES.
3. If it failed: run `snapshot.bat <label>`, then add an entry at the bottom
   using the template.
4. Come back any time: this file + the `runs/` folder are the whole story.

**Copy/paste fault template**

```
### F-___ | <date> <time> | <Layer/step> | OPEN
Symptom  : (paste the VERBATIM console text - do not paraphrase)
Test     : <runbook step id>  -> <what you did>
Expected : <one line>
Actual   : <one line>
Evidence : runs\<folder printed by snapshot.bat>
Log file : logs\<the one .jsonl that answers it>  (claim/gate/talk/broadcast)
Suspect  : <file:line or subsystem>
Fix      : <what was changed, or blank>
Status   : OPEN | FIXED | WON'T-FIX | NOT-A-BUG
```

---

## Test tracker

Fill a row after **each** step. Do not start the next step until the row is
filled in.

| Step | What it proves | Date run | Result | Snapshot folder | Fault ID |
|---|---|---|---|---|---|
| L0 | Static: compile + 0 OCR + 31 core tests | 2026-09-30 | **PASS** | — | — |
| L1 | Voice engine synthesis only | | | | |
| L2 | CEF read-only capture (`--observe`) | | | | |
| L3 | Replay: exactly one dispatch (`--replay 300`) | 2026-09-30 | **PASS** (900 attempts -> 3 dispatches, store untouched) | synthetic fixture | — |
| L4 | Live dedupe: same text twice, restart persistence | | | | |
| L5 | Idempotent controls (`!transcribe` x2) | | | | |
| L6 | **Verified mic grab** (the quoted bug) | | | | |
| L7 | Broadcast + one-hour gate | | | | |
| L8 | Cross-terminal (T3 console, outbox, inbox) | | | | |
| L9 | Failure modes (T2 down, T1 down) | | | | |

---

## Telemetry map — which file answers which symptom

| Symptom you observed | Open this file |
|---|---|
| "It answered the same message twice" | `logs/claim_<date>.jsonl` — one line per candidate, `granted: true/false` |
| "It repeated a reply it already said" | `logs/gate_<date>.jsonl` — `decision: allow/suppress` + `age_s` |
| "Mic grab failed / said grabbed but nobody heard it" | `logs/talk_<date>.jsonl` — every press, pattern, observed speaker, stability, outcome |
| "It spoke with the wrong voice" | `logs/broadcast_<date>.jsonl` — `engine`, `playback_ok`, `reason` |
| "Who queued that message?" | `logs/broadcast_enqueue_<date>.jsonl`, `logs/chat_outbox_<date>.jsonl` |
| "Who is holding the mic right now?" | `talk_state.json` |
| "Which terminals are actually alive?" | `terminal_heartbeats.json` |
| "Is the bot muted / is transcription on?" | `bot_state.json` |

---

## Open faults

_(none yet — add entries below this line using the template)_