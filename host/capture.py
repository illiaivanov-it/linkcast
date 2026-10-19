"""Screen capture: ONE background thread publishes the latest JPEG frame.

Stream handlers never capture. They wait on the ``FrameHub`` for the next frame
and write it to their client, so the cost of capturing does not grow with the
number of viewers.
"""

import contextlib
import io
import logging
import threading
import time

import mss
from PIL import Image

from host import config

log = logging.getLogger("linkcast.capture")


class FrameHub:
    """Holds the latest JPEG and wakes everyone waiting for a newer one."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._frame: bytes | None = None
        self._seq = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def publish(self, jpeg: bytes) -> None:
        with self._cond:
            self._frame = jpeg
            self._seq += 1
            self._cond.notify_all()

    def wait_next(self, last_seq: int, timeout: float) -> tuple[int, bytes] | None:
        """Block until a frame newer than ``last_seq`` exists.

        Returns ``(seq, jpeg)``, or None on timeout or when the hub is closed.
        A slow viewer simply skips frames it missed and gets the newest one.
        """
        with self._cond:
            self._cond.wait_for(
                lambda: self._closed or self._seq > last_seq, timeout=timeout
            )
            if self._closed or self._frame is None or self._seq <= last_seq:
                return None
            return self._seq, self._frame

    def close(self) -> None:
        """Wake all waiting stream handlers so they can exit."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()


def encode_frame(shot, target_height: int, quality: int) -> bytes:
    """Convert an mss screenshot to JPEG bytes, downscaled to ``target_height``."""
    image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    width, height = image.size
    if target_height and height > target_height:
        new_width = max(1, round(width * target_height / height))
        image = image.resize((new_width, target_height), Image.Resampling.BILINEAR)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


class CaptureThread(threading.Thread):
    def __init__(self, hub: FrameHub) -> None:
        super().__init__(name="capture", daemon=True)
        self._hub = hub
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        interval = 1.0 / config.FPS
        failing = False
        sct = None
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                if sct is None:
                    # mss instances are thread-local: create it HERE, in the
                    # thread that uses it.
                    sct = mss.mss()
                shot = sct.grab(sct.monitors[1])  # primary monitor
                jpeg = encode_frame(
                    shot, config.SCALE_TARGET_HEIGHT, config.JPEG_QUALITY
                )
            except Exception as exc:  # keep trying, whatever the cause
                # Typical causes: UAC prompt / lock screen (secure desktop),
                # display change, RDP disconnect. Log once, retry quietly.
                if not failing:
                    log.warning("Screen capture failed (%s); retrying...", exc)
                    failing = True
                if sct is not None:
                    with contextlib.suppress(Exception):
                        sct.close()
                    sct = None
                self._stop_event.wait(1.0)
                continue
            if failing:
                log.info("Screen capture recovered.")
                failing = False
            self._hub.publish(jpeg)
            self._stop_event.wait(max(0.0, interval - (time.monotonic() - started)))
        if sct is not None:
            sct.close()
