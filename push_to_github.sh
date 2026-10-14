#!/usr/bin/env bash
# ==============================================================================
# push_to_github.sh — Push Complete Bot-Refined Suite to GitHub master Branch
# ==============================================================================

set -e

REPO_URL="https://github.com/Ap0cryphus/BOT-Refined.git"
BRANCH="master"

echo "===================================================================="
echo "  KaeKae_Toad & PepeFrog Suite: Push to GitHub ($BRANCH branch)"
echo "  Target: $REPO_URL"
echo "===================================================================="
echo ""

# Ensure git is initialized and on master
git init
git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"

# Configure remote
if git remote | grep -q "^origin$"; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi

# Stage and commit any recent changes
git add .
if git status --porcelain | grep -q .; then
  git commit -m "Restore complete KaeKae_Toad & PepeFrog application suite"
else
  echo "Working tree is clean. Ready to push."
fi

echo ""
echo "Select authentication method:"
echo "1) Push using existing Git credential manager / SSH"
echo "2) Push using a GitHub Personal Access Token (PAT)"
read -rp "Enter choice [1 or 2]: " AUTH_CHOICE

if [ "$AUTH_CHOICE" = "2" ]; then
  read -rp "Enter your GitHub username [Ap0cryphus]: " GH_USER
  GH_USER=${GH_USER:-Ap0cryphus}
  read -rsp "Enter your GitHub Personal Access Token (PAT): " GH_TOKEN
  echo ""
  
  if [ -z "$GH_TOKEN" ]; then
    echo "Error: Token cannot be empty."
    exit 1
  fi
  
  AUTHENTICATED_URL="https://${GH_USER}:${GH_TOKEN}@github.com/Ap0cryphus/BOT-Refined.git"
  echo "Pushing changes to $BRANCH branch..."
  git push -u "$AUTHENTICATED_URL" "$BRANCH" --force
  echo "Success! GitHub repository restored on branch $BRANCH."
else
  echo "Pushing changes to $BRANCH branch..."
  git push -u origin "$BRANCH" --force
  echo "Success! GitHub repository restored on branch $BRANCH."
fi
