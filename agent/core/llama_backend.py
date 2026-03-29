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
except ImportError:
    Llama = None  # type: ignore

# Model paths validated at runtime (not import time)
QWEN3_8B = Path(
    r"C:\Users\Asherre Roamin\.ollama\models\blobs\sha256-a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f"  # noqa: E501
)
QWEN3_8B = QWEN3_8B if QWEN3_8B.exists() else None

QWEN35_9B = Path(
    r"C:\Users\Asherre Roamin\.lmstudio\models\lmstudio-community" r"\Qwen3.5-9B-GGUF\Qwen3.5-9B-Q4_K_M.gguf"
)
QWEN35_9B = QWEN35_9B if QWEN35_9B.exists() else None

QWEN35_9B_MMPROJ = Path(
    r"C:\Users\Asherre Roamin\.lmstudio\models\lmstudio-community\Qwen3.5-9B-GGUF\mmproj-Qwen3.5-9B-BF16.gguf"
)
QWEN35_9B_MMPROJ = QWEN35_9B_MMPROJ if QWEN35_9B_MMPROJ.exists() else None

DEEPSEEK_R1_8B = Path(r"C:\Users\Asherre Roamin\.lmstudio\models" r"\DeepSeek-R1-0528-Qwen3-8B-Q4_K_M.gguf")
DEEPSEEK_R1_8B = DEEPSEEK_R1_8B if DEEPSEEK_R1_8B.exists() else None

MINISTRAL_14B = Path(
    r"C:\Users\Asherre Roamin\.lmstudio\models\lmstudio-community\Ministral-3-14B-Reasoning-2512-GGUF\Ministral-3-14B-Reasoning-2512-Q4_K_M.gguf"  # noqa: E501
)
MINISTRAL_14B = MINISTRAL_14B if MINISTRAL_14B.exists() else None

QWEN3_CODER_NEXT = Path(
    r"C:\Users\Asherre Roamin\.lmstudio\models\lmstudio-community\Qwen3-Coder-Next-GGUF\Qwen3-Coder-Next-Q4_K_M.gguf"
)
QWEN3_CODER_NEXT = QWEN3_CODER_NEXT if QWEN3_CODER_NEXT.exists() else None


CAPABILITY_MAP: dict[str, Path | None] = {
    "default": QWEN3_8B,
    "chat": QWEN3_8B,
    "fast": QWEN3_8B,
    "vision": QWEN35_9B,
    "screen_reading": QWEN35_9B,
    "reasoning": DEEPSEEK_R1_8B,
    "analysis": DEEPSEEK_R1_8B,
    "code": QWEN3_CODER_NEXT,
    "heavy_code": QWEN3_CODER_NEXT,
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
            kwargs["mmproj"] = str(self.mmproj_path)

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
    ) -> str:
        """Generate a chat completion from a message list.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                      Roles: "user", "system", or "assistant".
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = random).
            stop: Optional list of stop sequences.

        Returns:
            Assistant reply string stripped of leading/trailing whitespace.

        Raises:
            RuntimeError: If model not loaded or llama-cpp-python unavailable.
        """
        if not self.is_loaded():
            raise RuntimeError("Model must be loaded before calling chat().")

        # Convert message dicts to llama-cpp format
        prompt = self._format_messages_as_prompt(messages, no_think=no_think)

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
        """Convert message list to ChatML prompt format for Qwen3/DeepSeek models.

        Format:
            <|im_start|>system
            {system_content}<|im_end|>
            <|im_start|>user
            {user_content}<|im_end|>
            <|im_start|>assistant

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            no_think: If True, suppress Qwen3 thinking mode by pre-filling
                      the assistant turn with an empty think block.
        """
        if not messages:
            return ""

        formatted_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                formatted_parts.append("<|im_start|>system\n" + content + "<|im_end|>")
            elif role == "assistant":
                formatted_parts.append("<|im_start|>assistant\n" + content + "<|im_end|>")
            else:  # user or unknown
                formatted_parts.append("<|im_start|>user\n" + content + "<|im_end|>")

        return (
            "\n".join(formatted_parts) + "\n<|im_start|>assistant\n" + ("<think>\n\n</think>\n\n" if no_think else "")
        )


class ModelRegistry:
    """Singleton registry managing LLM model instances.

    Handles loading/unloading of models on-demand, ensuring only one model
    is loaded at a time. Thread-safe.
    """

    _instance: ModelRegistry | None = None

    def __init__(self) -> None:
        self._lock = threading.Lock()
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
            mmproj_path: Path | None = None
            if capability in ("vision", "screen_reading"):
                mmproj_path = QWEN35_9B_MMPROJ

            # If same model already loaded, return it
            if (
                self._current is not None
                and self._current.model_path == model_path
                and self._current.mmproj_path == mmproj_path
            ):
                return self._current

            # Unload current model if different
            if self._current is not None:
                self.unload_all()

            # Create and load new backend
            try:
                backend = LlamaCppBackend(
                    model_path=model_path,
                    n_gpu_layers=-1,  # Full GPU offload - Chatterbox runs on CPU
                    mmproj_path=mmproj_path,
                )
                backend.load()
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
) -> str:
    """Get LLM response using in-process inference.

    Args:
        prompt: Input prompt string (used if messages is None).
        capability: Model capability to use ("default", "chat", "vision", etc.).
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = random).
        messages: Optional list of message dicts. If provided, uses chat mode.

    Returns:
        LLM response string stripped of whitespace.

    Raises:
        RuntimeError: If model loading fails or llama-cpp-python unavailable.
    """
    if messages is not None:
        backend = _REGISTRY.get_backend(capability)
        return backend.chat(messages, max_tokens=max_tokens, temperature=temperature, no_think=no_think)

    # Generation mode
    backend = _REGISTRY.get_backend(capability)
    return backend.generate(prompt, max_tokens=max_tokens, temperature=temperature)
