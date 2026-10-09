@echo off
title Camfrog Fast Room Monitor + Bot Triggers (0.10s)
cd /d "C:\Users\newbe\AIBot"
if exist "__pycache__" rmdir /s /q "__pycache__" >nul 2>&1
python room_monitor.py
pause
