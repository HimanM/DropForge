from __future__ import annotations

import asyncio

from textual.drivers.windows_driver import WindowsDriver, WriterThread, win32


class NoAltScreenWindowsDriver(WindowsDriver):
    def start_application_mode(self) -> None:
        loop = asyncio.get_running_loop()

        self._restore_console = win32.enable_application_mode()

        self._writer_thread = WriterThread(self._file)
        self._writer_thread.start()

        self._enable_mouse_support()
        self.write("\x1b[2J\x1b[H")  # Clear the normal console buffer and move home.
        self.write("\x1b[?25l")  # Hide cursor
        self.write("\033[?1004h")  # Enable FocusIn/FocusOut.
        self.write("\x1b[>1u")  # https://sw.kovidgoyal.net/kitty/keyboard-protocol/
        self.flush()
        self._enable_bracketed_paste()

        self._event_thread = win32.EventMonitor(
            loop, self._app, self.exit_event, self.process_message
        )
        self._event_thread.start()

    def stop_application_mode(self) -> None:
        self._disable_bracketed_paste()
        self.disable_input()

        self.write("\x1b[<u")
        self.write("\x1b[?25h")
        self.write("\033[?1004l")
        self.flush()
