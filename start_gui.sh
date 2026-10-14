#!/usr/bin/env bash
# =====================================================================
#       KAEKAE_TOAD & PEPEFROG AUTOMATION BOT - GUI LAUNCHER (BASH)
# =====================================================================

cd "$(dirname "$0")" || exit 1

echo "====================================================================="
echo "      KAEKAE_TOAD & PEPEFROG AUTOMATION BOT - GUI LAUNCHER"
echo "====================================================================="
echo ""

# 1. Check for Node.js
if ! command -v node >/dev/null 2>&1; then
    echo "[ERROR] Node.js is not installed or not in your PATH!"
    echo "Please download and install Node.js from https://nodejs.org/"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

echo "[OK] Node.js detected: $(node -v)"
echo ""

# 2. Check dependencies
if [ ! -d "node_modules" ]; then
    echo "[INFO] First time setup: Installing bot dependencies..."
    echo "Running 'npm install'..."
    npm install || {
        echo "[ERROR] Failed to install dependencies."
        exit 1
    }
    echo "[OK] Dependencies installed successfully!"
    echo ""
fi

# 3. Launch browser if available
echo "[INFO] Opening interface at http://localhost:3000 ..."
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:3000" &
elif command -v open >/dev/null 2>&1; then
    open "http://localhost:3000" &
fi

# 4. Start the dev server
echo "[INFO] Starting Vite development server..."
npm run dev
