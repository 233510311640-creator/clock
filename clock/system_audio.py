"""Speaker volume and media-key control (Windows)."""
import ctypes

_MEDIA_KEYS = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}


def _endpoint():
    import comtypes
    from pycaw.pycaw import AudioUtilities
    comtypes.CoInitialize()
    return AudioUtilities.GetSpeakers().EndpointVolume


def volume(action: str, level=None) -> str:
    ep = _endpoint()
    cur = round(ep.GetMasterVolumeLevelScalar() * 100)
    if action == "get":
        return f"Volume is {cur}%{' (muted)' if ep.GetMute() else ''}."
    if action in ("mute", "unmute"):
        ep.SetMute(1 if action == "mute" else 0, None)
        return "Muted." if action == "mute" else "Unmuted."
    if action == "set":
        new = level
    elif action in ("up", "down"):
        step = 10 if level is None else abs(int(level))
        new = cur + step if action == "up" else cur - step
    else:
        return f"Unknown volume action {action}."
    new = max(0, min(100, int(new)))
    ep.SetMute(0, None)
    ep.SetMasterVolumeLevelScalar(new / 100, None)
    return f"Volume set to {new}%."


def media(action: str) -> str:
    vk = _MEDIA_KEYS.get(action)
    if not vk:
        return f"Unknown media action {action}."
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)       # key down
    user32.keybd_event(vk, 0, 2, 0)       # key up
    return {"play_pause": "Toggled play/pause.", "next": "Next track.",
            "previous": "Previous track.", "stop": "Stopped."}[action]
