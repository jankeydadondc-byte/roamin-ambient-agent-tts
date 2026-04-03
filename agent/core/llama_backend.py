"""LlamaCpp-based in-process LLM inference backend for Roamin.

This module eliminates external server dependencies by loading GGUF models directly
via llama-cpp-python. All model paths are validated at runtime, not import time.
"""

from __future__ import annotations

import threading
from pathlib import Path

# Import guard: deferred error if llama-cpp-python is missing
try:
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Llava15ChatHandler

    try:
        from llama_cpp.llama_chat_format import Qwen25VLChatHandler
    except ImportError:
        Qwen25VLChatHandler = None  # type: ignore
except ImportError:
    Llama = None  # type: ignore
    Llava15ChatHandler = None  # type: ignore
    Qwen25VLChatHandler = None  # type: ignore

# Model paths validated at runtime (not import time)
# --- Primary: Qwen3-VL-8B abliterated (unified default + vision) ---
_MODELS_DIR = Path(r"C:\AI\roamin-ambient-agent-tts\models")

QWEN3_VL_8B = _MODELS_DIR / "Qwen3-VL-8B-Instruct-abliterated-v2.Q4_K_M.gguf"
QWEN3_VL_8B = QWEN3_VL_8B if QWEN3_VL_8B.exists() else None

QWEN3_VL_8B_MMPROJ = _MODELS_DIR / "Qwen3-VL-8B-Instruct-abliterated-v2.mmproj-Q8_0.gguf"
QWEN3_VL_8B_MMPROJ = QWEN3_VL_8B_MMPROJ if QWEN3_VL_8B_MMPROJ.exists() else None

# --- Legacy: Qwen3 8B (Ollama blob, text-only fallback) ---
QWEN3_8B = Path(
    r"C:\Users\Asherre Roamin\.ollama\models\blobs\sha256-a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f"  # noqa: E501
)
QWEN3_8B = QWEN3_8B if QWEN3_8B.exists() else None

# --- Qwen3.5 9B (legacy vision, kept for reference) ---
QWEN35_9B = Path(
    r"C:\Users\Asherre Roamin\.lmstudio\models\lmstudio-community" r"\Qwen3.5-9B-GGUF\Qwen3.5-9B-Q4_K_M.gguf"
)
QWEN35_9B = QWEN35_9B if QWEN35_9B.exists() else None

QWEN35_9B_MMPROJ = Path(
    r"C:\Users\Asherre Roamin\.lmstudio\models\lmstudio-community\Qwen3.5-9B-GGUF\mmproj-Qwen3.5-9B-BF16.gguf"
)
QWEN35_9B_MMPROJ = QWEN35_9B_MMPROJ if QWEN35_9B_MMPROJ.exists() else None

# --- DeepSeek R1 8B ---
DEEPSEEK_R1_8B = Path(r"C:\Users\Asherre Roamin\.lmstudio\models" r"\DeepSeek-R1-0528-Qwen3-8B-Q4_K_M.gguf")
DEEPSEEK_R1_8B = DEEPSEEK_R1_8B if DEEPSEEK_R1_8B.exists() else None

# --- Ministral 3 14B ---
MINISTRAL_14B = Path(
    r"C:\Users\Asherre Roamin\.lmstudio\models\lmstudio-community\Ministral-3-14B-Reasoning-2512-GGUF\Ministral-3-14B-Reasoning-2512-Q4_K_M.gguf"  # noqa: E501
)
MINISTRAL_14B = MINISTRAL_14B if MINISTRAL_14B.exists() else None

MINISTRAL_14B_MMPROJ = Path(
    r"C:\Users\Asherre Roamin\.lmstudio\models\lmstudio-community\Ministral-3-14B-Reasoning-2512-GGUF\mmproj-Ministral-3-14B-Reasoning-2512-F16.gguf"  # noqa: E501
)
MINISTRAL_14B_MMPROJ = MINISTRAL_14B_MMPROJ if MINISTRAL_14B_MMPROJ.exists() else None

# --- Qwen3 Coder Next 80B ---
QWEN3_CODER_NEXT = Path(
    r"C:\Users\Asherre Roamin\.lmstudio\models\lmstudio-community\Qwen3-Coder-Next-GGUF\Qwen3-Coder-Next-Q4_K_M.gguf"
)
QWEN3_CODER_NEXT = QWEN3_CODER_NEXT if QWEN3_CODER_NEXT.exists() else None

# --- mmproj lookup: maps model paths to their multimodal projection files ---
_MMPROJ_MAP: dict[Path | None, Path | None] = {
    QWEN3_VL_8B: QWEN3_VL_8B_MMPROJ,
    QWEN35_9B: QWEN35_9B_MMPROJ,
    MINISTRAL_14B: MINISTRAL_14B_MMPROJ,
}

CAPABILITY_MAP: dict[str, Path | None] = {
    # Qwen3-VL-8B abliterated — unified default: chat + vision + fast (4.7GB, uncensored)
    "default": QWEN3_VL_8B,
    "chat": QWEN3_VL_8B,
    "fast": QWEN3_VL_8B,
    "vision": QWEN3_VL_8B,
    "screen_reading": QWEN3_VL_8B,
    # DeepSeek R1 8B — deep reasoning
    "reasoning": DEEPSEEK_R1_8B,
    "analysis": DEEPSEEK_R1_8B,
    # Qwen3 Coder Next 80B — heavy code tasks (requires full 24GB+ VRAM)
    "code": QWEN3_CODER_NEXT,
    "heavy_code": QWEN3_CODER_NEXT,
    # Ministral 3 14B — vision + reasoning in one model
    "ministral": MINISTRAL_14B,
    "ministral_vision": MINISTRAL_14B,
    "ministral_reasoning": MINISTRAL_14B,
}

# Context window sizes per capability.
# Qwen3-VL-8B stays at 8192 — vision mmproj consumes extra VRAM so we keep it tight.
# Reasoning and code models load exclusively (Qwen3-VL-8B unloads first), giving them
# the VRAM headroom to support their full training context without overflow.
_CAPABILITY_N_CTX: dict[str, int] = {
    "default": 8192,
    "chat": 8192,
    "fast": 8192,
    "vision": 8192,
    "screen_reading": 8192,
    "reasoning": 32768,
    "analysis": 32768,
    "code": 16384,
    "heavy_code": 16384,
    "ministral": 32768,
    "ministral_vision": 32768,
    "ministral_reasoning": 32768,
}


class LlamaCppBackend:
    """In-process LLM inference backend using llama-cpp-python.

    Supports both text generation and chat completions with optional
    multimodal projections for vision capabilities.
    """

    def __init__(
        self,
        model_path: Path,
        n_gpu_layers: int = -1,
        n_ctx: int = 8192,
        verbose: bool = False,
        mmproj_path: Path | None = None,
    ) -> None:
        """Initialize backend with model path and inference parameters.

        Args:
            model_path: Path to GGUF model file.
            n_gpu_layers: Number of layers to offload to GPU (-1 for full offload).
            n_ctx: Context window size in tokens.
            verbose: Enable llama-cpp-python verbose logging.
            mmproj_path: Optional path to multimodal projection matrix (for vision models).
        """
        self.model_path = model_path
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.verbose = verbose
        self.mmproj_path = mmproj_path

        self._llm: Llama | None = None
        self._loaded: bool = False

    def load(self) -> None:
        """Load model into memory (lazy initialization).

        Raises:
            RuntimeError: If llama-cpp-python is not installed or model file missing.
        """
        if Llama is None:
            raise RuntimeError(
                "llama-cpp-python is required but not installed. " "Install with: pip install llama-cpp-python"
            )

        if not self.model_path.exists():
            raise RuntimeError(f"Model file not found: {self.model_path}")

        # Build kwargs for Llama constructor
        kwargs = {
            "model_path": str(self.model_path),
            "n_gpu_layers": self.n_gpu_layers,
            "n_ctx": self.n_ctx,
            "verbose": self.verbose,
        }

        if self.mmproj_path is not None:
            if not self.mmproj_path.exists():
                raise RuntimeError(f"Multimodal projection file not found: {self.mmproj_path}")
            model_lower = str(self.model_path).lower()
            is_qwen_vl = any(x in model_lower for x in ("qwen2-vl", "qwen2_vl", "qwen25vl", "qwen3-vl", "qwen3_vl"))
            if is_qwen_vl and Qwen25VLChatHandler is not None:
                kwargs["chat_handler"] = Qwen25VLChatHandler(
                    clip_model_path=str(self.mmproj_path), verbose=self.verbose
                )
            elif Llava15ChatHandler is not None:
                kwargs["chat_handler"] = Llava15ChatHandler(clip_model_path=str(self.mmproj_path), verbose=self.verbose)

        try:
            self._llm = Llama(**kwargs)
            self._loaded = True
        except Exception as e:
            raise RuntimeError(f"Failed to load model '{self.model_path}': {e}")

    def unload(self) -> None:
        """Unload model from memory, freeing GPU/CPU resources."""
        if self._llm is not None:
            self._llm.close()
            self._llm = None
        self._loaded = False
        # Release CUDA memory back to OS so other processes (e.g. Chatterbox) can allocate
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        except Exception:
            pass

    def is_loaded(self) -> bool:
        """Check if the model is currently loaded in memory."""
        return self._loaded and self._llm is not None

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 512,
        temperature: float = 0.7,
        stop: list[str] | None = None,
        no_think: bool = False,
        stream_think: bool = False,
    ) -> str:
        """Generate a chat completion from a message list.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                      Roles: "user", "system", or "assistant".
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = random).
            stop: Optional list of stop sequences.
            no_think: If True, suppress <think> blocks by pre-filling empty tags.
            stream_think: If True and no_think is False, stream <think> content
                          to the terminal in real time as the model generates it.

        Returns:
            Assistant reply string stripped of leading/trailing whitespace.

        Raises:
            RuntimeError: If model not loaded or llama-cpp-python unavailable.
        """
        if not self.is_loaded():
            raise RuntimeError("Model must be loaded before calling chat().")

        # Vision path: detect multimodal messages (content is a list with image_url blocks)
        if any(isinstance(msg.get("content"), list) for msg in messages):
            assert self._llm is not None  # guaranteed by is_loaded() check above
            response = self._llm.create_chat_completion(
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop or [],
            )
            if not response or not response["choices"]:
                raise RuntimeError("No response from model.")
            reply = response["choices"][0]["message"]["content"] or ""
            return reply.strip()

        # Text-only path: convert message dicts to llama-cpp format
        prompt = self._format_messages_as_prompt(messages, no_think=no_think)

        # Streaming path: print <think> content to terminal in real time
        if stream_think and not no_think:
            return self._stream_with_think_print(prompt, max_tokens, temperature, stop or [])

        # Non-streaming path (original)
        response = self._llm(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or [],
            echo=False,
        )

        if not response or not response["choices"]:
            raise RuntimeError("No response from model.")

        reply = response["choices"][0]["text"]
        return reply.strip()

    def _stream_with_think_print(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        stop: list[str],
    ) -> str:
        """Stream tokens from the model, printing <think> content to terminal in real time.

        Tokens inside <think>...</think> are printed to stdout as they arrive (dimmed cyan).
        Tokens outside think blocks are accumulated silently.
        The full raw response (including think tags) is returned for the caller to strip.
        """
        OPEN_TAG = "<think>"
        CLOSE_TAG = "</think>"
        DIM_CYAN = "\033[2;36m"
        BOLD_CYAN = "\033[1;36m"
        RESET = "\033[0m"

        full_text = ""
        in_think = False
        buffer = ""

        assert self._llm is not None
        print("[Roamin] Inference started (streaming)...", flush=True)

        for chunk in self._llm(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            echo=False,
            stream=True,
        ):
            token = chunk["choices"][0]["text"]
            full_text += token
            buffer += token

            if not in_think:
                # --- Looking for <think> opening ---
                if OPEN_TAG in buffer:
                    in_think = True
                    print(f"\n{BOLD_CYAN}[Roamin thinking...]{RESET}", flush=True)
                    after = buffer.split(OPEN_TAG, 1)[1]
                    # Edge case: </think> already in same chunk
                    if CLOSE_TAG in after:
                        before_close = after.split(CLOSE_TAG, 1)[0]
                        print(f"{DIM_CYAN}{before_close}{RESET}", end="", flush=True)
                        print(f"\n{BOLD_CYAN}[Roamin done thinking]{RESET}\n", flush=True)
                        in_think = False
                    else:
                        print(f"{DIM_CYAN}{after}{RESET}", end="", flush=True)
                    buffer = ""
                else:
                    # Keep tail for partial tag detection across chunks
                    max_tail = len(OPEN_TAG) - 1
                    if len(buffer) > max_tail:
                        buffer = buffer[-max_tail:]
            else:
                # --- Inside think block, looking for </think> ---
                if CLOSE_TAG in buffer:
                    before_close = buffer.split(CLOSE_TAG, 1)[0]
                    print(f"{DIM_CYAN}{before_close}{RESET}", end="", flush=True)
                    print(f"\n{BOLD_CYAN}[Roamin done thinking]{RESET}\n", flush=True)
                    in_think = False
                    buffer = ""
                else:
                    # Print safe portion, keep tail for partial close tag
                    safe_len = len(buffer) - (len(CLOSE_TAG) - 1)
                    if safe_len > 0:
                        print(f"{DIM_CYAN}{buffer[:safe_len]}{RESET}", end="", flush=True)
                        buffer = buffer[safe_len:]

        # Flush remaining buffer
        if in_think and buffer:
            print(f"{DIM_CYAN}{buffer}{RESET}", end="", flush=True)
            print(f"\n{BOLD_CYAN}[Roamin done thinking]{RESET}\n", flush=True)

        return full_text.strip()

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        """Generate a completion for a raw text prompt.

        Args:
            prompt: Input prompt string.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = random).

        Returns:
            Generated text stripped of leading/trailing whitespace.

        Raises:
            RuntimeError: If model not loaded or llama-cpp-python unavailable.
        """
        if not self.is_loaded():
            raise RuntimeError("Model must be loaded before calling generate().")

        response = self._llm(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            echo=False,
        )

        if not response or not response["choices"]:
            raise RuntimeError("No response from model.")

        completion = response["choices"][0]["text"]
        return completion.strip()

    def _format_messages_as_prompt(self, messages: list[dict], no_think: bool = False) -> str:
        """Convert message list to prompt format appropriate for the loaded model.

        Detects model family from path and applies correct template:
        - Qwen3/DeepSeek: ChatML (<|im_start|> tokens)
        - Ministral/Mistral: Instruct format ([INST] tokens)
        """
        if not messages:
            return ""

        # Detect model family from path
        model_name = str(self.model_path).lower()
        is_mistral = any(x in model_name for x in ("mistral", "ministral"))

        if is_mistral:
            return self._format_mistral(messages)
        return self._format_chatml(messages, no_think=no_think)

    def _format_chatml(self, messages: list[dict], no_think: bool = False) -> str:
        """ChatML format for Qwen3/DeepSeek models."""
        formatted_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                formatted_parts.append("<|im_start|>system\n" + content + "<|im_end|>")
            elif role == "assistant":
                formatted_parts.append("<|im_start|>assistant\n" + content + "<|im_end|>")
            else:
                formatted_parts.append("<|im_start|>user\n" + content + "<|im_end|>")
        return (
            "\n".join(formatted_parts) + "\n<|im_start|>assistant\n" + ("<think>\n\n</think>\n\n" if no_think else "")
        )

    def _format_mistral(self, messages: list[dict]) -> str:
        """Instruct format for Ministral/Mistral models."""
        system_content = ""
        turns = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_content = content
            elif role == "user":
                if system_content:
                    turns.append(f"[INST] {system_content}\n{content} [/INST]")
                    system_content = ""
                else:
                    turns.append(f"[INST] {content} [/INST]")
            elif role == "assistant":
                turns.append(content)
        return " ".join(turns)


class ModelRegistry:
    """Singleton registry managing LLM model instances.

    Handles loading/unloading of models on-demand, ensuring only one model
    is loaded at a time. Thread-safe.
    """

    _instance: ModelRegistry | None = None

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._current: LlamaCppBackend | None = None
        self._current_capability: str | None = None

    def __new__(cls) -> ModelRegistry:
        """Ensure singleton behavior."""
        if cls._instance is None:
            with threading.Lock():
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def get_backend(self, capability: str) -> LlamaCppBackend:
        """Get a backend instance for the given capability.

        If a different model is currently loaded, it will be unloaded
        and the requested model loaded in its place. Thread-safe.

        Args:
            capability: Capability key (e.g., "chat", "vision", "reasoning").

        Returns:
            Backend instance ready for inference.

        Raises:
            RuntimeError: If no model exists for the given capability.
        """
        with self._lock:
            # Validate capability
            model_path = CAPABILITY_MAP.get(capability)
            if model_path is None:
                raise RuntimeError(
                    f"No GGUF model registered for capability '{capability}'. "
                    f"Available capabilities: {', '.join(CAPABILITY_MAP.keys())}"
                )

            # Check if model file exists
            if not model_path.exists():
                raise RuntimeError(
                    f"Model file missing for '{capability}' ({model_path}). "
                    "Please download the GGUF model and ensure the path is correct."
                )

            # Determine required multimodal projection (if any)
            mmproj_path: Path | None = _MMPROJ_MAP.get(model_path)

            # If same model already loaded, return it
            if (
                self._current is not None
                and self._current.model_path == model_path
                and self._current.mmproj_path == mmproj_path
            ):
                return self._current

            # Unload current model if different
            if self._current is not None:
                print(
                    f"[Roamin] Switching model: unloading '{self._current_capability}'" f" → loading '{capability}'",
                    flush=True,
                )
                self.unload_all()
                print("[Roamin] Previous model unloaded, VRAM freed.", flush=True)

            # Create and load new backend
            try:
                import time as _time

                n_ctx = _CAPABILITY_N_CTX.get(capability, 8192)
                print(
                    f"[Roamin] Loading '{capability}' model (n_ctx={n_ctx})" f" — this may take 30-90s...",
                    flush=True,
                )
                _t0_load = _time.perf_counter()
                backend = LlamaCppBackend(
                    model_path=model_path,
                    n_gpu_layers=-1,  # Full GPU offload for fastest inference
                    n_ctx=n_ctx,
                    mmproj_path=mmproj_path,
                )
                backend.load()
                print(
                    f"[Roamin] '{capability}' model ready in {_time.perf_counter() - _t0_load:.1f}s",
                    flush=True,
                )
                self._current = backend
                self._current_capability = capability
                return backend
            except RuntimeError as e:
                raise RuntimeError(f"Failed to initialize {capability} model: {e}")

    def unload_all(self) -> None:
        """Unload all currently loaded models, freeing memory."""
        with self._lock:
            if self._current is not None:
                self._current.unload()
                self._current = None
                self._current_capability = None


# Module-level singleton instance
_REGISTRY = ModelRegistry()


def get_llm_response(
    prompt: str,
    capability: str = "default",
    max_tokens: int = 512,
    temperature: float = 0.7,
    messages: list[dict] | None = None,
    no_think: bool = False,
    stream_think: bool = False,
) -> str:
    """Get LLM response using in-process inference.

    Args:
        prompt: Input prompt string (used if messages is None).
        capability: Model capability to use ("default", "chat", "vision", etc.).
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = random).
        messages: Optional list of message dicts. If provided, uses chat mode.
        no_think: If True, suppress <think> blocks.
        stream_think: If True and no_think is False, print <think> tokens to terminal.

    Returns:
        LLM response string stripped of whitespace.

    Raises:
        RuntimeError: If model loading fails or llama-cpp-python unavailable.
    """
    if messages is not None:
        backend = _REGISTRY.get_backend(capability)
        return backend.chat(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            no_think=no_think,
            stream_think=stream_think,
        )

    # Generation mode (no streaming — think blocks not used in raw prompts)
    backend = _REGISTRY.get_backend(capability)
    return backend.generate(prompt, max_tokens=max_tokens, temperature=temperature)
