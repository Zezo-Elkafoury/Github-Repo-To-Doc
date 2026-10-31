"""Pytest configuration (offline by default)."""

import os

# Ensure offline/default tests never accidentally hit the network or require
# real model credentials. Real-model opt-in tests set this explicitly.
os.environ.setdefault("GITHUB_TO_DOCS_OFFLINE", "1")
