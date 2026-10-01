# TEST RUNBOOK — one step at a time

Rules: **do not start step N+1 until step N is recorded in `FAULTS.md`.**
After every step: `snapshot.bat L<n>-<shortname>` and copy the printed path
into the tracker row.

Run everything from `c:\Users\newbe\AIBot`.

---

## L0 — Static, no Camfrog needed (~2 min)

```bat
python _test_core.py
python -m py_compile kaekae_bot.py cef_probe.py cef_explorer.py cef_eval.py kaekae_core.py audio_worker.py chat_worker.py master_dashboard.py launch_kaekae.py calibrate_camfrog.py
powershell -NoProfile -Command "Get-ChildItem *.py | Select-String -Pattern 'pytesseract|ImageEnhance|query_speaker_micro_roi|ocr_scan_camfrog_chat|watching_ocr|screenshot'"
```
**PASS** = 31/31 core tests, compile clean, and the OCR grep prints **nothing**.

## L1 — Voice engine only (~1 min, no Camfrog)

```bat
python cef_probe.py
```
`[7]` Voice/Engine selector -> `[8]` Test the currently saved voice.
**PASS** = it names the engine (`qwen` or `edge`/`system`) and writes a WAV.
*First Qwen run loads the model (~5 s) and synthesises (~18 s) on CPU.*

## L2 — CEF read-only capture (~5 min, **Camfrog must be open**)

```bat
python cef_eval.py --observe --minutes 5
```
From a second account: post 2-3 chat lines and one `!transcribe`, leave them on
screen; talk on the mic for ~5 s.
**PASS** = messages + senders land in `logs/parse_*.jsonl`, speaker samples in
`logs/speaker_*.jsonl`, **and the bot sends nothing at all**.
Note in the tracker how many times each message repeats in `parse_*.jsonl`
(`times_seen_this_run`) — that count *is* your duplicate-trigger problem.

## L3 — Prove one dispatch (offline, uses the L2 capture)

```bat
python cef_eval.py --replay logs\dom_<timestamp>.jsonl --loops 300
```
**PASS** = `dispatches granted == expected` and `real claim store safe: YES`.
*(Already validated on a synthetic capture: 900 attempts -> 3 dispatches.)*

## L4 — Live dedupe + restart persistence (~5 min)

1. Post `!transcribe` once. Wait for the single ack.
2. Leave it on screen 60 s — it must **not** re-ack.
3. Post the same text twice from two accounts — both handled.
4. **Restart T1** with the messages still on screen — nothing re-fires.

**PASS** = one ack in 2, nothing after restart.
Evidence: `logs/claim_<date>.jsonl` (`granted` count should match what you typed).

## L5 — Idempotent controls (~2 min)

`!transcribe` twice, then `!listen` twice, then `!mute` twice.
**PASS** = each announces **once**; the repeat is silently suppressed.

## L6 — Verified mic grab (~5 min, **the quoted bug**)

Quiet room first, then with someone else talking.

```bat
python cef_probe.py     -> option [2]
```
(or `python cef_eval.py --talktest --attempts 3`)

**PASS** = `OUTCOME: CONFIRMED`, `observed speaker` = a KaeKae name,
`name stability >= 1.0s`.
**On failure you should see** `FAILED - timeout: KaeKae's name never held the
speaker slot`, with the mic auto-released — *not* a false "Grabbed".
Evidence: `logs/talk_<date>.jsonl`.

## L7 — Broadcast + one-hour gate (~5 min)

From chat: `!say "KaeKae test broadcast one"`. Then repeat the identical text.
**PASS** = first broadcast speaks and releases; the second is
`Gate: suppressed repeat within past hour`, mic never grabbed.
Evidence: `logs/gate_<date>.jsonl` + `logs/broadcast_<date>.jsonl`.

## L8 — Cross-terminal (~10 min)

```bat
python launch_kaekae.py
```
- T3 `[1]` speak -> T2 broadcasts it.
- T3 `[2]` pick a voice/persona -> then `!say` from chat uses the new voice.
- T3 `[3]` `!who` -> T1 answers **in chat, silently** (no chatroom spam).
- T3 `[4]` grab -> honest verdict with attempts/speaker/stability.
- T3 `[5]` stop transcription -> sticks in T1 **and** T2 (T2 prints
  "Adopted control state from Terminal 1").
**PASS** = HUD shows T1/T2 ONLINE, real room + speaker, engine + queue count.

## L9 — Failure modes (~5 min)

1. Close T2, then `!say "..."` from chat -> queued, not lost; no crash.
2. Restart T2 -> queued item is spoken.
3. Close T1 -> T3 `[5]` shows T1 OFFLINE in the HUD.
Evidence: `logs/broadcast_enqueue_<date>.jsonl`, `terminal_heartbeats.json`.

---

## Rollback, three levels

| Level | Action |
|---|---|
| One file broke | `git checkout -- <file>` |
| Whole build suspect | copy from `_prefeval_backup\` |
| Everything wrong | copy from `_presync_backup\` (originals) |