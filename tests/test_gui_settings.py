import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Windows Tk settings smoke test")
class GUISettingsTests(unittest.TestCase):
    def test_deadline_checkbox_updates_only_the_isolated_settings(self):
        import tkinter as tk
        from tkinter import ttk
        from argparse import Namespace
        from core.settings import Settings
        from gui.components import SettingsPanel

        with tempfile.TemporaryDirectory() as directory, patch("core.settings.SETTINGS_PATH", Path(directory, "settings.json")):
            settings = Settings(Namespace())
            manager = SimpleNamespace(_twitch=SimpleNamespace(settings=settings, state_change=lambda _: lambda: None))
            root = tk.Tk()
            root.withdraw()
            try:
                with patch.object(SettingsPanel, "update_autostart"):
                    panel = SettingsPanel(manager, ttk.Frame(root))
                self.assertFalse(panel._vars["skip_unfinishable_drops"].get())
                def widgets(parent):
                    for child in parent.winfo_children():
                        yield child
                        yield from widgets(child)
                control = next(widget for widget in widgets(root)
                    if isinstance(widget, ttk.Checkbutton) and str(widget.cget("variable")) == str(panel._vars["skip_unfinishable_drops"]))
                control.invoke()
                self.assertTrue(settings.skip_unfinishable_drops)
                settings.save()
                self.assertTrue(Settings(Namespace()).skip_unfinishable_drops)
            finally:
                root.destroy()
