# LinkCast (Milestone 1)

LinkCast replaces hardware screen-sharing dongles in classrooms with a network
service. The instructor runs a small agent on their own Windows machine. The
classroom display opens a web page served by that agent, types a short code,
and shows the instructor's screen as a motion JPEG (MJPEG) stream. Everything
stays on the campus LAN: no cloud, no accounts, no extra hardware.

**Status:** in development, Fall 2026

**Client:** Seward County Community College, IT department

**Context:** senior capstone project, INF490, Fort Hays State University

Milestone 1 only proves the transport works end to end. See
`docs/known-limitations.md` for what it does not do.

## Requirements

- Host: Windows 10/11, Python 3.13 or newer
- Python packages: `mss` (screen capture) and `Pillow` (JPEG encoding). The web
  server is the Python standard library. Nothing else.
- Display: any browser that can show an `<img>` tag. The viewer is plain HTML,
  CSS and ES5 JavaScript with no build step.

## Setup

From this folder (`linkcast`):

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

For development (tests, linting) also run `pip install -r requirements-dev.txt`.

## Run

```powershell
python -m host
```

No arguments and no configuration file. The agent prints the address to open on
the display and the session code, written to be read aloud:

```
  1. On the classroom display, open this address in the browser:
         http://192.168.0.2:8080
  2. When asked, enter this code:
         5 3 8 1 1 1
```

Press Ctrl+C to stop. The port is released.

Optional: `python -m host --code-ttl 60` sets how many seconds the code can be
used to connect (a positive whole number). Without it the default from
`host/config.py` is used (3600). Handy for testing expiry quickly.

**Firewall:** the host needs an allowed inbound port (8080 by default). In
classrooms IT sets this with a single rule; on first run Windows shows a dialog
that someone has to allow manually. LinkCast never changes firewall rules and
never asks for administrator rights.

If the machine has several network adapters (VPN, virtual switches) and the
printed address is not the classroom one, use the right address by hand. If no
LAN is found the banner says so and prints 127.0.0.1.

## Tuning

Everything adjustable is in one file: `host/config.py`.

| Setting | Default | Meaning |
|---|---|---|
| `PORT` | 8080 | TCP port |
| `FPS` | 12 | PRELIMINARY: frames per second (about 16 Mbit/s per viewer at 1080p, see `docs/test-results.md`) |
| `SCALE_TARGET_HEIGHT` | 1080 | Screen is scaled down to this height (0 = full size) |
| `JPEG_QUALITY` | 80 | 1 to 95. Lower if the stream stutters |
| `CODE_LENGTH` | 6 | Digits in the session code |
| `CODE_LIFETIME_SECONDS` | 3600 | How long the code works as an entry pass (override at launch with `--code-ttl SECONDS`) |
| `VIEWER_STALL_MIN_LOADS` | 10 | PRELIMINARY: load events needed before the viewer trusts frame-stall detection |
| `VIEWER_STALL_TIMEOUT_MS` | 6000 | PRELIMINARY: silence (ms) after which a stalled stream is reconnected |

The two `VIEWER_STALL_*` values are guesses to be confirmed in the classroom test
on the real TV browser (see `docs/known-limitations.md`).

Edit, save, restart the agent.

## Design decision: two credentials, two jobs

LinkCast deliberately uses two credentials.

- **The code is the entry pass.** It is short (6 digits) so it can be read aloud
  and typed on a TV remote, and it has a lifetime (default one hour). It is
  accepted in exactly one place: `GET /check?code=...`. If the code is valid and
  not expired, the host replies with a random **token**. A missing, wrong or
  expired code gets a 403 and no token.
- **The token is the continuation credential.** Each display gets its own. The
  viewer keeps it only in a JavaScript variable (no cookie, no localStorage, not
  in the address bar) and uses it for `/stream?token=...` and for reconnects
  (`/token-check?token=...` before each retry). The token never expires on its
  own and is not affected by the code expiring. It lives in the agent's memory
  and dies when the agent stops.

Why: a lecture must not be cut off mid-way because a timer ran out, and a
display with no keyboard must heal itself after a network blip even if that blip
happens after the code expired. The code expiry still does its job: a code that
someone saw an hour ago cannot be used to join later.

Consequences:

- A running stream is never cut when the code expires, and automatic
  reconnects keep working after expiry.
- There is no automatic code rotation in Milestone 1: one code per agent run.
  Restarting the agent gives a new code and invalidates all tokens; displays
  then show the code prompt with "The host was restarted. Enter the new code."
- Refreshing the viewer page forgets the token, so the code is needed again.
  After expiry that code is rejected as expired.
- `/stream` does not accept a code, only a token.

The request log never prints a full code or token (only the first 2 characters,
see `redact_code` in `host/session.py`).

## Manual acceptance test

Use the host machine plus a second device on the same network (a phone or
laptop is fine for a first run; the real classroom display later).

1. **Start.** Run `python -m host`. Expect a banner with a LAN URL (your real
   IP, not `localhost` or `0.0.0.0`) and a code with spaces between the digits.
2. **Code prompt.** On the second device open the printed URL. Expect a black
   page with a large code field and a Connect button.
3. **Wrong code.** Type a wrong code and press Connect (or Enter). Expect a
   readable error message and no video.
4. **Correct code.** Type the code from the banner. Expect the host's screen,
   moving, filling the window edge to edge with no scrollbars. Move a window on
   the host and check that it follows in about a second or less.
5. **Concurrency.** Open the URL in a second tab (or a third device), enter the
   code and confirm that both viewers stream at the same time. While both are
   streaming, open the URL in a third tab: the code page must still load at
   once. A viewer must never block the others.
6. **Network drop.** On the host, unplug the network cable (or turn off Wi-Fi)
   for about 20 seconds, then plug it back in. Expect "Reconnecting..." in the
   corner of the viewer and then the stream returning by itself, without
   touching the viewer. (The code must still be inside its lifetime.)
7. **Code expiry.** Start the agent with `python -m host --code-ttl 60` (the
   banner shows "60 seconds"/"1 minute"). Connect a viewer with the code, then
   wait more than 60 seconds. Check that:
   a. the streaming viewer keeps streaming;
   b. a network drop on that viewer (as in step 6) still recovers by itself,
      even though the code has expired (it reconnects with its token);
   c. refreshing the viewer page asks for the code again, and the old code is
      rejected with "expired".
8. **Clean stop.** Press Ctrl+C in the agent window. Expect it to stop within a
   second or two. Start it again at once: it must start without a "port in
   use" error.

## Tests and code checks

With the virtual environment active:

```powershell
python -m pytest
ruff check .
ruff format --check .
python -m bandit -r host -c pyproject.toml
```

The unit tests cover code generation, expiry, rejection of missing, wrong and
expired codes, the code-for-token exchange, log redaction and the launch flag.
Manual test results are in `docs/test-results.md`. Capture, the browser and the network are
checked by hand using the steps above.

## Layout

```
host/      capture, session code handling, HTTP server
viewer/    static viewer page (index.html, viewer.css, viewer.js)
docs/      known limitations and manual test results
tests/     unit tests
```

## Development note
An AI coding assistant was used during implementation. The architecture, technical decisions, and verifications are my own.