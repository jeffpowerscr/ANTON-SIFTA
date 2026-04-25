#!/usr/bin/env python3
"""
swarm_kernel_config.py - shared runtime constants for SIFTA UI widgets.

This module is intentionally small: it centralizes the knobs that Talk to Alice
imports at startup while still allowing local overrides through environment
variables.
"""
from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


_OLLAMA_URL = os.environ.get("SIFTA_OLLAMA_URL", "http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434"
_DEFAULT_WHISPER_MODEL = os.environ.get("SIFTA_WHISPER_MODEL", "tiny.en").strip() or "tiny.en"

# Audio Engine
_AUDIO_RATE = _env_int("SIFTA_AUDIO_RATE", 16000)
_AUDIO_CHANS = _env_int("SIFTA_AUDIO_CHANS", 1)
_MAX_RECORD_S = _env_int("SIFTA_MAX_RECORD_S", 60)
_SOFT_CLIP_CEIL = _env_float("SIFTA_SOFT_CLIP_CEIL", 0.98)
_PEAK_TARGET = _env_float("SIFTA_PEAK_TARGET", 0.90)
_PEAK_NORM_FLOOR = _env_float("SIFTA_PEAK_NORM_FLOOR", 0.05)
_VAD_NOISE_HALFLIFE_S = _env_float("SIFTA_VAD_NOISE_HALFLIFE_S", 4.0)

# Memory Context Window
_HISTORY_TURNS = _env_int("SIFTA_HISTORY_TURNS", 8)
_GROUNDED_HISTORY_TURNS = _env_int("SIFTA_GROUNDED_HISTORY_TURNS", 3)

# Response and TTS constraints
_MAX_RESPONSE_CHARS = _env_int("SIFTA_MAX_RESPONSE_CHARS", 1200)
_TTS_MAX_CHARS_DEFAULT = _env_int("SIFTA_TTS_MAX_CHARS", 320)

__all__ = [
    "_OLLAMA_URL",
    "_DEFAULT_WHISPER_MODEL",
    "_AUDIO_RATE",
    "_AUDIO_CHANS",
    "_MAX_RECORD_S",
    "_MAX_RESPONSE_CHARS",
    "_SOFT_CLIP_CEIL",
    "_PEAK_TARGET",
    "_PEAK_NORM_FLOOR",
    "_VAD_NOISE_HALFLIFE_S",
    "_HISTORY_TURNS",
    "_GROUNDED_HISTORY_TURNS",
    "_TTS_MAX_CHARS_DEFAULT",
]
