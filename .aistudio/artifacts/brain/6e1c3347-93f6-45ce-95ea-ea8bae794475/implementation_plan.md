# Dedicated Clone Mode & Live Speaker Audio Hijack Architecture

A dual-mode operational architecture that safely isolates live speaker voice cloning from regular room automation, automatically captures Camfrog microphone audio when a speaker is detected, generates an XTTS-v2 voice clone, and seamlessly returns to regular mode with the new voice active.

---

## User Review & Critical Decisions

> [!IMPORTANT]
> Based on your direct answers in the planning interview, the implementation is grounded on three confirmed operational pillars:
> 1. **Dedicated Clone Mode with Safe State Toggle**: The bot will feature a top-level dual-mode state machine (`REGULAR_BOT_MODE` vs `ONE_CLICK_DEPLOY_CLONE`). Engaging Clone Mode automatically and safely suspends background auto-spins and non-critical chat dispatches so audio bandwidth and GPU compute are dedicated to cloning.
> 2. **Automatic Active Speaker Mic Audio Hijack**: Rather than requiring manual button timing, Clone Mode arms an automatic listener on `SPEAKER_ON_MIC` (`[1506, 1174, 1548, 1190]`). The moment any user grabs the Camfrog microphone, the pipeline immediately captures an optimal 4.5-second audio sample from the live room stream.
> 3. **Automatic Return to Regular Mode with Loaded Clone**: Upon clone generation, the bot automatically assigns the new voice profile (e.g. `Active Clone: <SpeakerName>`), switches the active TTS engine to Coqui XTTS-v2, and restores Regular Bot Mode with all room listeners and auto-spinners unpaused.

---

## 1. Overview & Core Concept

Currently, voice cloning requires manual multi-step interactions (`Sample` &rarr; `Clone Voice` &rarr; `Default`), which can clash with auto-spin cooldowns, continuous chat listeners, and unpredictable speaker turn-taking in live Camfrog rooms.

This architecture introduces an **atomic Dual-Mode State Machine**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        REGULAR BOT MODE (Default)                       │
│  - Silent Room Listener active on Players__Lounge                      │
│  - 20 KaeKae_Toad triggers responsive                                  │
│  - Optional Auto-Spin running (20.2s or 1-3m Random)                   │
│  - Speech broadcasts play using currently selected voice               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Operator clicks
                                    │ "🎙️ ONE-CLICK DEPLOY CLONE"
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   ONE-CLICK DEPLOY CLONE MODE (Armed)                  │
│  - Safely suspends auto-spin timers & outgoing speech to avoid overlap │
│  - Focuses audio capture on ACTIVE_SPEAKER_RECT                       │
│  - Waits for next user to grab microphone in Camfrog                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Speaker detected!
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               AUTOMATIC SPEAKER AUDIO HIJACK & EMBEDDING               │
│  - Samples 4.5s clean audio chunk from live room loopback stream       │
│  - XTTS-v2 extracts speaker latent embeddings & verifies SNR           │
│  - Creates named voice profile: `Active Clone: <SpeakerName>`          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Clone Complete
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 AUTOMATIC RESTORATION TO REGULAR MODE                  │
│  - Active TTS voice automatically set to the new clone                 │
│  - Restores regular mode, auto-spin readiness & room interactions      │
│  - Bot is immediately ready to speak in the cloned speaker's voice!    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. User Experience & Visual Design

### Top Bar & Dual-Mode Controls Alignment
- **Top Bar Dual-Mode Segment**:
  - `⚡ REGULAR BOT MODE` (active by default, emerald border/badge).
  - `🎙️ ONE-CLICK DEPLOY CLONE` (prominent amber/purple action button).
- **Clone Pipeline Visual Ribbon**:
  - When Clone Mode is active, an illuminated live pipeline stage indicator appears below the top bar:
    - `STAGE 1: ARMED` (Waiting for speaker to grab mic...)
    - `STAGE 2: RECORDING` (Live wave peak meter sampling speaker audio...)
    - `STAGE 3: EXTRACTING` (Synthesizing XTTS latent voice vector...)
    - `STAGE 4: DEPLOYED` (Returning to regular bot mode with voice ready!)
- **Terminal 3 (Live Audio & Voice Clone Stream)**:
  - Real-time logging of capture duration, sample rate (24,000 Hz), speaker name identification, signal-to-noise ratio (SNR), and voice assignment.
- **Voice Engine Dropdown Sync**:
  - Automatically adds newly created clones to the voice catalog (`Active Clone: Stonerwayne1000`, `Active Clone: Rosie`, etc.) so operators can switch between multiple captured voices at any time.

---

## 3. Key Product Decisions & Implementation Logic

### Decision 1: Safe State Preservation
- **Behavior**: Entering Clone Mode pauses `autoSpinEnabled` and `countdownTimerId` without wiping session profit, total spins, or pity streaks. Exiting Clone Mode cleanly resumes the exact state.
- **Why**: Prevents wheel spins or bot speech from firing into the room while sampling or overloading the GPU during XTTS embedding generation.

### Decision 2: Speaker Hijack Detection & Validation
- **Behavior**: Uses the existing active speaker detector (`ACTIVE_SPEAKER_RECT [1506, 1174, 1548, 1190]`). If an operator triggers Clone Mode while someone is already speaking, capture starts immediately. If the mic is free, the listener waits in "Armed" state until someone begins speaking.
- **Why**: Eliminates manual button coordination so the operator never misses a quick 4-second mic grab.

### Decision 3: Fallback & Cancel Affordance
- **Behavior**: Includes a `"Cancel Clone / Return to Normal"` button at any point during Clone Mode so operators can abort if a speaker leaves or if they decide not to clone.

---

## 4. Technical Architecture & Component Mapping

```
┌────────────────────────────────────────────────────────────────────────┐
│                              botStore.ts                               │
│  State Machine:                                                        │
│    - appMode: 'REGULAR' | 'CLONE_ARMED' | 'CLONE_SAMPLING' | 'CLONE_PROCESSING'
│    - cloneState: { armed: boolean, targetSpeaker: string, stage: string }
│    - savedRegularState: { autoSpinWasEnabled: boolean }               │
│                                                                        │
│  Methods:                                                              │
│    - enterCloneMode(): pauses auto-spins, sets appMode to 'CLONE_ARMED' │
│    - triggerSpeakerHijack(speakerName): captures audio & processes     │
│    - finishCloneAndResume(cloneVoiceName): sets voice & resumes        │
│    - cancelCloneMode(): restores savedRegularState                     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
┌──────────────┐             ┌──────────────┐             ┌──────────────┐
│  TopBar.tsx  │             │ HudBar.tsx   │             │ InputLines.tsx
│ - Dual-mode  │             │ - Mode badge │             │ - Voice list │
│   toggle     │             │ - Speaker    │             │   with new   │
│ - Cancel btn │             │   status     │             │   clones     │
└──────────────┘             └──────────────┘             └──────────────┘
```

---

## 5. Verification & Testing Steps

1. **Verify State Transition**: Press `🎙️ ONE-CLICK DEPLOY CLONE` while Auto-Spin is running; verify auto-spin safely pauses and countdown halts without resetting wallet/jackpot counters.
2. **Verify Mic Audio Hijack**: When a speaker appears on mic, verify Clone Mode automatically locks onto their name and triggers audio sampling.
3. **Verify XTTS Latent Generation**: Verify Terminal 3 logs the 24kHz waveform processing, latency, and embedding completion.
4. **Verify Auto-Return**: Confirm the bot automatically re-enters Regular Bot Mode with the new clone selected in Line 3 and resumes room operations seamlessly.
5. **Verify Compilation & Linting**: Run `compile_applet` and `lint_applet` to ensure zero TypeScript or bundling issues.
