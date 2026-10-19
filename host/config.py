"""All tunables in one place.

Edit the constants below, save, and restart the agent (``python -m host``).
The right values for FPS / scale / quality have to be found by testing on the
real classroom network, so these are the numbers you are expected to change.
"""

# --- Network ---------------------------------------------------------------

# TCP port the viewer page and stream are served on. On first run Windows shows
# a firewall dialog for this program; someone has to allow it (see README).
PORT = 8080

# Listen on every interface so a display on the LAN can connect. The address
# shown to the instructor is the real LAN IP, found at startup (host/netinfo.py).
# Intentional for a LAN-only service, hence the targeted suppressions.
BIND_ADDRESS = "0.0.0.0"  # noqa: S104  # nosec B104

# --- Video -----------------------------------------------------------------

# Target frames per second (spec: roughly 10 to 15). Classroom content is mostly
# static slides, so a higher rate costs bandwidth without a visible gain. At
# 1080p / quality 80 this is about 16 Mbit/s per viewer (docs/test-results.md).
# PRELIMINARY: to be confirmed in the classroom test.
FPS = 12

# Frames taller than this are scaled down to this height, keeping the aspect
# ratio. Smaller frames are never enlarged. Use 0 to send the full-size screen.
SCALE_TARGET_HEIGHT = 1080

# JPEG quality, 1 (small, blocky) to 95 (large, sharp). Lower it first if the
# stream stutters on a slow network.
JPEG_QUALITY = 80

# --- Viewer stall detection ------------------------------------------------
# PRELIMINARY values, to be confirmed in the classroom test on the real TV.
# Some browsers fire onload for every MJPEG frame in an <img>, some only once.
# If a connection has produced at least VIEWER_STALL_MIN_LOADS load events,
# the viewer treats frames as observable and reconnects after
# VIEWER_STALL_TIMEOUT_MS of silence. Too low a MIN_LOADS risks a reconnect
# loop on browsers that fire only a few events; too high disables detection.
# Served to the page as /viewer-config.js.
VIEWER_STALL_MIN_LOADS = 10
VIEWER_STALL_TIMEOUT_MS = 6000

# --- Session code ----------------------------------------------------------

# Digits only on purpose: a TV remote has a number pad but typing letters means
# multi-tap or an on-screen keyboard. Digits are also unambiguous when read
# aloud (no O/0, I/l/1 confusion), and the phone-style keypad is what the
# viewer's input field brings up. 6 digits = 1,000,000 combinations; attempt
# limiting is planned for Milestone 2.
CODE_ALPHABET = "0123456789"
CODE_LENGTH = 6

# How long the code works as an ENTRY PASS for new connections, in seconds.
# It is checked only when a viewer connects (page unlock, opening /stream).
# A stream that is already running is never cut when the code expires.
CODE_LIFETIME_SECONDS = 3600
