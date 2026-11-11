"""Play the capsule's short cues without blocking its Qt event loop."""
from collections import deque
from pathlib import Path
import sys
import winsound

from PyQt5.QtCore import QObject, QTimer


SOUND_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets/reminder-sounds'
SOUND_KINDS = ('agenda', 'focus_done', 'rest_done', 'water', 'battery', 'quota')
# Leave a short gap after the longest nature clip and its fade.
CUE_SPACING_MS = 760


class ReminderAudio(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.pending = deque()
        self.current = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._advance)

    def play(self, kind):
        if kind not in SOUND_KINDS or kind == self.current or kind in self.pending:
            return
        self.pending.append(kind)
        if not self.timer.isActive():
            self._advance()

    def _advance(self):
        self.current = self.pending.popleft() if self.pending else None
        if self.current is None:
            return
        path = SOUND_DIR / (self.current + '.wav')
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except RuntimeError:
            pass
        self.timer.start(CUE_SPACING_MS)

    def stop(self):
        self.timer.stop()
        self.pending.clear()
        if self.current is not None:
            self.current = None
            try:
                winsound.PlaySound(None, 0)
            except RuntimeError:
                pass
