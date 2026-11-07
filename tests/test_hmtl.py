import importlib.machinery
import importlib.util
import json
import sys
import time
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "how-many-tokens-left"
loader = importlib.machinery.SourceFileLoader("hmtl", str(SRC))
spec = importlib.util.spec_from_loader("hmtl", loader)
hmtl = importlib.util.module_from_spec(spec)
sys.modules["hmtl"] = hmtl
loader.exec_module(hmtl)


def cfg(**over):
    c = json.loads(json.dumps(hmtl.DEFAULTS))
    c.update(over)
    return c


def acct(provider="claude", email="a@x.com", **wins):
    return hmtl.Account(
        provider=provider,
        email=email,
        label=hmtl.make_label(email, {}),
        windows={k.replace("w", ""): hmtl.Window(v) for k, v in wins.items()},
    )


class Parsers(unittest.TestCase):
    def test_claude_idle_five_hour(self):
        body = {"five_hour": None, "seven_day": {"utilization": 35.0, "resets_at": "2026-11-13T04:59:59.603373+00:00"}}
        w = hmtl.parse_claude_usage(body)
        self.assertNotIn("5h", w)
        self.assertEqual(w["7d"].remaining, 65)
        self.assertAlmostEqual(w["7d"].resets_at, 1794545999.6, places=0)

    def test_codex_maps_by_window_length(self):
        body = {"rate_limit": {
            "primary_window": {"used_percent": 20, "limit_window_seconds": 18000, "reset_at": 1},
            "secondary_window": {"used_percent": 37, "limit_window_seconds": 604800, "reset_at": 2},
        }}
        w = hmtl.parse_codex_usage(body)
        self.assertEqual(w["5h"].used, 20)
        self.assertEqual(w["7d"].used, 37)

    def test_codex_weekly_only_primary(self):
        body = {"rate_limit": {"primary_window": {"used_percent": 37, "limit_window_seconds": 604800, "reset_at": 9}, "secondary_window": None}}
        self.assertEqual(list(hmtl.parse_codex_usage(body)), ["7d"])

    def test_signals_fallback_and_staleness(self):
        future = str(int(time.time()) + 3600)
        sig = {
            "Anthropic-Ratelimit-Unified-5h-Utilization": "0.09",
            "Anthropic-Ratelimit-Unified-5h-Reset": "1",  # already rolled over
            "Anthropic-Ratelimit-Unified-7d-Utilization": "0.6",
            "Anthropic-Ratelimit-Unified-7d-Reset": future,
        }
        w = hmtl.parse_signals("claude", sig)
        self.assertNotIn("5h", w)
        self.assertAlmostEqual(w["7d"].remaining, 40)

        sig = {"X-Codex-Primary-Used-Percent": "37", "X-Codex-Primary-Window-Minutes": "10080",
               "X-Codex-Primary-Reset-At": future, "X-Codex-Secondary-Window-Minutes": "0"}
        self.assertEqual(hmtl.parse_signals("codex", sig)["7d"].used, 37)


class Aggregation(unittest.TestCase):
    def setUp(self):
        self.accts = [acct(email="a@one.com", w5h=10, w7d=100), acct(email="b@two.com", w7d=35)]

    def test_mean_min_sum(self):
        self.assertEqual(hmtl.pool(self.accts, "7d", "mean"), 32.5)
        self.assertEqual(hmtl.pool(self.accts, "7d", "min"), 0)
        self.assertEqual(hmtl.pool(self.accts, "7d", "sum"), 65)
        # b has no 5h window -> counts as untouched
        self.assertEqual(hmtl.pool(self.accts, "5h", "mean"), 95)

    def test_effective_is_binding_window(self):
        self.assertEqual(self.accts[0].effective, 0)
        self.assertEqual(self.accts[1].effective, 65)

    def test_unavailable_accounts_excluded(self):
        bad = acct(email="c@three.com")
        bad.source = "none"
        self.assertEqual(hmtl.pool(self.accts + [bad], "7d", "mean"), 32.5)

    def test_summary_hides_windows_nobody_has(self):
        s = hmtl.provider_summary([acct("codex", w7d=37)], cfg())
        self.assertEqual(s, {"codex": {"7d": 63}})


class Rendering(unittest.TestCase):
    def test_lowest_window_highlighted(self):
        c = cfg()
        out = hmtl.render_waybar([acct(w5h=20, w7d=70)], c, False, time.time())
        self.assertIn(f"foreground='{c['colors']['warning']}' weight='bold'>7d 30%", out["text"])
        self.assertIn(f"foreground='{c['colors']['dim']}'>5h 80%", out["text"])
        self.assertEqual(out["class"], ["warning"])
        self.assertEqual(out["percentage"], 30)

    def test_expanded_lists_accounts(self):
        out = hmtl.render_waybar([acct(email="me@example.com", w7d=10)], cfg(), True, time.time())
        self.assertIn("example", out["text"])
        self.assertIn("expanded", out["class"])

    def test_markup_is_escaped(self):
        a = acct(email="x&y@<evil>.com", w7d=1)
        out = hmtl.render_waybar([a], cfg(aliases={}), True, time.time())
        self.assertNotIn("<evil>", out["text"] + out["tooltip"])

    def test_reset_format(self):
        now = 1_000_000
        self.assertEqual(hmtl.fmt_reset(now + 90061, now), "1d 1h")
        self.assertEqual(hmtl.fmt_reset(now + 3720, now), "1h 02m")
        self.assertEqual(hmtl.fmt_reset(now - 5, now), "now")
        self.assertEqual(hmtl.fmt_reset(None, now), "—")


class Dither(unittest.TestCase):
    def lit(self, data, w, h, rgb):
        """count fill-coloured pixels per column"""
        cols = [0] * w
        for y in range(h):
            for x in range(w):
                i = (y * w + x) * 4
                if tuple(data[i:i + 3]) == rgb and data[i + 3] > 200:
                    cols[x] += 1
        return cols

    def test_size_and_bounds(self):
        for pct in (None, 0, 37.5, 100, 140):
            data = hmtl.dither_bar(pct, 101, 7, 2, (255, 0, 0), (9, 9, 9))
            self.assertEqual(len(data), 101 * 7 * 4)

    def test_fill_extent_and_ramp(self):
        w, h = 200, 16
        cols = self.lit(hmtl.dither_bar(50, w, h, 2, (255, 0, 0), (9, 9, 9)), w, h, (255, 0, 0))
        self.assertTrue(all(c == 0 for c in cols[102:]))   # nothing past 50%
        self.assertEqual(cols[99], h)                       # leading edge solid
        self.assertLess(sum(cols[:20]), sum(cols[80:100]))  # sparse -> dense
        self.assertGreater(sum(cols[:20]), 0)

    def test_empty_bar_has_only_track(self):
        data = hmtl.dither_bar(0, 64, 8, 1, (255, 0, 0), (9, 9, 9))
        self.assertEqual(sum(self.lit(data, 64, 8, (255, 0, 0))), 0)
        self.assertGreater(sum(self.lit(data, 64, 8, (9, 9, 9))) + sum(
            1 for i in range(0, len(data), 4) if data[i:i + 3] == bytes((9, 9, 9))), 0)


class SharedPoll(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = {k: getattr(hmtl, k) for k in ("STATE_DIR", "CACHE_PATH", "RUN_DIR", "LOCK_PATH", "fetch_all")}
        hmtl.STATE_DIR = self.tmp
        hmtl.CACHE_PATH = self.tmp / "last.json"
        hmtl.RUN_DIR = self.tmp
        hmtl.LOCK_PATH = self.tmp / "lock"
        self.calls = 0

        def fake_fetch(cfg):
            self.calls += 1
            time.sleep(0.2)
            return [acct(w7d=50)]

        hmtl.fetch_all = fake_fetch

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(hmtl, k, v)

    def test_concurrent_bars_poll_once(self):
        from concurrent.futures import ThreadPoolExecutor
        since = time.time()
        with ThreadPoolExecutor(4) as pool:
            snaps = list(pool.map(lambda _: hmtl.shared_poll(cfg(), since), range(4)))
        self.assertEqual(self.calls, 1)
        self.assertTrue(all(s.accounts[0].remaining("7d") == 50 for s in snaps))

    def test_failed_poll_keeps_previous_numbers(self):
        hmtl.shared_poll(cfg(), time.time())

        def boom(cfg):
            raise hmtl.QuotaError("down")

        hmtl.fetch_all = boom
        snap = hmtl.shared_poll(cfg(), time.time() + 1)
        self.assertEqual(snap.error, "down")
        self.assertEqual(snap.accounts[0].remaining("7d"), 50)
        self.assertIn("stale", hmtl.render_snapshot(snap, cfg())["class"])


if __name__ == "__main__":
    unittest.main()
