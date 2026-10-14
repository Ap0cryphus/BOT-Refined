# KaeKae_Toad & PepeFrog Supreme Command

A high-performance React application rewritten from the desktop automation suite for **Camfrog (Players__Lounge)** and **PepeFrog / publicaccess.tv** game optimization.

## Core Features Preserved

1. **Automatic Silent Room Listening & Live Monitoring**:
   - Boots in silent mode (`auto_spin_enabled = false`) without disrupting active rooms.
   - Monitors live room chatter, user joins/quits, and `SPEAKER_ON_MIC` tracking.
   - Enhanced SQLite 5.1/5.2 psychometric profiling (top nouns, sentiment scores, speech cadence, biographies).

2. **20 KaeKae_Toad Contextual Triggers**:
   - `kaekae <message>`: 5-compartment contextual intelligence engine (Identity, Psychometrics, Lexical Topics, Mic Memory, Room Atmosphere).
   - `!chat`, `!chatoff`, `!shutup`, `!transcribe`, `!transcribed`, `!suppress`, `!unsuppress`, `!say`, `!diss`, `!who is`, `!info on`, `!grabs`, `-`, `!idk`, `who kicked/banned/blocked/punished`, `!happy`, `!sad`, `!mad`, `!triggers`, `!admins`.

3. **Three Split Terminals with Artwork**:
   - **Terminal 1**: 📥 Incoming Room Feed (Chat, Presence, `SPEAKER_ON_MIC`, User DB).
   - **Terminal 2**: 📤 Bot Actions, Triggers & All-Spins Analyzer (EV, Pity Surge, Phase Timing, Payouts).
   - **Terminal 3**: 🎙️ Live Speech Transcription & Neural Voice Cloning Progress.

4. **PepeFrog Economy & Heist Optimizer**:
   - 30-Second Timing Window Brackets (`60s-90s`, `90s-120s`, `120s-150s`, `150s-180s`).
   - 6 D&D Attributes (`STR`, `DEX`, `CON`, `INT`, `WIS`, `CHA`) for Grand Theft Frogger (`!heist`).
   - Vault Door crack odds vs `!bail` calculation with Ghost Plates (+20% loot bonus).
   - Pity mechanics & Sink Rate safety net trigger after 6 consecutive losses.

5. **Direct Pixel Coordinate Calibration**:
   - Method 1: 3-Second Cursor Auto-Calibrate (Chat box & Talk button).
   - Method 2: Direct Pixel entry (Chat X/Y, Talk Btn X/Y, Lock Pixels, Live Mouse XY tracker).

6. **Voice Synthesis & Cloning**:
   - Local GPU (Kokoro ONNX FP16), Microsoft Edge Neural, and Coqui XTTS-v2.
   - Voice sampling, cloning, default slot assignment, and clearing.

## Tech Stack

- **Framework**: React 19 + TypeScript + Vite 6
- **Styling**: Tailwind CSS v4
- **Icons**: Lucide React
