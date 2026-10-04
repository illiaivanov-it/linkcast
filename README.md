# LinkCast
 
Browser-based screen distribution over a local campus network.
 
An instructor runs a lightweight host agent on their machine. Any browser-capable
display on the same network joins the session with an IP address and a short
code, and shows the instructor's screen. No new hardware, no cables, and no
traffic leaving the local network.
 
**Status:** in development, Fall 2026

**Client:** Seward County Community College

**Context:** senior capstone project, INF490, Fort Hays State University
 
## Problem
 
Classroom screen sharing currently runs on hardware dongles: one transmitter in
the instructor's laptop, one receiver at the display. The link is
point-to-point, so each room needs its own pair, a single machine can only
reach one display, and the campus network is not involved at all.
 
## Approach
 
Replace the dongle pair with a network service.
 
- **Host agent** captures the screen and serves a stream over HTTP
- **Viewer** is a plain web page, so any display with a browser works
- **Session code** with a limited lifetime controls who can connect

Transport starts as MJPEG over HTTP, which works in any browser including
older display firmware. WebRTC is a later step if lower latency is needed.
 
## Planned stack
 
| Part | Choice |
|---|---|
| Host capture | Python, `mss` |
| Server | FastAPI, uvicorn |
| Viewer | Plain HTML and JavaScript |
| Transport | MJPEG over HTTP, WebRTC later |
 
## Scope
 
**MVP**
- Screen capture to a stream
- Session code generation and validation
- Viewer page
- Verified on real classroom hardware

**Phase 2**
- Authentication and brute-force protection
- Subnet restrictions
- Session logging

**Later**
- Low-latency transport
- Packaged installer so Python is not required on the host
## Repository layout
 
```
host/      capture, session handling, server
viewer/    viewer pages
docs/      diagrams, test results, notes
```
 
## Notes
 
This repository is coursework. It targets one institution's network and is not
a general-purpose product.
