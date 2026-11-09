"""Terminal-side Herdr status adapter for gateway-backed Hermes CLI clients.

Lives outside the Hermes checkout. No prompt, tool or gateway modifications.
"""
import functools
import importlib.abc
import importlib.machinery
import os
import sys
import threading


def emit(state):
    if not os.environ.get('HC_TERMINAL_ID'):
        return
    try:
        fd = os.open('/dev/tty', os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            os.write(fd, ('\x1b]7501;state=' + state + ':app=hermes\x1b\\').encode())
        finally:
            os.close(fd)
    except OSError:
        # No controlling tty (e.g. CLI help, gateway, redirected script).
        return


def patch_client(cls, writer=emit):
    if cls.__dict__.get('_herdr_status_adapter'):
        return
    original_init, original_chat, original_invalidate = cls.__init__, cls.chat, cls._invalidate

    def report(client):
        lock = getattr(client, '_herdr_status_lock', None)
        if lock is None:
            return
        with lock:
            state = 'working' if client._herdr_turn_depth else 'idle'
            if any(getattr(client, field, None) for field in (
                '_approval_state', '_clarify_state', '_sudo_state', '_secret_state',
                '_slash_confirm_state', '_connection_state',
            )):
                state = 'blocked'
            if state != client._herdr_last_status:
                writer(state)
                client._herdr_last_status = state

    @functools.wraps(original_init)
    def initialize(client, *args, **kwargs):
        client._herdr_status_lock = threading.RLock()
        client._herdr_turn_depth = 0
        client._herdr_last_status = None
        original_init(client, *args, **kwargs)
        report(client)

    @functools.wraps(original_chat)
    def chat(client, *args, **kwargs):
        with client._herdr_status_lock:
            client._herdr_turn_depth += 1
        report(client)
        try:
            return original_chat(client, *args, **kwargs)
        finally:
            with client._herdr_status_lock:
                client._herdr_turn_depth -= 1
            report(client)

    def wrap_refresh(original):
        @functools.wraps(original)
        def refresh(client, *args, **kwargs):
            report(client)
            return original(client, *args, **kwargs)
        return refresh

    cls.__init__, cls.chat = initialize, chat
    cls._invalidate = wrap_refresh(original_invalidate)
    if hasattr(cls, '_paint_now'):
        cls._paint_now = wrap_refresh(cls._paint_now)
    cls._herdr_status_adapter = True


class ClientLoader:
    def __init__(self, loader):
        self.loader = loader

    def create_module(self, spec):
        return self.loader.create_module(spec)

    def exec_module(self, module):
        self.loader.exec_module(module)
        patch_client(module.HermesCLI)

    def __getattr__(self, name):
        return getattr(self.loader, name)


class ClientFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != 'cli':
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec and spec.loader:
            spec.loader = ClientLoader(spec.loader)
        return spec


def install():
    if not os.environ.get('HC_TERMINAL_ID'):
        return
    if 'cli' in sys.modules:
        patch_client(sys.modules['cli'].HermesCLI)
    else:
        sys.meta_path.insert(0, ClientFinder())
