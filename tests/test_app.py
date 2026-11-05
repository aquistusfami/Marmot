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


if __name__ == "__main__":
    unittest.main()
