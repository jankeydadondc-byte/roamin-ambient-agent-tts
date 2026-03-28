@echo off
set VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat
set NVCC=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.1\bin\nvcc.exe
set CMAKE_ARGS=-DGGML_CUDA=on -DCMAKE_CUDA_COMPILER="%NVCC%" -G Ninja
set FORCE_CMAKE=1
call "%VCVARS%" && C:\AI\roamin-ambient-agent-tts\.venv\Scripts\pip.exe install llama-cpp-python --no-cache-dir
echo DONE
