# Milestone 1 - manual test results

Manual acceptance run. It covers the checklist in `README.md` (section "Manual
acceptance test", steps 1 to 8) plus additional checks that are not in that
checklist. Unit tests, `ruff` and `bandit` are run separately and are not
repeated here.

## Run 1 - home network, 2026-10-18

### Setup

| | |
|---|---|
| Host | Windows 11 desktop, primary screen 2560x1440, Python 3.13 |
| Network | Home Wi-Fi, 192.168.0.0/24, host at 192.168.0.2 |
| Viewers | Windows laptop and a phone, both on the same Wi-Fi |
| Settings during the run | `FPS = 20`, `SCALE_TARGET_HEIGHT = 1080`, `JPEG_QUALITY = 80` |

The default `FPS` was lowered to 12 after this run, based on the bandwidth
numbers below.

### Results: README checklist

| README step | Check | Result |
|---|---|---|
| 1 | Agent starts with one command, prints LAN URL and code | Pass |
| 2 | Second device on the same network reaches the code prompt | Pass, after the firewall fix below |
| 3 | Wrong code shows a readable error and no video | Pass |
| 4 | Correct code shows the moving screen, filling the window | Pass |
| 5 | Concurrency: two viewers at once (laptop + phone) | Pass |
| 6 | Network drop on the host (Wi-Fi off ~15 s, then on) recovers without touching the viewer; "Reconnecting..." shown meanwhile | Pass |
| 7a | `--code-ttl 60`: a running stream continues after the code expires | Pass |
| 7b | Network drop **after** code expiry recovers on its own (session token) | Pass |
| 7c | Refresh after expiry: old code rejected as expired, no video | Pass |
| 8 | Ctrl+C stops cleanly, port 8080 free for an immediate restart | Pass |

The acceptance criterion says "pull the network cable". The host was on Wi-Fi,
so the drop was done by turning Wi-Fi off and on, which breaks the connection
the same way.

### Results: additional checks

| Check | Result |
|---|---|
| Agent restart while a viewer is streaming: viewer returns to the prompt with "The host was restarted. Enter the new code." | Pass |
| Lock screen (Win+L) during streaming: stream keeps running and shows the lock screen | Pass |
| UAC secure desktop during streaming | Not tested yet |
| Classroom TV browser | Not tested yet (no access) |

### Finding: Windows firewall and the network profile

At first the viewer worked on the host itself but not from other devices. The
host's Wi-Fi was marked as a **Public** network, where Windows blocks inbound
connections by default, and there was no allow rule for the agent. Fixed by:

1. Setting the Wi-Fi profile to **Private**.
2. Adding one inbound rule, Private profile only:
   `New-NetFirewallRule -DisplayName "LinkCast 8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Private`

Both need administrator rights, which is why LinkCast does not do this itself.
For deployment this confirms the README note: IT must allow the inbound port on
the network profile the classroom machine actually uses. On campus that is
usually the Domain profile, not Private. Also note that `ping` from another
device is not a valid reachability test: Windows does not answer inbound ICMP by
default even when TCP 8080 is allowed.

### Finding: resolution, quality and bandwidth

At 720p the picture was blurry on this host, because a 2560x1440 screen was
scaled down by half on each side. Measured JPEG frame size on this host's
desktop, with the agent's own encoder:

| Height | Quality | KB / frame | Mbit/s per viewer at 12 fps | at 15 fps | at 20 fps |
|---|---|---|---|---|---|
| 720 | 70 | 67 | 6.6 | 8.3 | 11.0 |
| 720 | 95 | 148 | 14.5 | 18.1 | 24.2 |
| 1080 | 70 | 139 | 13.7 | 17.1 | 22.8 |
| **1080** | **80** | **166** | **16.3** | **20.3** | **27.1** |
| 1080 | 95 | 299 | 29.4 | 36.8 | 49.0 |

Encoding took about 2 to 4 ms per frame in every case, so CPU is not the limit.
Bandwidth is. 1080p at quality 80 was chosen: visibly sharp, and cheaper than
the previous 720p at quality 95.

The frame rate was the remaining lever. At 20 fps, 1080p/80 is about 27 Mbit/s
per viewer. The classrooms show mostly static slides and the displays are on
Wi-Fi, so 20 fps buys almost nothing visible while costing the most bandwidth.
The default is now **12 fps, about 16 Mbit/s per viewer**, roughly 40% less.
This value is preliminary and will be confirmed in the classroom test.

The numbers are for a mostly static desktop; slides with photos or video
produce larger frames. Bandwidth per viewer multiplied by the number of
displays is the figure to check against classroom Wi-Fi.

### Still open

- Classroom TV: ES5 viewer on the real embedded browser, and the preliminary
  stall thresholds (`VIEWER_STALL_MIN_LOADS = 10`, `VIEWER_STALL_TIMEOUT_MS = 6000`)
- Measure bandwidth with real teaching material on screen, not an idle desktop.
  Image-heavy slides produce larger frames than the numbers above.
- Frame rate and bandwidth on the campus network with the chosen settings
- UAC secure desktop behaviour
- Firewall profile on a campus machine (Domain vs Private)