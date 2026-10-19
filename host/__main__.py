"""Start the LinkCast host agent: ``python -m host``."""

import argparse
import logging
import sys
import threading

from host import config
from host.capture import CaptureThread, FrameHub
from host.netinfo import find_lan_ip
from host.server import LinkCastServer
from host.session import Session, spaced


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError("must be a whole number of seconds, 1 or more")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m host", description="LinkCast host agent."
    )
    parser.add_argument(
        "--code-ttl",
        type=positive_int,
        default=config.CODE_LIFETIME_SECONDS,
        metavar="SECONDS",
        help="how long the code can be used to connect "
        f"(default {config.CODE_LIFETIME_SECONDS}); handy for testing expiry",
    )
    return parser.parse_args(argv)


def format_lifetime(seconds: float) -> str:
    """ "60 minutes", "1 minute", or "45 seconds" when not whole minutes."""
    seconds = int(seconds)
    if seconds >= 60 and seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minute{'' if minutes == 1 else 's'}"
    return f"{seconds} second{'' if seconds == 1 else 's'}"


def print_banner(ip: str, ip_found: bool, session: Session) -> None:
    # The banner is the ONE place the full code is printed, on purpose: the
    # instructor reads it aloud. Request logging never shows it.
    print()
    print("  LinkCast is running.")
    print()
    print("  1. On the classroom display, open this address in the browser:")
    print()
    print(f"         http://{ip}:{config.PORT}")
    print()
    print("  2. When asked, enter this code:")
    print()
    print(f"         {spaced(session.code)}")
    print()
    lifetime = format_lifetime(session.lifetime)
    print(f"  The code can be used to connect for the next {lifetime}.")
    print("  Displays already connected are never cut off.")
    print("  Restart this program to get a new code.  Press Ctrl+C to stop.")
    if not ip_found:
        print()
        print("  WARNING: no LAN address was found (not connected to a network?).")
        print("  The address above only works on this computer.")
    print(flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    session = Session(lifetime=args.code_ttl)
    hub = FrameHub()
    capture = CaptureThread(hub)
    try:
        server = LinkCastServer((config.BIND_ADDRESS, config.PORT), session, hub)
    except OSError as exc:
        print(f"Could not listen on port {config.PORT}: {exc}", file=sys.stderr)
        print(
            "Is another copy running? The port is set in host/config.py.",
            file=sys.stderr,
        )
        return 1

    capture.start()
    ip, ip_found = find_lan_ip()
    print_banner(ip, ip_found, session)

    # serve_forever runs in a worker thread; the main thread only waits, in
    # short slices, so Ctrl+C (KeyboardInterrupt) is delivered promptly on
    # Windows, where a blocking call in the main thread would swallow it.
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.25}, name="http"
    )
    worker.start()
    try:
        while worker.is_alive():
            worker.join(0.5)
    except KeyboardInterrupt:
        print("\nStopping LinkCast...")
    finally:
        hub.close()  # wake every waiting stream handler so it can exit
        capture.stop()
        server.shutdown()
        server.server_close()
        worker.join(5)
        capture.join(5)
    print("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
