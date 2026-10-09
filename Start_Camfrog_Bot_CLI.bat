@echo off
title Camfrog Bot Interactive Console
cd /d "C:\Users\newbe\AIBot"
if exist "__pycache__" rmdir /s /q "__pycache__" >nul 2>&1
python camfrog_bot.py
pause
