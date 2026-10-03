import asyncio
import os
import queue
import tempfile
import threading
import edge_tts
import pygame
from . import config as C

_inited = False
_mixer_lock = threading.Lock()
_chime_sound = None


def ensure_mixer():
    """Initialise pygame's mixer once, safely from any thread."""
    global _inited
    with _mixer_lock:
        if not _inited:
            pygame.mixer.init()
            _inited = True


def _make_chime():
    """A soft two-note 'ding-dong' (rising), built in code so there is no sound file to ship."""
    import numpy as np
    rate, _, channels = pygame.mixer.get_init()
    notes = []
    for freq, secs in ((880.0, 0.09), (1318.5, 0.16)):
        t = np.linspace(0, secs, int(rate * secs), endpoint=False)
        env = np.minimum(1.0, np.minimum(t / 0.008, (secs - t) / (secs * 0.7)))  # quick attack, smooth decay
        notes.append(np.sin(2 * np.pi * freq * t) * env)
    wave = (np.concatenate(notes) * C.CHIME_VOLUME * 32767).astype(np.int16)
    if channels == 2:
        wave = np.column_stack([wave, wave])
    return pygame.mixer.Sound(buffer=wave.tobytes())


def chime():
    """Play the wake-word chime without blocking. Never raises: a missing chime must not stop Clock."""
    global _chime_sound
    if not C.CHIME:
        return
    try:
        ensure_mixer()
        if _chime_sound is None:
            _chime_sound = _make_chime()
        _chime_sound.play()
    except Exception as e:
        print(f"(chime unavailable: {e})")


def speak(text: str):
    global _inited
    if not text:
        return
    print(f"Clock: {text}")
    path = os.path.join(tempfile.gettempdir(), "clock_tts.mp3")
    try:
        asyncio.run(edge_tts.Communicate(text, C.VOICE).save(path))
        if not _inited:
            pygame.mixer.init()
            _inited = True
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)
        pygame.mixer.music.unload()
    except Exception as e:  # offline etc: fall back to Windows SAPI
        print(f"(tts fallback: {e})")
        import subprocess
        safe = text.replace("'", "''")
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Add-Type -AssemblyName System.Speech; "
                        f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe}')"],
                       creationflags=0x08000000)  # CREATE_NO_WINDOW: no console flash


def _sapi(text: str):
    import subprocess
    safe = text.replace("'", "''")
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Add-Type -AssemblyName System.Speech; "
                    f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe}')"],
                       creationflags=0x08000000)  # CREATE_NO_WINDOW: no console flash


class Speaker:
    """Speaks queued sentences in order, synthesising the next one while the current one plays."""

    def __init__(self, mute=False):
        self.mute = mute
        self._text, self._audio = queue.Queue(), queue.Queue()
        threading.Thread(target=self._synth, daemon=True).start()
        threading.Thread(target=self._play, daemon=True).start()

    def say(self, text: str):
        if text and text.strip():
            self._text.put(text.strip())

    def wait(self):
        self._text.join()
        self._audio.join()

    def _synth(self):
        while True:
            text = self._text.get()
            path = None
            if not self.mute:
                try:
                    fd, path = tempfile.mkstemp(suffix=".mp3", prefix="clock_tts_")
                    os.close(fd)
                    asyncio.run(edge_tts.Communicate(text, C.VOICE).save(path))
                except Exception as e:
                    print(f"(tts fallback: {e})")
                    path = None
            self._audio.put((text, path))
            self._text.task_done()

    def _play(self):
        global _inited
        while True:
            text, path = self._audio.get()
            print(f"Clock: {text}")
            try:
                if not self.mute:
                    if path:
                        ensure_mixer()
                        pygame.mixer.music.load(path)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            pygame.time.wait(50)
                        pygame.mixer.music.unload()
                    else:
                        _sapi(text)
            except Exception as e:
                print(f"(playback error: {e})")
            finally:
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                self._audio.task_done()
