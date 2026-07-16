import asyncio
from marmot import MarmotApp

async def main():
    app = MarmotApp()
    
    print("=== Running Textual Diagnostic Test ===")
    async with app.run_test() as pilot:
        # Let the app run a bit to execute timers
        await pilot.pause(1.5)
        
        print(f"Active Screen: {app.screen}")
        print(f"Screen Size: {app.screen.size}")
        
        with open("layout_diagnostics.txt", "w") as out_file:
            out_file.write("=== Diagnosing Widget Tree Across Tabs ===\n")
            out_file.write(f"Screen size: {app.screen.size}\n\n")
            
            tab_ids = ["pane-monitor", "pane-cleaner", "pane-uninstaller", "pane-analyzer", "pane-optimizer"]
            tabs_widget = app.query_one("#tabs-main")
            
            for tab_id in tab_ids:
                tabs_widget.active = tab_id
                await pilot.pause(0.2)
                
                out_file.write(f"\n--- ACTIVE TAB: {tab_id} ---\n")
                # Find all children of the switcher that are descendants of this active tab
                for widget in app.query(f"#{tab_id} *"):
                    indent = "  " * len(list(widget.ancestors))
                    widget_type = type(widget).__name__
                    widget_id = widget.id or "None"
                    classes = " ".join(widget.classes) if widget.classes else "None"
                    size = widget.size
                    visible = widget.visible
                    out_file.write(f"{indent}- {widget_type} (id={widget_id}, classes={classes}) | Size: {size} | Visible: {visible}\n")
            
        print("\n--- Diagnostic file layout_diagnostics.txt generated successfully ---")

if __name__ == "__main__":
    asyncio.run(main())
