/* LinkCast viewer. Strict ES5 for old TV browsers: var, function, XMLHttpRequest. */
(function () {
  'use strict';

  var BACKOFF_START_MS = 1000;
  var BACKOFF_MAX_MS = 30000;
  var WATCHDOG_MS = 2000;      // how often we poll the host while playing
  var XHR_TIMEOUT_MS = 4000;
  var OVERLAY_FALLBACK_MS = 3000;

  // Tunables come from the host (/viewer-config.js, set in host/config.py).
  // PRELIMINARY values pending classroom testing; fallbacks if missing.
  var cfg = (typeof LINKCAST_CONFIG !== 'undefined' && LINKCAST_CONFIG) || {};
  var STALL_MIN_LOADS = cfg.stallMinLoads || 10;
  var STALL_MS = cfg.stallTimeoutMs || 6000;

  var promptEl = document.getElementById('prompt');
  var formEl = document.getElementById('form');
  var inputEl = document.getElementById('code');
  var errorEl = document.getElementById('error');
  var videoEl = document.getElementById('video');
  var statusEl = document.getElementById('status');

  // The code is exchanged once at /check for a token; the code is then
  // forgotten. The token lives ONLY in this variable, never in localStorage,
  // cookies or the address bar, so a refresh always asks for the code again.
  var token = null;

  var playing = false;
  var backoff = BACKOFF_START_MS;
  var reconnectTimer = null;
  var overlayTimer = null;
  var watchdogTimer = null;
  var checkInFlight = false;
  var submitting = false;
  var outage = false;

  // Frame tracking for the stall watchdog (see watchdog()).
  var loadCount = 0;
  var lastLoadAt = 0;

  var hasObjectFit = ('objectFit' in document.documentElement.style);

  function now() {
    return new Date().getTime();
  }

  /* ---- small helpers ---------------------------------------------------- */

  function show(el) { el.style.display = 'block'; }
  function hide(el) { el.style.display = 'none'; }

  // Asks the host something. Calls done(kind, text) where kind is
  // 'ok' (HTTP 200), 'rejected' (HTTP 403) or 'network' (anything else).
  function request(url, done) {
    var xhr = new XMLHttpRequest();
    var finished = false;
    function finish(kind, text) {
      if (finished) { return; }
      finished = true;
      done(kind, text);
    }
    xhr.open('GET', url, true);
    xhr.timeout = XHR_TIMEOUT_MS;
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) { return; }
      if (xhr.status === 200) {
        finish('ok', xhr.responseText);
      } else if (xhr.status === 403) {
        finish('rejected', xhr.responseText);
      } else {
        finish('network', '');
      }
    };
    xhr.ontimeout = function () { finish('network', ''); };
    xhr.onerror = function () { finish('network', ''); };
    try {
      xhr.send(null);
    } catch (e) {
      finish('network', '');
    }
  }

  // Reconnect pre-check: is our token still known to the host?
  function checkToken(done) {
    request('/token-check?token=' + encodeURIComponent(token) + '&t=' + now(), done);
  }

  /* ---- layout fallback for browsers without object-fit ------------------ */

  function fitVideo() {
    if (hasObjectFit || !videoEl.naturalWidth || !videoEl.naturalHeight) { return; }
    var winW = window.innerWidth || document.documentElement.clientWidth;
    var winH = window.innerHeight || document.documentElement.clientHeight;
    var scale = Math.min(winW / videoEl.naturalWidth, winH / videoEl.naturalHeight);
    var w = Math.round(videoEl.naturalWidth * scale);
    var h = Math.round(videoEl.naturalHeight * scale);
    videoEl.style.width = w + 'px';
    videoEl.style.height = h + 'px';
    videoEl.style.left = Math.round((winW - w) / 2) + 'px';
    videoEl.style.top = Math.round((winH - h) / 2) + 'px';
  }

  /* ---- prompt ----------------------------------------------------------- */

  function showPrompt(message) {
    playing = false;
    token = null;
    outage = false;
    stopTimers();
    videoEl.onload = null;
    videoEl.onerror = null;
    videoEl.removeAttribute('src');
    hide(videoEl);
    hide(statusEl);
    errorEl.innerHTML = '';
    errorEl.appendChild(document.createTextNode(message || ''));
    inputEl.value = '';
    show(promptEl);
    try { inputEl.focus(); } catch (e) { /* focus is a convenience only */ }
  }

  function submitCode() {
    if (submitting) { return; }
    var entered = inputEl.value.replace(/[\s\-]/g, '');
    if (entered === '') {
      errorEl.innerHTML = '';
      errorEl.appendChild(document.createTextNode('Please enter the code.'));
      return;
    }
    submitting = true;
    errorEl.innerHTML = '';
    request('/check?code=' + encodeURIComponent(entered) + '&t=' + now(), function (kind, text) {
      submitting = false;
      if (kind === 'ok') {
        token = text.replace(/\s/g, '');
        inputEl.value = '';
        startPlaying();
      } else if (kind === 'rejected') {
        inputEl.value = '';
        errorEl.appendChild(document.createTextNode(text || 'That code was not accepted.'));
        try { inputEl.focus(); } catch (e) { /* ignore */ }
      } else {
        errorEl.appendChild(document.createTextNode(
          'Cannot reach the host. Check the address and the network, then try again.'));
      }
    });
  }

  /* ---- playing ---------------------------------------------------------- */

  function startPlaying() {
    playing = true;
    backoff = BACKOFF_START_MS;
    hide(promptEl);
    show(videoEl);
    connectStream();
    watchdogTimer = window.setInterval(watchdog, WATCHDOG_MS);
  }

  function connectStream() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    outage = false;
    loadCount = 0;
    lastLoadAt = now();
    videoEl.onload = onFrame;
    videoEl.onerror = onStreamError;
    // New URL every time (the t parameter) so the browser never reuses a dead connection.
    videoEl.src = '/stream?token=' + encodeURIComponent(token) + '&t=' + now();
    // If this browser never fires onload for streams, do not leave the
    // overlay up forever; hide it unless an error arrives first.
    if (overlayTimer !== null) { window.clearTimeout(overlayTimer); }
    overlayTimer = window.setTimeout(function () {
      overlayTimer = null;
      hide(statusEl);
    }, OVERLAY_FALLBACK_MS);
  }

  function onFrame() {
    loadCount += 1;
    lastLoadAt = now();
    backoff = BACKOFF_START_MS;   // the stream demonstrably works
    if (loadCount === 1) {
      fitVideo();
      hide(statusEl);
    }
  }

  function onStreamError() {
    if (!playing) { return; }
    connectionLost();
  }

  function connectionLost() {
    if (overlayTimer !== null) {
      window.clearTimeout(overlayTimer);
      overlayTimer = null;
    }
    show(statusEl);
    scheduleReconnect();
  }

  // Retry with exponential backoff: 1s, 2s, 4s and so on, capped. No keypress needed.
  function scheduleReconnect() {
    if (!playing || reconnectTimer !== null) { return; }
    var delay = backoff;
    backoff = Math.min(backoff * 2, BACKOFF_MAX_MS);
    reconnectTimer = window.setTimeout(attemptReconnect, delay);
  }

  function attemptReconnect() {
    reconnectTimer = null;
    if (!playing) { return; }
    // The token never expires while the host runs, so code expiry cannot
    // block a reconnect. 403 here means the host was restarted.
    checkToken(function (kind, text) {
      if (!playing) { return; }
      if (kind === 'ok') {
        connectStream();
      } else if (kind === 'rejected') {
        showPrompt('The host was restarted. Enter the new code.');
      } else {
        scheduleReconnect();
      }
    });
  }

  /* ---- stall watchdog ----------------------------------------------------
   * An <img> showing an MJPEG stream often fires NO event when the network
   * silently dies (cable pulled): no error, the picture just freezes. Two
   * independent signals cover this:
   *
   * 1. Frame timeout. Some browsers fire onload for every frame; if we have
   *    seen STALL_MIN_LOADS or more loads for this connection, frames are observable, and
   *    STALL_MS of silence means the stream is dead.
   * 2. Host reachability. Every WATCHDOG_MS we ask /ping (which does not check
   *    the code, so a running stream is never affected by code expiry). When
   *    the host stops answering we mark an outage; when it answers again we
   *    reconnect straight away rather than waiting for a dead TCP connection
   *    to time out. This works in every browser, whatever events it fires.
   */
  function watchdog() {
    if (!playing || reconnectTimer !== null || checkInFlight) { return; }

    if (loadCount >= STALL_MIN_LOADS && now() - lastLoadAt > STALL_MS) {
      connectionLost();
      return;
    }

    checkInFlight = true;
    request('/ping?t=' + now(), function (kind) {
      checkInFlight = false;
      if (!playing) { return; }
      if (kind === 'network') {
        outage = true;
        show(statusEl);
      } else if (outage) {
        // Host is back after an outage: do not trust the old connection.
        outage = false;
        backoff = BACKOFF_START_MS;
        connectionLost();
      }
    });
  }

  function stopTimers() {
    if (reconnectTimer !== null) { window.clearTimeout(reconnectTimer); reconnectTimer = null; }
    if (overlayTimer !== null) { window.clearTimeout(overlayTimer); overlayTimer = null; }
    if (watchdogTimer !== null) { window.clearInterval(watchdogTimer); watchdogTimer = null; }
  }

  /* ---- wiring ----------------------------------------------------------- */

  formEl.addEventListener('submit', function (e) {
    if (e.preventDefault) { e.preventDefault(); }
    submitCode();
    return false;
  }, false);

  // Some TV browsers do not submit on the remote's OK/Enter key.
  inputEl.addEventListener('keydown', function (e) {
    var key = e.keyCode || e.which;
    if (key === 13) {
      if (e.preventDefault) { e.preventDefault(); }
      submitCode();
    }
  }, false);

  window.addEventListener('resize', fitVideo, false);

  try { inputEl.focus(); } catch (e) { /* ignore */ }
}());
