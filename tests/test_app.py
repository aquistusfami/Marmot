"""Headless TUI tests (no privileged action and no real cleaning is ever triggered)."""
import asyncio
import unittest
from unittest.mock import patch

from textual.widgets import TabbedContent

from marmot.app import MarmotApp

TABS = ["pane-monitor", "pane-cleaner", "pane-uninstaller", "pane-analyzer", "pane-optimizer"]

FAKE_SCAN = {
    'user_cache': {'name': "User Caches", 'path': "/nonexistent/.cache", 'size': 300, 'size_str': "300 B",
                   'desc': "", 'requires_sudo': False,
                   'children': [{'name': "a", 'path': "/nonexistent/.cache/a", 'size': 200, 'size_str': "200 B"},
                                {'name': "b", 'path': "/nonexistent/.cache/b", 'size': 100, 'size_str': "100 B"}]},
    'trash': {'name': "System Trash", 'path': "/nonexistent/Trash", 'size': 0, 'size_str': "0 B",
              'desc': "", 'requires_sudo': False},
}


def run(coro):
    return asyncio.run(coro)


class TestAppSmoke(unittest.TestCase):
    def test_mount_and_switch_tabs(self):
        async def go():
            app = MarmotApp()
            async with app.run_test(size=(140, 45)) as pilot:
                tabs = app.query_one(TabbedContent)
                for tab in TABS:
                    tabs.active = tab
                    await pilot.pause()
                    self.assertEqual(tabs.active, tab)
                await pilot.press("q")
        run(go())

    def test_cleaner_scan_then_preview(self):
        async def go():
            app = MarmotApp()
            calls = []

            def fake_clean(item_id, data, dry_run=False, selected=None, use_trash=True):
                calls.append((item_id, dry_run, selected))
                return True, "would do it"

            with patch.object(app.cleaner, "scan", return_value=FAKE_SCAN), \
                 patch.object(app.cleaner, "clean", side_effect=fake_clean):
                async with app.run_test(size=(140, 45)) as pilot:
                    app.query_one(TabbedContent).active = "pane-cleaner"
                    await pilot.pause()
                    await pilot.click("#btn-clean-scan")
                    await app.workers.wait_for_complete()
                    await pilot.pause()
                    # defaults: user cache + trash ticked, every cache folder ticked
                    self.assertEqual(set(app.clean_items.selected), {"user_cache", "trash"})
                    self.assertEqual(len(app.clean_cache.selected), 2)
                    app.clean_cache.deselect("/nonexistent/.cache/b")
                    await pilot.click("#btn-clean-preview")
                    await app.workers.wait_for_complete()
                    await pilot.pause()
            self.assertIn(("user_cache", True, ["/nonexistent/.cache/a"]), calls)
            self.assertTrue(all(dry for _, dry, _ in calls))
        run(go())


class TestAppSafety(unittest.TestCase):
    def test_clean_asks_for_confirmation_and_cancel_does_nothing(self):
        async def go():
            app = MarmotApp()
            with patch.object(app.cleaner, "scan", return_value=FAKE_SCAN), \
                 patch.object(app.cleaner, "clean", return_value=(True, "done")) as clean:
                async with app.run_test(size=(140, 45)) as pilot:
                    await pilot.press("2")
                    await pilot.click("#btn-clean-scan")
                    await app.workers.wait_for_complete()
                    await pilot.pause()
                    await pilot.click("#btn-clean-run")
                    await pilot.pause()
                    self.assertEqual(type(app.screen).__name__, "ConfirmScreen")
                    await pilot.press("escape")
                    await app.workers.wait_for_complete()
                    await pilot.pause()
                    clean.assert_not_called()
        run(go())

    def test_analyzer_refuses_trash_outside_home(self):
        import tempfile
        from pathlib import Path

        async def go():
            app = MarmotApp()
            with tempfile.TemporaryDirectory() as outside, \
                 patch("marmot.trash.move_to_trash") as mv:
                Path(outside, "f").write_text("x")
                async with app.run_test(size=(140, 45)) as pilot:
                    app.analyzer.set_path(outside)
                    await pilot.press("4")
                    app.refresh_analyzer()
                    await app.workers.wait_for_complete()
                    await pilot.pause()
                    app.analyzer_list.index = 0
                    app.action_analyzer_trash()
                    await pilot.pause()
                    self.assertNotEqual(type(app.screen).__name__, "ConfirmScreen")
                mv.assert_not_called()
        run(go())

    def test_timers_after_exit_do_not_crash(self):
        """Regression: interval/worker callbacks firing during shutdown raised NoMatches (flaky CI)."""
        async def go():
            app = MarmotApp()
            async with app.run_test() as pilot:
                await pilot.pause()
            return app
        app = run(go())
        app.update_monitor_dashboard()
        app.update_processes()
        app._show_check("trim", {'applicable': True, 'status': "ok"})

    def test_number_keys_switch_tabs(self):
        async def go():
            app = MarmotApp()
            async with app.run_test(size=(140, 45)) as pilot:
                for key, tab in (("5", "pane-optimizer"), ("3", "pane-uninstaller"), ("1", "pane-monitor")):
                    await pilot.press(key)
                    await pilot.pause()
                    self.assertEqual(app.query_one(TabbedContent).active, tab)
        run(go())


if __name__ == "__main__":
    unittest.main()
