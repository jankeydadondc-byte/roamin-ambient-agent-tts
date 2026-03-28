# Install llama-cpp-python with CUDA on this machine
# Requires: VS 2019 Build Tools + CUDA 13.1 + Ninja
# Run from the repo root with venv activated

$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$nvcc = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.1\bin\nvcc.exe"

$env:CMAKE_ARGS = "-DGGML_CUDA=on -DCMAKE_CUDA_COMPILER=`"$nvcc`" -G Ninja"
$env:FORCE_CMAKE = 1

cmd /c "`"$vcvars`" && pip install llama-cpp-python --no-cache-dir"
