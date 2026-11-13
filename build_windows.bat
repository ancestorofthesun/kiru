@echo off
rem ============================================================================================
rem  Kiru - build the Windows app and its installer. Just double-click this file.
rem
rem  It does everything by itself:
rem    1. finds Python 3.10+                       (tells you where to get it if it is missing)
rem    2. makes its own build environment          (.venv-build - your Python is left alone)
rem    3. installs the packages and PyInstaller
rem    4. gets FFmpeg into vendor\ffmpeg           (copies yours, or downloads it)
rem    5. gets Inno Setup                          (finds it, or installs it with winget)
rem    6. builds  dist\Kiru\Kiru.exe  (no console window, no UPX)  and  dist\installer\KiruSetup.exe
rem
rem  If a step cannot be done, it says exactly what is missing and waits - it never fails silently.
rem  (c) 2026 Aden. All rights reserved.
rem ============================================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "CI="
if /i "%~1"=="--ci" set "CI=1"
title Building Kiru
echo.
echo   Building Kiru for Windows. This takes 5-15 minutes the first time.
echo.

rem ---------------------------------------------------------------- 1. Python
set "PY="
where py >nul 2>&1 && (py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=py -3")
if not defined PY (where python >nul 2>&1 && (python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"))
if not defined PY goto :no_python
echo   [1/6] Python found.

rem ---------------------------------------------------------------- 2. build environment
if not exist ".venv-build\Scripts\python.exe" (
  echo   [2/6] Making the build environment...
  %PY% -m venv .venv-build || goto :fail_venv
) else (
  echo   [2/6] Build environment ready.
)
set "VPY=%CD%\.venv-build\Scripts\python.exe"

rem ---------------------------------------------------------------- 3. packages
echo   [3/6] Installing Kiru's packages and PyInstaller (a few minutes the first time)...
"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
"%VPY%" -m pip install -r requirements.txt pyinstaller pywebview --quiet --disable-pip-version-check || goto :fail_pip

rem ---------------------------------------------------------------- 4. FFmpeg
if not exist "vendor\ffmpeg" mkdir "vendor\ffmpeg"
if exist "vendor\ffmpeg\ffmpeg.exe" if exist "vendor\ffmpeg\ffprobe.exe" goto :ffmpeg_ok
echo   [4/6] FFmpeg is not in vendor\ffmpeg yet...
for %%E in (ffmpeg ffprobe) do (
  if not exist "vendor\ffmpeg\%%E.exe" for /f "delims=" %%P in ('where %%E.exe 2^>nul') do (
    rem a Chocolatey "shim" is only a pointer to the real program: never bundle that
    echo %%P | find /i "chocolatey\bin" >nul || if not exist "vendor\ffmpeg\%%E.exe" copy /y "%%P" "vendor\ffmpeg\%%E.exe" >nul
  )
)
if exist "vendor\ffmpeg\ffmpeg.exe" if exist "vendor\ffmpeg\ffprobe.exe" (echo         copied the FFmpeg that is installed on this PC. & goto :ffmpeg_ok)
echo         downloading FFmpeg (about 100 MB)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; $z=Join-Path $env:TEMP 'kiru-ffmpeg.zip'; $d=Join-Path $env:TEMP 'kiru-ffmpeg'; Invoke-WebRequest -UseBasicParsing 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $z; if (Test-Path $d) { Remove-Item $d -Recurse -Force }; Expand-Archive $z $d -Force; Get-ChildItem $d -Recurse -Include ffmpeg.exe,ffprobe.exe | Copy-Item -Destination 'vendor\ffmpeg' -Force; Remove-Item $z -Force; Remove-Item $d -Recurse -Force"
if exist "vendor\ffmpeg\ffmpeg.exe" if exist "vendor\ffmpeg\ffprobe.exe" goto :ffmpeg_ok
goto :no_ffmpeg
:ffmpeg_ok
"vendor\ffmpeg\ffmpeg.exe" -version >nul 2>&1 || goto :bad_ffmpeg
echo   [4/6] FFmpeg ready (it goes inside the app).

rem ---------------------------------------------------------------- 5. Inno Setup
call :find_iscc
if defined ISCC goto :iscc_ok
echo   [5/6] Inno Setup is not installed: installing it with winget...
where winget >nul 2>&1 && winget install -e --id JRSoftware.InnoSetup --silent --accept-source-agreements --accept-package-agreements >nul 2>&1
call :find_iscc
if defined ISCC goto :iscc_ok
echo   [5/6] Inno Setup could not be installed automatically. The app is built anyway;
echo         for KiruSetup.exe install it from https://jrsoftware.org/isdl.php and run this file again.
set "APPONLY=--app-only"
goto :build
:iscc_ok
echo   [5/6] Inno Setup ready.
set "APPONLY="

rem ---------------------------------------------------------------- 6. build
:build
echo   [6/6] Building Kiru.exe (windowed, no console, no UPX)...
echo.
"%VPY%" scripts\build_installer.py %APPONLY% || goto :fail_build
echo.
echo   ==========================================================
if defined APPONLY (
  echo    Done. The app:        dist\Kiru\Kiru.exe
  echo    No installer was made: Inno Setup is missing, see above.
) else (
  echo    Done. The installer:  dist\installer\KiruSetup.exe
  echo          The app itself: dist\Kiru\Kiru.exe
)
echo   ==========================================================
if not defined CI pause
exit /b 0

:find_iscc
set "ISCC="
for /f "delims=" %%P in ('where iscc.exe 2^>nul') do if not defined ISCC set "ISCC=%%P"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
exit /b 0

:no_python
echo.
echo   [X] Python 3.10 or newer was not found.
echo.
echo       Get it from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH" in its installer^),
echo       then double-click build_windows.bat again.
goto :stop
:fail_venv
echo.
echo   [X] The build environment could not be made ^(python -m venv .venv-build failed^).
echo       Delete the .venv-build folder if there is one and run this file again.
goto :stop
:fail_pip
echo.
echo   [X] A package could not be installed. The lines above name it.
echo       Most often this is no internet connection, or a Python older than 3.10 / newer than 3.12.
goto :stop
:no_ffmpeg
echo.
echo   [X] FFmpeg is missing and could not be downloaded.
echo.
echo       Kiru cannot make videos without it, so the build stops here instead of making a broken app.
echo.
echo       Fix:  1. download  https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
echo             2. open it and copy  bin\ffmpeg.exe  and  bin\ffprobe.exe  into
echo                %CD%\vendor\ffmpeg
echo             3. double-click build_windows.bat again
goto :stop
:bad_ffmpeg
echo.
echo   [X] vendor\ffmpeg\ffmpeg.exe is there but does not run ^(a broken or blocked download?^).
echo       Delete the two files in vendor\ffmpeg and run this file again to fetch them anew.
goto :stop
:fail_build
echo.
echo   [X] The build stopped. The message above says why.
echo       If it names a missing module, send that line to the author: it is one word to add to kiru.spec.
goto :stop
:stop
echo.
if not defined CI pause
exit /b 1
