# Herdr status for Hermes

**Native plugin v2.0.0** — show classic Hermes terminal sessions as Working, Idle, or Blocked in Herdr, rather than as an unidentified Python process.

> **Install on every machine and OS user that actually runs Hermes.** If you use Herdr on a Mac and run Hermes on a Linux development machine over SSH, run setup on **both** machines, as the user who launches Hermes there. Installing only on the Mac does not fix remote agents. Remote status travels through the existing SSH terminal connection; no new port is needed.
>
> Setup does not copy credentials, connect to other machines, install remotely, or restart running agents.

## Requirements and scope

- Linux or macOS, with Git and Python 3.9 or newer available.
- An installed, working Hermes CLI; the recommended route requires Hermes native plugin installation support.
- Herdr with terminal agent-status support. Launch sessions inside a Herdr terminal, locally or over SSH.
- A writable, per-user Hermes launcher installation. **No `sudo` is required or recommended.** Stop and investigate if permissions require it.

This integration targets the **classic Python `HermesCLI` lifecycle**. The separate Ink interface (`hermes --tui`, including when selected as the default interface) is not covered. Desktop, gateway, and other non-classic surfaces are not implied to be supported.

## Install

Run these commands on each execution machine, as the user who runs Hermes:

```bash
hermes plugins install jspoynor/herdr-hermes-status --enable
hermes herdr setup
hermes herdr status
```

The native plugin and its installed key are **`herdr-status`**; its management command is **`herdr`**. Inspect registration with `hermes plugins show herdr-status`. Plugin installation registers the command. The explicit `setup` step installs the terminal companion; loading the plugin alone does not modify your launcher.

### Migrating from the old plugin

Disable `herdr-app-status` in **every affected Hermes profile** to avoid competing status reports:

```bash
# Default profile
hermes plugins disable herdr-app-status

# Example named profile
hermes -p code plugins disable herdr-app-status
```

Repeat for other affected profiles. The new companion is per-machine/per-user, not a separate launcher patch for every profile. Native plugin availability and the old plugin's enabled state remain profile-specific; use the intended profile when managing plugins.

### Activate and verify

New Hermes processes launched through the configured launcher pick up the companion automatically. For an already-running agent, finish or save its work, exit, and **relaunch or resume it in a new process**. `/reset` alone does not reload the launcher or retrofit a running process.

1. Run `hermes herdr status` and inspect the launcher, companion, and backup/state diagnostics.
2. Start a classic Hermes session in a Herdr terminal.
3. Check that Herdr identifies it as Hermes and shows Idle while waiting for input.
4. Send a request: expect Working during the turn, then Idle after completion. If an approval is requested, check Blocked and the return to Working after responding.
5. Repeat on each remote execution machine through your usual SSH terminal.

A successful setup or diagnostic command is not proof of a live status transition. Verify the session in Herdr itself.

## Clone-based fallback

If native plugin installation is unavailable, clone the repository and use its standalone entry point:

```bash
mkdir -p ~/src
cd ~/src
git clone https://github.com/jspoynor/herdr-hermes-status.git
cd herdr-hermes-status
python3 install.py setup
python3 install.py status
```

**This route installs only the terminal companion. It does not register or enable the native Hermes plugin**, so it does not by itself make `hermes herdr …` available. Continue using `python3 install.py status` and `python3 install.py uninstall` from the checkout, or install the native plugin separately later. The same migration and per-machine requirements apply.

## Management and recovery

```bash
hermes herdr status       # Inspect installation health before changing it
hermes herdr setup       # Install, refresh, or repair the companion
hermes herdr uninstall   # Remove the managed wrapper and restore its backup
```

The standalone equivalents are `python3 install.py status`, `python3 install.py setup`, and `python3 install.py uninstall`. Preview setup without changing files:

```bash
hermes herdr setup --dry-run
# Standalone equivalent:
python3 install.py setup --dry-run
```

Management supports `--dry-run`, `--launcher PATH`, and `--runtime-launcher PATH`; consult command help before overriding discovery. The common root runtime is autodetected using `--print-runtime-command`. Setup refuses symlink launchers and unknown changed launchers rather than guessing how to modify them.

Setup copies the stable companion payload to `~/.local/share/hermes-herdr`, so removing the source clone or plugin directory does not silently break an installed shim. It also keeps a backup of the original launcher and installation state. It is designed to be safely repeatable: rerunning setup should not stack wrappers or replace the original backup with an already-wrapped launcher. Uninstall uses that state to roll back the managed launcher changes. If the launcher has been independently modified or diagnostics report a conflict, stop and inspect it rather than force-overwriting it or deleting the backup.

**Uninstall the companion before disabling or removing the native plugin**, while the management command is still available:

```bash
hermes herdr uninstall
hermes plugins remove herdr-status
```

If you want to retain the plugin files, use `hermes plugins disable herdr-status` instead of removal, still after companion uninstall. Confirm the resulting installation state and normal Hermes startup.

For general Hermes health checks, use `hermes doctor`; for this integration's launcher/companion diagnostics, use `hermes herdr status`. Neither replaces a live terminal check.

### Updates and compatibility

The wrapper depends on the runtime format of the top-level Hermes launcher and the classic Python CLI lifecycle. A Hermes update may change that format or overwrite the wrapper. After updating Hermes or this integration, run `hermes herdr status`, rerun `hermes herdr setup` if needed, and verify a new session. Do not assume an unknown launcher format is safe to patch.

## How it works

The native plugin registers CLI management commands. It adds no agent tools or prompt content and performs no automatic filesystem installation on import.

Explicit setup installs a per-user launcher wrapper and stable companion payload. The companion uses a Python import finder to adapt the **actual terminal `HermesCLI` lifecycle** at runtime, rather than relying only on the old inline plugin hooks. It reports Herdr terminal status using OSC 7501 through the terminal, including Working, Idle, and approval-related Blocked states.

- No Hermes core checkout modifications.
- No credentials or tokens required by the companion.
- No network daemon, listener, or additional SSH port.
- No automatic remote deployment or process restart.
- No Herdr UI mod installation.

The historical `RECIPE.md` and `hermes-plugin/herdr-app-status/` directory are retained as legacy reference, **not the v2 installation procedure**.

## Development

Run the standard-library test suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The installation, migration, verification, and rollback sections above are the runbook for both people and installation agents. Give an agent this repository URL and ask it to follow those sections on each authorized execution machine, then report each machine's verification separately. Setup does not grant permission to access another machine or restart existing work.

Automated tests do not establish compatibility with every Hermes launcher release or replace local and SSH smoke tests.

## License

MIT.
