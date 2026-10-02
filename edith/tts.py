import asyncio
import os
import tempfile
import edge_tts
import pygame
from . import config as C

_inited = False


def speak(text: str):
    global _inited
    if not text:
        return
    print(f"Clock: {text}")
    path = os.path.join(tempfile.gettempdir(), "edith_tts.mp3")
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
                        f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe}')"])
