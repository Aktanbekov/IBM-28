"""Tests never call a real model: a teammate's local Ollama or watsonx keys must not change results.
Tests that need another backend set LLM_BACKEND themselves (monkeypatch)."""
import os

os.environ["LLM_BACKEND"] = "rules"
