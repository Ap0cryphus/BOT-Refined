# KaeKae_Toad & PepeFrog Supreme Command

A high-performance application suite for **Camfrog (Players__Lounge)** and **PepeFrog / publicaccess.tv** game optimization, neural voice synthesis/cloning, and room coordination.

---

## 🚀 How to Start Your Bot & GUI

### Method 1: 1-Click Desktop Launcher (Windows - Recommended)
1. In the project folder, locate **`start_gui.bat`**.
2. **Double-click `start_gui.bat`**.
3. It automatically:
   - Verifies Node.js is installed.
   - Installs all dependencies (`npm install`) on first launch.
   - Starts the Bot GUI server at `http://localhost:3000`.
   - Automatically opens your default web browser to the Supreme Command Dashboard.

### Method 2: 1-Click Bash Launcher (Linux / Mac / Git Bash)
Run the launcher script in your terminal:
```bash
bash start_gui.sh
```

### Method 3: Command Line (Standard)
1. Open a terminal in the project directory.
2. Install dependencies (first time only):
   ```bash
   npm install
   ```
3. Start the GUI development server:
   ```bash
   npm run dev
   ```
4. Open your browser and navigate to:
   ```
   http://localhost:3000
   ```

---

## 📁 Where is the GUI File?

The graphical user interface is built as a web-native application:
- **Primary HTML Entry Point**: [`index.html`](./index.html) — The web page container mounted on port 3000.
- **Main React Engine**: [`src/App.tsx`](./src/App.tsx) — The master GUI layout holding all three split terminals, telemetry monitors, PepeFrog economy controls, and voice clone decks.
- **Root Mount**: [`src/main.tsx`](./src/main.tsx) — Bootstraps React into the DOM.
- **Automation & Telemetry Core**: [`src/services/botStore.ts`](./src/services/botStore.ts) — The active bot state machine, trigger engine, Camfrog coordinate pipeline, and clone mode coordinator.
- **1-Click Launchers**:
  - Windows: [`start_gui.bat`](./start_gui.bat)
  - Linux/Mac: [`start_gui.sh`](./start_gui.sh)

---

## 🔄 GitHub Sync & Recovery

- **Export & Sync GUI**: Click the **`GITHUB SYNC`** button in the top navigation bar to download the complete standalone `.zip` bundle or view your live Git status.
- **Push Updates to GitHub Master**:
  - Windows: Double-click `push_to_github.bat`
  - Linux / Mac: Run `bash push_to_github.sh`
  - Command: `git push -u origin master --force`

---

## ⚡ Core Features Preserved

1. **Automatic Silent Room Listening & Live Monitoring**:
   - Boots in silent mode (`auto_spin_enabled = false`) without disrupting active rooms.
   - Monitors live room chatter, user joins/quits, and `SPEAKER_ON_MIC` tracking.
   - Enhanced SQLite 5.1/5.2 psychometric profiling (top nouns, sentiment scores, speech cadence, biographies).

2. **Dedicated Clone Mode & State Safety Toggle**:
   - Hijacks audio from whoever is the active `SPEAKER_ON_MIC`.
   - Halts all background spam/spins/heists safely while cloning.
   - Automatically returns to normal bot automation once synthesis completes.

3. **20 KaeKae_Toad Contextual Triggers**:
   - `kaekae <message>`: 5-compartment contextual intelligence engine (Identity, Psychometrics, Lexical Topics, Mic Memory, Room Atmosphere).
   - `!chat`, `!chatoff`, `!shutup`, `!transcribe`, `!transcribed`, `!suppress`, `!unsuppress`, `!say`, `!diss`, `!who is`, `!info on`, `!grabs`, `-`, `!idk`, `who kicked/banned/blocked/punished`, `!happy`, `!sad`, `!mad`, `!triggers`, `!admins`.

4. **Three Split Terminals with Artwork**:
   - **Terminal 1**: 📥 Incoming Room Feed (Chat, Presence, `SPEAKER_ON_MIC`, User DB).
   - **Terminal 2**: 📤 Bot Actions, Triggers & All-Spins Analyzer (EV, Pity Surge, Phase Timing, Payouts).
   - **Terminal 3**: 🎙️ Live Speech Transcription & Neural Voice Cloning Progress.

5. **PepeFrog Economy & Heist Optimizer**:
   - 30-Second Timing Window Brackets (`60s-90s`, `90s-120s`, `120s-150s`, `150s-180s`).
   - 6 D&D Attributes (`STR`, `DEX`, `CON`, `INT`, `WIS`, `CHA`) for Grand Theft Frogger (`!heist`).
   - Vault Door crack odds vs `!bail` calculation with Ghost Plates (+20% loot bonus).
   - Pity mechanics & Sink Rate safety net trigger after 6 consecutive losses.

6. **Direct Pixel Coordinate Calibration**:
   - Method 1: 3-Second Cursor Auto-Calibrate (Chat box & Talk button).
   - Method 2: Direct Pixel entry (Chat X/Y, Talk Btn X/Y, Lock Pixels, Live Mouse XY tracker).

7. **Voice Synthesis & Cloning Engines**:
   - Local GPU (Kokoro ONNX FP16), Microsoft Edge Neural, and Coqui XTTS-v2.
   - Voice sampling, cloning, default slot assignment, and clearing.

---

## 🛠️ Tech Stack

- **Framework**: React 19 + TypeScript + Vite 6
- **Styling**: Tailwind CSS v4
- **Icons**: Lucide React
- **Launchers**: Native Windows Batch (`start_gui.bat`) & Unix Shell (`start_gui.sh`)
