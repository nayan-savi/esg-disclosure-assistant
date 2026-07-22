import sys
import time
import threading
from itertools import cycle


class Spinner:
    def __init__(self, startMessage="Loading...", endMessage="Completed!..."):
        self.startMessage = startMessage
        self.endMessage = endMessage
        self._running = False
        self._thread = None

    def _spin(self):
        for char in cycle([
            "⬛⬜⬜⬜⬜",
            "⬛⬛⬜⬜⬜",
            "⬛⬛⬛⬜⬜",
            "⬛⬛⬛⬛⬜",
            "⬛⬛⬛⬛⬛",
            "⬜⬛⬛⬛⬛",
            "⬜⬜⬛⬛⬛",
            "⬜⬜⬜⬛⬛",
            "⬜⬜⬜⬜⬛",
        ]):
            if not self._running:
                break
            sys.stdout.write(f"\r{self.startMessage} {char}")
            sys.stdout.flush()
            time.sleep(0.1)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._spin)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        self._running = False
        self._thread.join()
        sys.stdout.write(f"\r{self.endMessage}\n")
        sys.stdout.flush()
