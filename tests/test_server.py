#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from server import idle_should_exit  # noqa: E402


class IdleWatchTests(unittest.TestCase):
    def test_idle_exit_requires_minutes_and_silence(self):
        now = 1_000.0
        self.assertFalse(idle_should_exit(
            idle_minutes=15, playing=False, client_count=0,
            last_activity=now, now=now))
        self.assertTrue(idle_should_exit(
            idle_minutes=15, playing=False, client_count=0,
            last_activity=now - 15 * 60, now=now))

    def test_idle_exit_skips_playing_and_connected_clients(self):
        now = 1_000.0
        self.assertFalse(idle_should_exit(
            idle_minutes=15, playing=True, client_count=0,
            last_activity=now - 15 * 60, now=now))
        self.assertFalse(idle_should_exit(
            idle_minutes=15, playing=False, client_count=1,
            last_activity=now - 15 * 60, now=now))
        self.assertFalse(idle_should_exit(
            idle_minutes=0, playing=False, client_count=0,
            last_activity=now - 15 * 60, now=now))


if __name__ == "__main__":
    unittest.main()
