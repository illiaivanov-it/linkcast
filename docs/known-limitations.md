# Known limitations (Milestone 1)

## Host IP address change

The viewer is opened at the host's LAN address. If the host's IP changes (for
example DHCP hands out a new address after the laptop reconnects), a viewer that
is already open cannot recover, because it keeps asking the old address.

This is a deployment requirement, not a bug: the classroom machine needs a
**DHCP reservation** so it always gets the same address. IT sets this up once.
It goes into the deployment plan of the Written Proposal.

## Code expiry and tokens

The session code is an entry pass: it is accepted only at `/check`, only until it
expires, and it returns a per-display token. The token (not the code) opens the
stream and is used for every automatic reconnect, so code expiry never cuts a
running lecture and never stops a display from healing itself. Tokens live in
memory and last until the agent stops; there is no code rotation in M1. If the
agent is restarted, all tokens die and displays show the code prompt again.
See the README for the reasoning.

## Code is in the URL, and logging rule for Milestone 2

The code (at `/check`) and the token (at `/stream`) are sent as query-string
parameters because cookies are a risk on old TV firmware. URLs can end up in
logs, so:

- Milestone 1 never prints a full code or token from a request. The request
  log is scrubbed in `host/server.py` and `redact_code()` in `host/session.py`
  reduces a value to at most its first 2 characters. The full code appears only
  in the startup banner, on purpose, so it can be read aloud.
- **Milestone 2 session logging must record only the redacted code or token
  (first 2 characters at most), or just success/failure. Never log a full code
  or a full token.** Tokens appear in `/stream?token=...` URLs, so the same
  scrubber covers them.

## No attempt limiting: the code can be brute-forced within its lifetime

The code has 6 digits (1,000,000 combinations) and Milestone 1 has no attempt
limiting. `/check` is a cheap handler. Measured against the real server on the
development machine (loopback, wrong codes, new connection per request): about
570 requests/s from one client thread and about 1,900 requests/s from 4 to 8
threads. At that rate the whole code space takes about 9 minutes and a random
code is found in about 4 to 5 minutes on average. A Wi-Fi client would be
slower, but not by enough to matter.

Without attempt limiting, a code is found well within its one-hour lifetime on
a LAN: at the measured rate in about 4 to 5 minutes on average, and even at a
tenth of that rate still inside the hour. Attempt limiting in Milestone 2 is
what makes the code length meaningful.

## No HTTPS

All traffic is plain HTTP, including the code at `/check` and the token in
`/stream?token=...`. Anyone on the same subnet who can capture traffic (for
example on shared Wi-Fi) can read a token and open the same stream.

This is accepted for Milestone 1 because:

- the traffic never leaves the campus LAN;
- the stream shows what is already on the classroom screen, so there is little
  of value to steal;
- TLS would need a trusted certificate on every classroom display, and the TV
  browsers do not allow installing one. A self-signed certificate would show a
  warning that nobody can click through with a remote.

If the risk assessment changes, the options are a campus-issued certificate for
the host (if the displays trust the campus CA) or a wired, isolated VLAN for
classroom displays.

## Video only, no audio

MJPEG cannot carry sound. Audio is outside the project scope.

## MJPEG latency and bandwidth

Every frame is a separate JPEG, so the stream uses more bandwidth and has more
delay than WebRTC (expect a few hundred milliseconds, more on slow Wi-Fi). This
is an accepted trade for working on very old browsers. Tune `FPS`,
`SCALE_TARGET_HEIGHT` and `JPEG_QUALITY` in `host/config.py` by testing on the
real network.

## Capture limits

Only the primary monitor is captured.

- **Lock screen (Win+L): tested, capture continues.** The viewer shows the lock
  screen while the host is locked (see `docs/test-results.md`).
- **UAC secure desktop: capture is expected to fail. Not yet tested.** The UAC
  prompt runs on a separate secure desktop that normal programs cannot capture.
  The agent is written to log the failure once, keep retrying, and leave the
  viewer on the last frame until capture works again.

## Viewer stall detection thresholds are preliminary

`VIEWER_STALL_MIN_LOADS = 10` and `VIEWER_STALL_TIMEOUT_MS = 6000` in
`host/config.py` are guesses, served to the page as `/viewer-config.js`. How
often an `<img>` showing MJPEG fires `onload` differs per browser engine (some
fire per frame, some only once). The viewer only trusts frame-timeout detection
once a connection has produced `VIEWER_STALL_MIN_LOADS` load events. Too low a
value can cause a reconnect loop on a browser that fires a few events and then
stops; too high disables stall detection (the host-reachability check still
works). They are isolated in one place before the classroom test and will be
confirmed and tuned after it.

## Milestone 2 items

Deferred from Milestone 1 on purpose, as listed in the task:

- **Attempt limiting on `/check`.** Needed to make the 6-digit code meaningful
  (see "No attempt limiting" above).
- **Session logging to file.** Must follow the redaction rule above: only the
  redacted code or token, or success/failure.
- **Pause capture with zero viewers.** The capture thread works continuously
  and wastes CPU on the instructor's laptop when nobody is watching. M2 should
  pause capture while no stream is connected.
- Also out of scope for M1: subnet allowlisting, packaging into a standalone
  executable, multiple sessions or hosts, WebRTC.
