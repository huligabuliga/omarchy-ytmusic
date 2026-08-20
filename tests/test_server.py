#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import player  # noqa: E402
from server import (  # noqa: E402
    Backend,
    idle_should_exit,
    pick_authuser,
)
import server  # noqa: E402


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


class StreamCacheWarmUpTests(unittest.TestCase):
    """Solving YouTube's player JS challenge before the first play."""

    def setUp(self):
        self._runtime = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = self._runtime.name
        self.backend = Backend(Path(self._runtime.name) / "absent.json")

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self._previous
        self._runtime.cleanup()

    def test_warm_up_is_skipped_when_the_cache_is_already_warm(self):
        with mock.patch.object(player, "yt_dlp_cache_warm", return_value=True), \
             mock.patch.object(self.backend, "_catalog_video_id") as picker:
            self.backend._warm_stream_cache()
        picker.assert_not_called()

    def test_warm_up_uses_a_catalog_video_not_a_hardcoded_one(self):
        with mock.patch.object(player, "yt_dlp_cache_warm", return_value=False), \
             mock.patch.object(self.backend, "_catalog_video_id",
                               return_value="dQw4w9wgkcQ") as picker, \
             mock.patch.object(self.backend.player.resolver, "resolve") as resolve:
            self.backend._warm_stream_cache()
            for _ in range(50):
                if picker.called and resolve.called:
                    break
                time.sleep(0.02)
        picker.assert_called_once_with()
        resolve.assert_called_once_with("dQw4w9wgkcQ")

    def test_state_reports_whether_a_resolve_is_in_flight(self):
        self.assertIs(self.backend.state()["resolving"], False)
        self.backend.player.resolving = True
        self.assertIs(self.backend.state()["resolving"], True)


if __name__ == "__main__":
    unittest.main()


class AuthUserSelectionTests(unittest.TestCase):
    def test_prefers_the_account_with_the_most_liked_songs(self):
        self.assertEqual(pick_authuser({"0": 1, "1": 311}), "1")

    def test_keeps_slot_zero_unless_another_slot_beats_it(self):
        self.assertEqual(pick_authuser({"0": 12, "1": 12}), "0")
        self.assertEqual(pick_authuser({}), "0")

    def test_set_authuser_rewrites_only_the_account_slot(self):
        import json

        import auth

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "browser.json"
            path.write_text(json.dumps({"cookie": "SID=x", "x-goog-authuser": "0"}))
            auth.set_authuser(path, "2")
            headers = json.loads(path.read_text())
        self.assertEqual(headers["x-goog-authuser"], "2")
        self.assertEqual(headers["cookie"], "SID=x")


class ViewCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(
            server, "view_cache_dir", return_value=Path(self._tmp.name)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_a_written_view_reads_back_fresh(self):
        server.write_cached_view("liked", {"items": [{"videoId": "abc"}]})
        payload, age = server.read_cached_view("liked")
        self.assertEqual(payload["items"][0]["videoId"], "abc")
        self.assertLess(age, server.VIEW_CACHE_TTL)

    def test_a_missing_or_corrupt_view_reads_as_absent(self):
        self.assertIsNone(server.read_cached_view("liked"))
        (Path(self._tmp.name) / "liked.json").write_text("{not json")
        self.assertIsNone(server.read_cached_view("liked"))

    def test_dropping_without_names_clears_every_account_view(self):
        server.write_cached_view("liked", {"items": []})
        server.write_cached_view("playlists", {"items": []})
        server.drop_cached_views()
        self.assertIsNone(server.read_cached_view("liked"))
        self.assertIsNone(server.read_cached_view("playlists"))

    def test_dropping_by_name_leaves_the_others(self):
        server.write_cached_view("liked", {"items": []})
        server.write_cached_view("playlists", {"items": []})
        server.drop_cached_views("liked")
        self.assertIsNone(server.read_cached_view("liked"))
        self.assertIsNotNone(server.read_cached_view("playlists"))
