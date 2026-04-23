"""LlamaCpp-based in-process LLM inference backend for Roamin.

This module eliminates external server dependencies by loading GGUF models directly
via llama-cpp-python. CAPABILITY_MAP is built dynamically at import time by scanning
configured model directories — no hardcoded paths or model-name assumptions.

To add a new model family: add a rule to _MODEL_FAMILY_RULES below and restart Roamin.
To try a new model: download the GGUF and restart — if it matches an existing rule it
is picked up automatically.
"""

from __future__ import annotations

import re
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

# ---------------------------------------------------------------------------
# Model family rules — priority-ordered.
#
# Each rule maps a filename-matching regex to the capabilities that model
# provides. First matching model found on disk wins each capability (lower
# index = higher priority). If two rules compete for the same capability,
# the higher-priority rule wins and the lower-priority rule skips it.
#
# text_caps:   {capability: n_ctx}  — loaded WITHOUT mmproj
# vision_caps: {capability: n_ctx}  — loaded WITH mmproj (skipped if no mmproj on disk)
#
# n_ctx guidance:
#   32768 — reasoning / chat tasks (no mmproj VRAM overhead)
#   16384 — fast text or code tasks
#    8192 — vision tasks (mmproj adds ~350MB VRAM; tighter ctx keeps total bounded)
# ---------------------------------------------------------------------------
_MODEL_FAMILY_RULES: list[dict] = [
    {
        # DeepSeek R1 — native <think> blocks, best default + reasoning model
        "pattern": re.compile(r"deepseek.*r1", re.IGNORECASE),
        "text_caps": {"default": 32768, "chat": 32768, "reasoning": 32768, "analysis": 32768},
        "vision_caps": {},
    },
    {
        # Qwen VL family — vision-language model; also handles fast text tasks without mmproj
        "pattern": re.compile(r"qwen.*\bvl\b", re.IGNORECASE),
        "text_caps": {"fast": 16384},
        "vision_caps": {"vision": 8192, "screen_reading": 8192},
    },
    {
        # Qwen Coder — heavy code generation
        "pattern": re.compile(r"qwen.*coder|coder.*next", re.IGNORECASE),
        "text_caps": {"code": 16384, "heavy_code": 16384},
        "vision_caps": {},
    },
    {
        # Ministral — vision + reasoning in one model
        "pattern": re.compile(r"ministral", re.IGNORECASE),
        "text_caps": {"ministral": 32768, "ministral_reasoning": 32768},
        "vision_caps": {"ministral_vision": 32768},
    },
    {
        # Fallback: large reasoning distillations (fills reasoning/analysis if DeepSeek absent)
        "pattern": re.compile(r"reasoning.*distill|qwen.*27b", re.IGNORECASE),
        "text_caps": {"reasoning": 32768, "analysis": 32768},
        "vision_caps": {},
    },
]


def _build_capability_map() -> tuple[dict[str, Path], dict[str, int], dict[Path, Path], frozenset[str]]:
    """Scan available GGUF files and build routing tables from what is on disk.

    Calls model_scanner.scan_models() which checks model_scan_paths from settings
    plus ~/.lmstudio/models. Walks _MODEL_FAMILY_RULES in priority order; first
    matching model wins each capability.

    Returns:
        cap_map:      capability → model Path  (no None values)
        ctx_map:      capability → n_ctx tokens
        mmproj_map:   model Path → mmproj Path (vision models only)
        vision_caps:  frozenset of capabilities that require mmproj at load time
    """
    try:
        from agent.core.model_scanner import scan_models

        models = scan_models()
    except Exception as exc:
        print(f"[Roamin] WARNING: Model scan failed ({exc}) — no capabilities registered", flush=True)
        return {}, {}, {}, frozenset()

    cap_map: dict[str, Path] = {}
    ctx_map: dict[str, int] = {}
    mmproj_map: dict[Path, Path] = {}
    vision_caps: set[str] = set()

    for rule in _MODEL_FAMILY_RULES:
        pattern = rule["pattern"]
        matched = None

        # Find first model whose filename matches this rule
        for model in models:
            if pattern.search(model["id"]) or pattern.search(model["name"]):
                matched = model
                break

        if matched is None:
            continue

        model_path = Path(matched["file_path"])
        has_mmproj = bool(matched.get("mmproj_path"))

        if has_mmproj:
            mmproj_map[model_path] = Path(matched["mmproj_path"])

        # Register text capabilities (no mmproj overhead)
        for cap, n_ctx in rule["text_caps"].items():
            if cap not in cap_map:
                cap_map[cap] = model_path
                ctx_map[cap] = n_ctx

        # Register vision capabilities (requires paired mmproj file)
        for cap, n_ctx in rule["vision_caps"].items():
            if cap in cap_map:
                continue  # Already claimed by a higher-priority rule
            if not has_mmproj:
                continue  # No projection file — cannot enable this vision capability
            cap_map[cap] = model_path
            ctx_map[cap] = n_ctx
            vision_caps.add(cap)

    if cap_map:
        print(f"[Roamin] Capabilities: {', '.join(sorted(cap_map))}", flush=True)
    else:
        print("[Roamin] WARNING: No GGUF models found — LLM inference unavailable", flush=True)

    return cap_map, ctx_map, mmproj_map, frozenset(vision_caps)


CAPABILITY_MAP, _CAPABILITY_N_CTX, _MMPROJ_MAP, _VISION_CAPABILITIES = _build_capability_map()


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

        # If the prompt already ends with <think>\n, the model will generate
        # think content immediately — start in think mode and prepend the tag
        # to full_text so the caller's strip regex can match <think>...</think>.
        prompt_forced_think = prompt.rstrip().endswith("<think>")
        full_text = "<think>\n" if prompt_forced_think else ""
        in_think = prompt_forced_think
        buffer = ""

        assert self._llm is not None
        print("[Roamin] Inference started (streaming)...", flush=True)
        if prompt_forced_think:
            print(f"\n{BOLD_CYAN}[Roamin thinking...]{RESET}", flush=True)

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
        if in_think:
            if buffer:
                print(f"{DIM_CYAN}{buffer}{RESET}", end="", flush=True)
            print(f"\n{BOLD_CYAN}[Roamin done thinking — token budget exhausted]{RESET}\n", flush=True)
            # Model hit max_tokens DURING the think block — never generated </think> or an answer.
            # Close the tag so the caller's regex can strip <think>...</think> cleanly.
            # Without this, the unclosed block leaks raw thinking content into TTS.
            full_text += "\n</think>"

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
            "\n".join(formatted_parts)
            + "\n<|im_start|>assistant\n"
            + ("<think>\n\n</think>\n\n" if no_think else "<think>\n")
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
                avail = ", ".join(sorted(CAPABILITY_MAP)) if CAPABILITY_MAP else "none — no GGUF models found on disk"
                raise RuntimeError(f"No GGUF model registered for capability '{capability}'. " f"Available: {avail}")

            # Check if model file exists (guards against deletion after startup scan)
            if not model_path.exists():
                raise RuntimeError(
                    f"Model file missing for '{capability}' ({model_path.name}). "
                    "File may have been moved or deleted since startup."
                )

            # Determine required multimodal projection (if any).
            # Only load mmproj for capabilities that actually process images.
            if capability in _VISION_CAPABILITIES:
                mmproj_path: Path | None = _MMPROJ_MAP.get(model_path)
            else:
                mmproj_path = None

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


def unload_current_model() -> None:
    """Unload the currently active LLM, freeing VRAM for other processes (e.g. Chatterbox TTS).

    Safe to call at any time — no-op if no model is loaded.
    """
    _REGISTRY.unload_all()


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


def stream_chat_completion(
    messages: list[dict],
    capability: str = "default",
    max_tokens: int = 2048,
    temperature: float = 0.7,
    top_p: float = 0.95,
    top_k: int = 40,
    repeat_penalty: float = 1.1,
):
    """Yield token strings from llama-cpp-python's streaming chat completion.

    Uses the module-level _REGISTRY to get (or load) the backend, then calls
    create_chat_completion with stream=True.  Meant to be run in a thread and
    fed into an asyncio.Queue for SSE delivery.

    Yields:
        str: Individual token text chunks as they are generated.

    Raises:
        RuntimeError: If llama-cpp-python is unavailable or model fails to load.
    """
    backend = _REGISTRY.get_backend(capability)
    if backend._llm is None:
        raise RuntimeError("Model not loaded")

    stream = backend._llm.create_chat_completion(
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repeat_penalty=repeat_penalty,
        stream=True,
    )
    for chunk in stream:
        delta = chunk["choices"][0].get("delta", {}).get("content", "") or ""
        if delta:
            yield delta
