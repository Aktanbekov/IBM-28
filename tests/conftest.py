"""Tests never call a real model: a teammate's local Ollama or watsonx keys must not change results.
Tests that need another backend set LLM_BACKEND themselves (monkeypatch)."""
import os
import tempfile

os.environ["LLM_BACKEND"] = "rules"
# Tests get their own database file, never the demo's data/casebridge.db.
os.environ["CASEBRIDGE_DB"] = os.path.join(tempfile.mkdtemp(prefix="casebridge-test-"), "test.db")
