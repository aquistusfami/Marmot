"""Headless smoke test: the TUI mounts and every tab renders (no privileged action is triggered)."""
import asyncio
import unittest

from textual.widgets import TabbedContent

from marmot.app import MarmotApp

TABS = ["pane-monitor", "pane-cleaner", "pane-uninstaller", "pane-analyzer", "pane-optimizer"]


class TestAppSmoke(unittest.TestCase):
    def test_mount_and_switch_tabs(self):
        async def run():
            app = MarmotApp()
            async with app.run_test(size=(140, 45)) as pilot:
                tabs = app.query_one(TabbedContent)
                for tab in TABS:
                    tabs.active = tab
                    await pilot.pause()
                    self.assertEqual(tabs.active, tab)
                # the package-cache checkbox exists only when a backend was detected
                self.assertEqual(bool(app.query("#chk-pkg-cache")), app.cleaner.pm is not None)
                await pilot.press("q")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
