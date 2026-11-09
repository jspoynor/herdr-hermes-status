"""Report Hermes status to the Herdr desktop app (herdr-core) via OSC 7501.

herdr-app treats a terminal as an agent only if the program reports status
with OSC 7501. Silent outside herdr terminals (no HC_TERMINAL_ID) and in
non-interactive runs (gateway/cron).

State model:
  * a turn is "open" from pre_llm_call until post_llm_call / on_session_end
    (tracked per session_id, so subagents and background reviews can't
    leave the pane stuck on "working" or flip it to idle early);
  * tool hooks only matter while a turn is open;
  * "blocked" is reported only for real human prompts, and only if the prompt
    is still pending after _BLOCK_DELAY seconds (auto-approvals are instant).
"""

from __future__ import annotations

import base64
import os
import threading

_APP = "hermes"
_INTERACTIVE = {"cli", "tui", "desktop", "acp"}
_BLOCK_DELAY = 1.0          # seconds a prompt must stay pending before "blocked"
_IGNORED_SURFACES = {"smart"}  # guardian-LLM checks: no human involved

_lock = threading.RLock()
_active = False             # saw an interactive-platform hook
_turns: set = set()         # session_ids with an open turn
_pending = 0                # unresolved human approval prompts
_timer: threading.Timer | None = None
_timer_generation = 0       # invalidate callbacks that race with cancellation
_last = None


def _write(state: str, kind: str | None = None, msg: str | None = None) -> None:
    global _last
    if not os.environ.get("HC_TERMINAL_ID"):
        return
    key = (state, kind, msg)
    fields = [f"state={state}", f"app={_APP}"]
    if state == "blocked" and kind:
        fields.append(f"kind={kind}")
    if msg:
        fields.append("msg=" + base64.b64encode(msg[:120].encode()).decode())
    seq = "\x1b]7501;" + ":".join(fields) + "\x1b\\"
    try:
        fd = os.open("/dev/tty", os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            os.write(fd, seq.encode())
        finally:
            os.close(fd)
        _last = key
    except OSError:
        pass


def _settle() -> None:
    """Emit the state implied by current bookkeeping (call with _lock held)."""
    if not _active or _pending > 0:
        return
    _write("working" if _turns else "idle")


def _cancel_timer() -> None:
    global _timer, _timer_generation
    _timer_generation += 1
    if _timer is not None:
        _timer.cancel()
        _timer = None


def _fire_blocked(msg: str, generation: int) -> None:
    with _lock:
        if generation == _timer_generation and _pending > 0 and _active:
            _write("blocked", "permission", msg)


def _sid(kw) -> str:
    return str(kw.get("session_id") or "")


def _mark(kw) -> None:
    global _active
    if kw.get("platform") in _INTERACTIVE:
        _active = True


def _on_session_start(**kw):
    with _lock:
        _mark(kw)
        _settle()


def _turn_open(**kw):
    with _lock:
        _mark(kw)
        _turns.add(_sid(kw))
        if _pending == 0:
            _settle()


def _turn_close(**kw):
    with _lock:
        _mark(kw)
        _turns.discard(_sid(kw))
        if _pending == 0:
            _settle()


def _tool(**kw):
    # Only refresh state; never open a turn from a stray/background tool call.
    with _lock:
        if _turns and _pending == 0:
            _settle()


def _approval_request(**kw):
    global _pending, _timer
    if kw.get("surface") in _IGNORED_SURFACES:
        return
    with _lock:
        if not _active:
            return
        _pending += 1
        _cancel_timer()
        # Not all hook surfaces provide a unique request ID; responses may
        # arrive out of order, so no captured description is reliably pending.
        msg = "Approval needed"
        _timer = threading.Timer(
            _BLOCK_DELAY, _fire_blocked, args=(msg, _timer_generation))
        _timer.daemon = True
        _timer.start()


def _approval_response(**kw):
    global _pending
    if kw.get("surface") in _IGNORED_SURFACES:
        return
    with _lock:
        _pending = max(0, _pending - 1)
        if _pending == 0:
            _cancel_timer()
            _settle()


def _finalize(**kw):
    global _pending, _last
    with _lock:
        _turns.clear()
        _pending = 0
        _cancel_timer()
        _last = None
        _settle()


def register(ctx):
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("pre_llm_call", _turn_open)
    ctx.register_hook("pre_tool_call", _tool)
    ctx.register_hook("post_llm_call", _turn_close)
    ctx.register_hook("on_session_end", _turn_close)
    ctx.register_hook("pre_approval_request", _approval_request)
    ctx.register_hook("post_approval_response", _approval_response)
    ctx.register_hook("on_session_finalize", _finalize)
