"""Helpers for detecting and preparing the local Ollama AI engine."""

import json
import logging
import subprocess
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemma3:4b"
MODEL_CHOICES = {
    "Gemma 3 (recommended)": "gemma3:4b",
    "Llama 3.2": "llama3.2:3b",
}


def ollama_models(ollama_url: str) -> Optional[list[str]]:
    """Return installed Ollama model names, or None when Ollama is unavailable."""
    try:
        response = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=3)
        response.raise_for_status()
        data = response.json()
        return [item.get("name", "") for item in data.get("models", []) if item.get("name")]
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.info("Ollama is unavailable: %s", exc)
        return None


def model_is_available(model: str, ollama_url: str) -> bool:
    """Check whether the configured model is installed in the local Ollama store."""
    installed = ollama_models(ollama_url)
    if installed is None:
        return False
    return any(name == model or name.split(":")[0] == model.split(":")[0] for name in installed)


def pull_model(model: str) -> int:
    """Ask the Ollama CLI to download a model and stream its progress to the terminal."""
    try:
        return subprocess.run(["ollama", "pull", model], check=False).returncode
    except FileNotFoundError:
        return 127
