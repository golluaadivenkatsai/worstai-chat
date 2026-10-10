@echo off
echo ==============================================
echo WorstAI Vercel Deployment Script
echo ==============================================
echo.

set PATH=C:\Users\DELL\.gemini\antigravity-ide\scratch\worstai-chat\node-v20.11.1-win-x64;%PATH%

echo Step 1: Logging into Vercel...
echo (A browser window might open. If it asks you to log in, please do so!)
call npx vercel login

echo.
echo Step 2: Pushing the fixed code to Vercel...
call npx vercel --prod --yes

echo.
echo ==============================================
echo Deployment Finished! Check your live URL!
echo ==============================================
pause
