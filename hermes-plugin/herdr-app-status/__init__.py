"""Report Hermes status to the Herdr desktop app (herdr-core) via OSC 7501.

herdr-app treats a terminal as an agent only if the program reports status
with OSC 7501. Silent outside herdr terminals (no HC_TERMINAL_ID) or when
there is no controlling tty (gateway/cron).
"""

from __future__ import annotations

import base64
import os

_APP = "hermes"
_INTERACTIVE = {"cli", "tui", "desktop", "acp"}
_last = None
_active = False


def _emit(state: str, kind: str | None = None, msg: str | None = None) -> None:
    global _last
    if not os.environ.get("HC_TERMINAL_ID"):
        return
    key = (state, kind, msg)
    if key == _last:
        return
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


def _interactive(kwargs) -> bool:
    p = kwargs.get("platform")
    return p is None and _active or p in _INTERACTIVE


def _mark(kwargs) -> bool:
    global _active
    if kwargs.get("platform") in _INTERACTIVE:
        _active = True
    return _active


def _start(**kw):
    if _mark(kw):
        _emit("idle")


def _working(**kw):
    if _mark(kw):
        _emit("working")


def _idle(**kw):
    if _mark(kw):
        _emit("idle")


def _blocked(**kw):
    if _active:
        _emit("blocked", "permission", (kw.get("description") or "Approval needed"))


def _resolved(**kw):
    if _active:
        _emit("working")


def _finalize(**kw):
    global _last
    if _active:
        _last = None
        _emit("idle")


def register(ctx):
    ctx.register_hook("on_session_start", _start)
    ctx.register_hook("pre_llm_call", _working)
    ctx.register_hook("pre_tool_call", _working)
    ctx.register_hook("post_llm_call", _idle)
    ctx.register_hook("on_session_end", _idle)
    ctx.register_hook("pre_approval_request", _blocked)
    ctx.register_hook("post_approval_response", _resolved)
    ctx.register_hook("on_session_finalize", _finalize)
