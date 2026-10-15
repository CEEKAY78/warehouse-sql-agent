"""Thin clients for a local Ollama server (http://localhost:11434): chat and embeddings."""

from __future__ import annotations

import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


class OllamaChat:
    def __init__(self, model: str, temperature: float = 0.0, timeout_s: float = 300.0,
                 num_ctx: int = 8192):
        self.model = model
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.num_ctx = num_ctx

    def chat(self, messages: list[dict], schema: dict | None = None) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,  # qwen3: no hidden reasoning tokens (slow on a 6 GB GPU)
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        if schema is not None:
            body["format"] = schema
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=self.timeout_s)
        if resp.status_code == 400 and "think" in resp.text:
            body.pop("think")  # models without a thinking mode reject the flag
            resp = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=self.timeout_s)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


class OllamaEmbedder:
    def __init__(self, model: str = "bge-m3", timeout_s: float = 120.0):
        self.model = model
        self.timeout_s = timeout_s

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = requests.post(f"{OLLAMA_URL}/api/embed",
                             json={"model": self.model, "input": texts}, timeout=self.timeout_s)
        resp.raise_for_status()
        return resp.json()["embeddings"]
