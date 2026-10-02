import base64
import io


def capture(source: str = "screen") -> str:
    """Capture the screen or webcam and return a base64 JPEG string."""
    from PIL import Image
    if source == "webcam":
        import cv2
        cam = cv2.VideoCapture(0)
        ok = False
        for _ in range(5):  # let exposure settle
            ok, frame = cam.read()
        cam.release()
        if not ok:
            raise RuntimeError("Could not read from webcam")
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    else:
        import mss
        with mss.mss() as s:
            shot = s.grab(s.monitors[1])
            img = Image.frombytes("RGB", shot.size, shot.rgb)
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()
