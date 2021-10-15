# MIT License
#
# Copyright (c) 2021 TrigonDev
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import sys
from typing import Callable

from prompt_toolkit import Application
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import VSplit, Window
from prompt_toolkit.widgets import TextArea

__all__ = ("App",)


class Stdout:
    def __init__(self, text_area: TextArea):
        self.old_stdout = sys.stdout
        self.text_area = text_area

    def write(self, text: str):
        text = self.text_area.text + text

        keep_pos = (
            len(self.text_area.text) == self.text_area.document.cursor_position
        )

        self.text_area.buffer.document = Document(
            text,
            len(text) if keep_pos else self.text_area.document.cursor_position,
        )

    def flush(self):
        self.old_stdout.flush()

    def __getattr__(self, name: str):
        return self.old_stdout.__getattribute__(name)


class App:
    def __init__(self, on_exit: Callable[[], None]):
        self.on_exit = on_exit

        self.output = TextArea(scrollbar=True)
        self.app_info = TextArea(width=50)
        self.container = Layout(
            VSplit(
                [
                    self.app_info,
                    Window(width=1, char="|"),
                    self.output,
                ]
            )
        )

        kb = KeyBindings()

        @kb.add("c-q")
        @kb.add("c-c")
        def exit_(event):
            self.on_exit()

        self.app: Application = Application(
            layout=self.container,
            key_bindings=kb,
            full_screen=True,
        )
        self.container.focus(self.output)

    async def run(self):
        sys.stdout = Stdout(self.output)  # type: ignore
        await self.app.run_async()

    def stop(self):
        self.app.exit()

    def set_app_info_text(self, text: str):
        self.app_info.document = Document(text)
