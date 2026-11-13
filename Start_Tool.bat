@echo off
setlocal
title Kiru - AMV maker
cd /d "%~dp0"

echo.
echo  ==============================================
echo     K I R U   -   the open-source AMV maker
echo     beat-synced edits, runs on this PC only
echo  ==============================================
echo.

rem ---------- Python ----------
rem "python" can be the Microsoft Store stub, so actually run it to check.
set "PY="
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY goto no_python
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo  [ok] %%v

rem ---------- FFmpeg / FFprobe ----------
where ffmpeg >nul 2>&1
if errorlevel 1 goto no_ffmpeg
where ffprobe >nul 2>&1
if errorlevel 1 goto no_ffmpeg
echo  [ok] FFmpeg and FFprobe found

rem ---------- Python packages (first run only) ----------
%PY% -c "import flask, librosa, PIL, cv2" >nul 2>&1
if not errorlevel 1 goto deps_ok
echo.
echo  First run: installing Flask, librosa, Pillow and OpenCV. This can take a few minutes...
echo.
%PY% -m pip install --upgrade pip
%PY% -m pip install flask librosa pillow opencv-contrib-python
if errorlevel 1 goto pip_failed
:deps_ok
echo  [ok] Flask, librosa, Pillow and OpenCV installed
rem ---------- OpenCV object tracker (CSRT) for Beat Sync "Track object" ----------
%PY% -c "import cv2; cv2.TrackerCSRT_create" >nul 2>&1
if not errorlevel 1 goto csrt_ok
echo  Adding the OpenCV object tracker (opencv-contrib-python). One time only...
%PY% -m pip uninstall -y opencv-python opencv-python-headless >nul 2>&1
%PY% -m pip install opencv-contrib-python
if errorlevel 1 (
    echo  [!] The tracker add-on could not be installed. Track object uses a simpler tracker.
    %PY% -m pip install opencv-python
)
:csrt_ok

rem ---------- AI video background removal model (Robust Video Matting, 15 MB) ----------
if not exist "%~dp0ai_models" mkdir "%~dp0ai_models"
if exist "%~dp0ai_models\rvm_mobilenetv3_fp32.onnx" goto rvm_ok
echo  Downloading the background-removal model once - 15 MB, kept in the ai_models folder...
%PY% -c "import urllib.request, os; d=r'%~dp0ai_models'; urllib.request.urlretrieve('https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx', os.path.join(d, 'rvm.part')); os.replace(os.path.join(d, 'rvm.part'), os.path.join(d, 'rvm_mobilenetv3_fp32.onnx'))"
if errorlevel 1 echo  [!] The model download failed - it is tried again when you first use Remove background.
:rvm_ok

rem ---------- ONNX Runtime (runs the AI): on the NVIDIA GPU when it passes the GPU test, else the CPU ----------
rem 1.21.1 and 1.23.2 crashed (0xC000001D) on the first GPU inference here; 1.27+ on PyPI is CUDA 13.
rem Tried in order, each one only once (ai_models\gpu_tried_*.txt), the first that passes the GPU test is kept:
rem   1. onnxruntime-gpu 1.20.0 - CUDA 12.2 / cuDNN 9 build, uses the NVIDIA CUDA 12 libraries already installed
rem   2. onnxruntime-gpu 1.18.0 - CUDA 11.8 / cuDNN 8 build, needs the CUDA 11 libraries (installed next to the CUDA 12 ones)
rem   3. background removal on the CPU (ai_models\gpu_force_cpu.txt).
rem The GPU test also retries each version with cuDNN's non-benchmarking modes before giving up on it.
where nvidia-smi >nul 2>&1
if errorlevel 1 goto ort_cpu
for /f "delims=" %%g in ('nvidia-smi --query-gpu^=name^,driver_version --format^=csv^,noheader 2^>nul') do echo  [ok] NVIDIA %%g
rem An earlier version switched the GPU off after 1.21.1 crashed: that switch is cleared once so 1.20.0 / 1.18.0 get their turn
if not exist "%~dp0ai_models\gpu_stack_ort1.21.1.txt" goto ort_nomigrate
del "%~dp0ai_models\gpu_force_cpu.txt" >nul 2>&1
del "%~dp0ai_models\gpu_stack_ort1.21.1.txt" >nul 2>&1
del "%~dp0ai_models\gpu_stack_cu12.txt" >nul 2>&1
:ort_nomigrate
if /i not "%~1"=="--repair-gpu" goto ort_norepair
del "%~dp0ai_models\gpu_force_cpu.txt" >nul 2>&1
del "%~dp0ai_models\gpu_tried_*.txt" >nul 2>&1
del "%~dp0ai_models\gpu_options.json" >nul 2>&1
:ort_norepair
if exist "%~dp0ai_models\gpu_force_cpu.txt" goto ort_forced_cpu
if not exist "%~dp0ai_models\rvm_mobilenetv3_fp32.onnx" goto ort_nomodel
if /i "%~1"=="--repair-gpu" goto ort_try_1200
echo  Checking the NVIDIA GPU for the AI...
%PY% app.py --gpu-check >nul 2>&1
if not errorlevel 1 goto ort_gpu_ok
:ort_try_1200
if exist "%~dp0ai_models\gpu_tried_1.20.0.txt" goto ort_try_1180
echo.
echo  Trying ONNX Runtime GPU 1.20.0 ^(CUDA 12.2 / cuDNN 9 build^) with your CUDA 12 libraries...
echo.
%PY% -m pip uninstall -y onnxruntime onnxruntime-gpu onnxruntime-directml
%PY% -m pip uninstall -y nvidia-cudnn-cu13 nvidia-cublas-cu13 nvidia-cuda-runtime-cu13 nvidia-cuda-nvrtc-cu13 nvidia-cufft-cu13 nvidia-curand-cu13 nvidia-cudnn nvidia-cublas nvidia-cuda-runtime nvidia-cuda-nvrtc nvidia-cufft nvidia-curand >nul 2>&1
%PY% -m pip install --no-cache-dir "onnxruntime-gpu==1.20.0"
if errorlevel 1 goto ort_install_failed
rem no --upgrade: the CUDA 12 libraries that are already there stay exactly as they are; only missing ones are added
%PY% -m pip install "nvidia-cudnn-cu12>=9,<10" "nvidia-cublas-cu12>=12,<13" "nvidia-cuda-runtime-cu12>=12,<13" "nvidia-cufft-cu12>=11,<12" "nvidia-curand-cu12>=10,<11" "nvidia-cuda-nvrtc-cu12>=12,<13"
if errorlevel 1 goto ort_install_failed
echo %date% %time%> "%~dp0ai_models\gpu_tried_1.20.0.txt"
echo  Testing the GPU with 1.20.0...
%PY% app.py --gpu-check >nul 2>&1
if not errorlevel 1 goto ort_gpu_ok
call :ort_report
:ort_try_1180
if exist "%~dp0ai_models\gpu_tried_1.18.0.txt" goto ort_force_cpu
echo.
echo  Trying ONNX Runtime GPU 1.18.0 ^(CUDA 11.8 / cuDNN 8 build^).
echo  It needs the CUDA 11 libraries - installed next to your CUDA 12 ones, which stay untouched. About 1.5 GB...
echo.
%PY% -m pip uninstall -y onnxruntime onnxruntime-gpu onnxruntime-directml
%PY% -m pip install --no-cache-dir "onnxruntime-gpu==1.18.0"
if errorlevel 1 goto ort_install_failed
%PY% -m pip install "nvidia-cudnn-cu11==8.9.5.29" "nvidia-cublas-cu11==11.11.3.6" "nvidia-cuda-runtime-cu11==11.8.89" "nvidia-cufft-cu11==10.9.0.58"
if errorlevel 1 goto ort_install_failed
echo %date% %time%> "%~dp0ai_models\gpu_tried_1.18.0.txt"
echo  Testing the GPU with 1.18.0...
%PY% app.py --gpu-check >nul 2>&1
if not errorlevel 1 goto ort_gpu_ok
call :ort_report
:ort_force_cpu
echo %date% %time% onnxruntime-gpu 1.20.0 and 1.18.0 failed the GPU test - see gpu_check.log> "%~dp0ai_models\gpu_force_cpu.txt"
echo  [!] No ONNX Runtime version passes the GPU test on this PC, so background removal runs on the CPU from now on.
echo      To try the GPU again later ^(e.g. after a driver update^): Start_Tool.bat --repair-gpu
goto ort_done
:ort_forced_cpu
echo  [ok] AI background removal runs on the CPU ^(the GPU test crashed with every ONNX Runtime version - ai_models\gpu_check.log^)
echo       To try the GPU again: Start_Tool.bat --repair-gpu
goto ort_done
:ort_gpu_ok
for /f "delims=" %%v in ('%PY% -c "import importlib.metadata as m; print(m.version('onnxruntime-gpu'))" 2^>nul') do set "ORTV=%%v"
echo  [ok] AI runs on the NVIDIA GPU ^(ONNX Runtime %ORTV%^)
goto ort_done
:ort_install_failed
echo.
echo  [!] The GPU packages could not be installed - see the messages above. The AI uses the CPU ^(slow^) for now;
echo      it is tried again next start.
%PY% -c "import onnxruntime" >nul 2>&1
if not errorlevel 1 goto ort_done
%PY% -m pip uninstall -y onnxruntime-gpu >nul 2>&1
%PY% -m pip install onnxruntime
goto ort_done
:ort_nomodel
echo  [!] The AI model isn't downloaded yet, so the GPU test is skipped this time.
%PY% -c "import onnxruntime" >nul 2>&1
if not errorlevel 1 goto ort_done
%PY% -m pip install "onnxruntime-gpu==1.20.0"
goto ort_done
:ort_cpu
%PY% -c "import onnxruntime" >nul 2>&1
if not errorlevel 1 goto ort_cpu_ok
echo  Installing ONNX Runtime for the AI. One time only...
%PY% -m pip install onnxruntime
:ort_cpu_ok
echo  [ok] AI runs on the CPU ^(no NVIDIA card found^)
:ort_done

rem ---------- Image Editor: AI Select Subject (rembg). Installed without touching the onnxruntime chosen above ----------
%PY% -c "import rembg" >nul 2>&1
if not errorlevel 1 goto rembg_ok
echo  Adding the Image Editor AI cut-out ^(rembg^). One time only...
%PY% -m pip install --no-deps rembg
%PY% -m pip install pooch pymatting scikit-image jsonschema tqdm
%PY% -c "import rembg" >nul 2>&1
if errorlevel 1 echo  [note] rembg could not be installed. Select Subject in the Image Editor will be unavailable; everything else works.
:rembg_ok

rem ---------- Image Editor: text finder for posters (RapidOCR, runs on the onnxruntime chosen above) ----------
%PY% -c "import rapidocr_onnxruntime" >nul 2>&1
if not errorlevel 1 goto pocr_ok
echo  Adding the poster text reader ^(rapidocr^). One time only...
%PY% -m pip install --no-deps rapidocr-onnxruntime
%PY% -m pip install pyclipper shapely pyyaml six
%PY% -c "import rapidocr_onnxruntime" >nul 2>&1
if errorlevel 1 echo  [note] rapidocr could not be installed. "From a picture" in the Image Editor falls back to Tesseract; everything else works.
:pocr_ok

rem ---------- Desktop window (PyWebView). Without it Kiru opens in the browser, as before ----------
%PY% -c "import webview" >nul 2>&1
if not errorlevel 1 goto wv_ok
echo  Adding the desktop window ^(pywebview^). One time only...
%PY% -m pip install pywebview
%PY% -c "import webview" >nul 2>&1
if errorlevel 1 echo  [note] pywebview could not be installed. Kiru opens in your browser instead.
:wv_ok

rem ---------- Template Lab extras (optional): PySceneDetect cross-check + reading on-screen text ----------
%PY% -c "import scenedetect, pytesseract" >nul 2>&1
if not errorlevel 1 goto tpl_ok
echo  Adding the Template Lab extras ^(scenedetect, pytesseract^). One time only...
%PY% -m pip install scenedetect pytesseract
if errorlevel 1 echo  [!] The extras could not be installed. Template Lab still works with its built-in scene detector.
:tpl_ok
where tesseract >nul 2>&1
if not errorlevel 1 goto tess_ok
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" goto tess_ok
echo  [i] Optional: Tesseract OCR is not installed, so Template Lab cannot read the on-screen text
echo      of a reference video. Everything else works. To add it, run:  winget install UB-Mannheim.TesseractOCR
goto tess_done
:tess_ok
echo  [ok] Tesseract found - Template Lab can read on-screen text
:tess_done
echo.

rem ---------- Run ----------
rem With the desktop window (pywebview) Kiru starts WITHOUT a console: pythonw runs it and this black window closes itself.
rem Without pywebview it runs here and opens in the browser, as before.
%PY% -c "import webview" >nul 2>&1
if errorlevel 1 goto run_console
set PYW=
for /f "usebackq delims=" %%P in (`%PY% -c "import sys,os; p=os.path.join(os.path.dirname(sys.executable),'pythonw.exe'); print(p if os.path.isfile(p) else '')"`) do set PYW=%%P
if not defined PYW goto run_console
echo  Starting Kiru - its window opens in a moment. This window closes by itself.
start "" "%PYW%" kiru.py
exit /b 0
:run_console
echo  Starting Kiru - its window opens in a moment.
echo.
%PY% kiru.py
echo.
echo  Kiru stopped.
pause
exit /b 0

rem ---------- Error screens ----------
:no_python
echo  [X] Python was not found.
echo.
echo      1. Download it from https://www.python.org/downloads/
echo      2. In the installer, TICK THE BOX "Add python.exe to PATH"
echo      3. Finish the install, then double-click Start_Tool.bat again.
echo.
pause
exit /b 1

:no_ffmpeg
echo  [X] FFmpeg / FFprobe were not found.
echo.
echo      Open a Command Prompt and run:
echo.
echo          winget install Gyan.FFmpeg
echo.
echo      Then CLOSE this window and double-click Start_Tool.bat again
echo      so Windows picks up the new PATH.
echo.
pause
exit /b 1

:pip_failed
echo.
echo  [X] Installing Flask / librosa / Pillow / OpenCV failed - see the error above.
echo      Check your internet connection for this one-time install and try again.
echo.
pause
exit /b 1

rem ---------- Subroutine: the full GPU test report (the Python traceback / missing DLL), also saved to ai_models\gpu_check.log ----------
:ort_report
echo.
echo  [!] The GPU test failed. Full report ^(also saved to ai_models\gpu_check.log^):
echo  ------------------------------------------------------------------------
%PY% app.py --gpu-check --verbose
echo  ------------------------------------------------------------------------
echo  The AI uses the CPU ^(slow^) until this is fixed. Nothing else breaks.
echo  Most often fixed by updating the NVIDIA driver ^(nvidia.com / NVIDIA App^) and starting again.
echo  To try the GPU install again: Start_Tool.bat --repair-gpu
echo.
exit /b 0
