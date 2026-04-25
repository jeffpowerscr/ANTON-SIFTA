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


_OLLAMA_URL = os.environ.get("SIFTA_OLLAMA_URL", "http://127.0.0.1:11434")

# Whisper and sounddevice both behave best with 16 kHz mono float32 input.
_AUDIO_RATE = _env_int("SIFTA_AUDIO_RATE", 16000)
_AUDIO_CHANS = _env_int("SIFTA_AUDIO_CHANS", 1)
_DEFAULT_WHISPER_MODEL = os.environ.get("SIFTA_WHISPER_MODEL", "tiny.en")

# Conversation and response bounds.
_HISTORY_TURNS = _env_int("SIFTA_HISTORY_TURNS", 8)
_MAX_RESPONSE_CHARS = _env_int("SIFTA_MAX_RESPONSE_CHARS", 2400)
_TTS_MAX_CHARS_DEFAULT = _env_int("SIFTA_TTS_MAX_CHARS", 420)

# VAD adaptive noise-floor decay. Higher values adapt more slowly.
_VAD_NOISE_HALFLIFE_S = _env_float("SIFTA_VAD_NOISE_HALFLIFE_S", 2.0)


__all__ = [
    "_OLLAMA_URL",
    "_AUDIO_RATE",
    "_AUDIO_CHANS",
    "_DEFAULT_WHISPER_MODEL",
    "_HISTORY_TURNS",
    "_MAX_RESPONSE_CHARS",
    "_TTS_MAX_CHARS_DEFAULT",
    "_VAD_NOISE_HALFLIFE_S",
]
