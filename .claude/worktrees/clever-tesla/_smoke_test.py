import sys

sys.path.insert(0, r"C:\AI\roamin-ambient-agent-tts")

results = []

checks = [
    ("chromadb", "import chromadb"),
    ("requests", "import requests"),
    ("PIL", "from PIL import Image"),
    ("sounddevice", "import sounddevice"),
    ("keyboard", "import keyboard"),
    ("pyttsx3", "import pyttsx3"),
    ("whisper", "import whisper"),
    ("torch", "import torch; print('CUDA:', torch.cuda.is_available())"),
    ("numpy", "import numpy"),
    ("agent.core.ports", "from agent.core.ports import get_control_api_url"),
    ("agent.core.model_router", "from agent.core.model_router import ModelRouter"),
    ("agent.core.llama_backend", "from agent.core.llama_backend import CAPABILITY_MAP"),
    ("agent.core.voice.tts", "from agent.core.voice.tts import TextToSpeech"),
    ("agent.core.voice.stt", "from agent.core.voice.stt import SpeechToText"),
    ("agent.core.voice.wake_listener", "from agent.core.voice.wake_listener import WakeListener"),
    ("agent.core.agent_loop", "from agent.core.agent_loop import AgentLoop"),
]

for name, code in checks:
    try:
        exec(code)
        results.append(f"  OK  {name}")
    except Exception as e:
        results.append(f"  FAIL {name}: {e}")

print("\n=== NEW VENV SMOKE TEST ===")
for r in results:
    print(r)
print(f"\n{sum(1 for r in results if 'OK' in r)}/{len(results)} passed")
