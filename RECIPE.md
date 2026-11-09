# Hermes Status

Makes Hermes Agent show up in the Herdr desktop app's Agents panel like Claude Code does: listed under Working / Idle / Blocked with the Hermes icon and name, and counted in space and tab status. Without it, Hermes appears as a plain `python3` or `zsh` terminal.

![Hermes Status](preview.png)

Note: this is a Hermes plugin, not a Herdr mod. It has no `mods/` or `layouts/` folder, no `main.js` and no `keys.json`. It is published under `herdr-mod` because it extends what Herdr shows.

## What you see

The Agents panel (left sidebar, `workspace-chrome` layout) lists the Hermes terminal as `<folder> · <terminal id>` with the Hermes glyph (the built-in `hermes` program in Herdr's programs table: name "Hermes", tile `#1c1d21`, white tint). Spinner and group heading follow the status below. No new UI is drawn.

## How it behaves

Herdr treats a terminal as an agent only when the program reports status over OSC 7501. The plugin sends `ESC ] 7501 ; state=<s>:app=hermes ESC \` (plus `kind=permission` and base64 `msg` when blocked):

- `working`: a turn starts (`pre_llm_call`) and when each tool starts (`pre_tool_call`).
- `idle`: session start, turn end (`post_llm_call`), `on_session_end`, `on_session_finalize`.
- `blocked` (kind `permission`, msg = the approval description, max 120 chars): `pre_approval_request`.
- back to `working`: `post_approval_response`.
- `done` is never sent.

Repeated identical reports are dropped. It does nothing unless `HC_TERMINAL_ID` is set (i.e. inside a herdr-core terminal), and only after a hook with `platform` in `cli, tui, desktop, acp` has been seen, so the Telegram gateway and cron runs never emit.

## Built from

One folder, `hermes-plugin/herdr-app-status/`, copied to `~/.hermes/plugins/herdr-app-status/`:

- `plugin.yaml`: `name: herdr-app-status`, `version: "1.0"`, a one-line description.
- `__init__.py`: `register(ctx)` calls `ctx.register_hook` for `on_session_start`, `pre_llm_call`, `pre_tool_call`, `post_llm_call`, `on_session_end`, `pre_approval_request`, `post_approval_response`, `on_session_finalize`. `_emit(state, kind, msg)` builds the sequence and writes it to `/dev/tty` (opened `O_WRONLY|O_NOCTTY|O_NONBLOCK`; OSError ignored), never stdout, so captured output can't swallow it. Module globals `_last` (dedupe) and `_active` (set by `_mark` on the first interactive-platform hook).
- Enable it: add `herdr-app-status` to `plugins.enabled` in `~/.hermes/config.yaml`, then start a NEW `hermes` process in a Herdr terminal.
- No Herdr files are changed. It is independent of the `herdr-agent-state` plugin that `herdr integration install hermes` writes (that one only reports session ids for resume and can stay enabled).

## Watch out

- Restart Hermes after enabling. A running process keeps the old plugin set, and a tab opened before enabling stays unlisted.
- Do not use `herdr pane report-agent`: that is the older `herdr` TUI server's API. The desktop app (`herdr-app` + `hc`) only reads OSC 7501.
- Write to `/dev/tty`, not stdout: Hermes' CLI captures stdout.
- `kwargs["platform"]` is `cli` on session and first-LLM hooks but `None` on later `pre_llm_call` and `pre_tool_call` calls, so gate on the `_active` flag, not on `platform` alone.
- Assumes Herdr 0.9.x desktop app with herdr-core, Hermes with plugin hooks incl. `pre_approval_request`, macOS or Linux (needs `/dev/tty`).
- Working and blocked records clear when the process exits; Herdr shows the terminal as an agent only while Hermes runs.

## Done when

1. `hermes plugins list` (or the startup log) shows `herdr-app-status` loaded.
2. In a Herdr terminal, start `hermes`, send a message, and run `hc ls` from another terminal: that terminal shows `"agent":"hermes"` with `"status":"working"` during the turn and `idle` afterwards.
3. `hc get <terminal>` has `"reported": true` and `status.app` equal to `hermes`.
4. The Agents panel lists it under Working or Idle with the Hermes icon.
5. Triggering an approval prompt moves it to Blocked, and answering moves it back to Working.
6. Running `hermes` outside Herdr, or `hermes gateway`, emits nothing and raises no errors.
