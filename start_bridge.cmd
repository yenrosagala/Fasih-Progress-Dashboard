@echo off
REM Browser bridge: a dedicated Chrome exposing CDP on port 9222, so importer.py
REM can read your live FASIH cookies (importer.browser_session) instead of you
REM pasting/renewing a session blob. Log into FASIH once -- this profile persists.
REM
REM Then run the dashboard with the bridge enabled:  set FASIH_BRIDGE=1
setlocal
set "PORT=9222"
set "PROFILE=%LOCALAPPDATA%\fasih-bridge-profile"

start "" chrome --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" https://fasih-sm.bps.go.id/app
if errorlevel 1 (
  start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" https://fasih-sm.bps.go.id/app
)
echo.
echo Bridge Chrome started on port %PORT% (profile: %PROFILE%).
echo Log into FASIH once in that window; the login persists.
echo Then start the dashboard with:  set FASIH_BRIDGE=1
