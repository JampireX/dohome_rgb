# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant **custom integration** (distributed via HACS / hapm) that controls DoHome
RGB bulbs and strips over the **local network via TCP**. All device protocol logic lives in
the external `dohome-api` package (pinned `==2.2.1`); this repo only adapts that library to
Home Assistant's config-entry + entity model. The integration exposes a single platform:
`light`.

Domain: `dohome_rgb`. All code is under `custom_components/dohome_rgb/`.

## Commands

Dependencies are managed with **uv** from `pyproject.toml` only — there is **no committed
`uv.lock`**, so `uv sync` resolves the latest versions allowed by the constraints. There is no
Makefile; run `uv` directly:

| Task | Command |
| --- | --- |
| Create/refresh venv | `uv venv --python 3.14` then `uv sync` |
| Type check | `uv run basedpyright custom_components/` |

There is **no test suite** and **no linter** — do not invent commands for either. ruff and
pylint were removed; `basedpyright` (configured in `pyproject.toml` under `[tool.basedpyright]`)
is the only static-analysis step. CI runs `.github/workflows/validate.yml` (HACS + hassfest)
and `.github/workflows/release.yml` (publishes a release when `manifest.json` `version` bumps).

## Architecture

Read these four files together to understand the flow; each is small but they are tightly
coupled through `entry.runtime_data` and the `dohome-api` types.

- **`__init__.py`** — config-entry lifecycle. Defines the `DoHomeRuntimeData` dataclass
  (`client` + parsed `info`) and the typed `DoHomeConfigEntry = ConfigEntry[DoHomeRuntimeData]`.
  `async_setup_entry` builds the `APIClient` once (the `TCPStream` constructor does no I/O)
  and stores it on `entry.runtime_data`, then forwards to the `light` platform; unload just
  unloads the platform (no `hass.data` cleanup). `async_migrate_entry` upgrades **v1 → v2**
  entries by re-parsing the stored raw device info through `parse_doit_device_info`. The
  config-entry `VERSION` is **2** (set in `config_flow.py`); bump both the flow version and
  add a migration branch when the stored data shape changes. `async_setup` (component-level)
  starts a **1-minute background discovery** loop (`async_track_time_interval`) that scans the
  LAN and opens an `integration_discovery` flow per found device — these appear as
  "discovered device" cards. Note: `async_setup` only runs once the integration is loaded
  (i.e. after the first entry exists), so the very first device is added via the config flow.

- **`config_flow.py`** — UI setup only (no YAML import). `async_step_user` has a single
  **optional** host field: if filled, the device is added directly (probe via `_async_read_device`
  → `unique_id` from `encode_device_id`); if left empty, it scans the LAN (`async_step_pick`,
  a `cv.multi_select` of unconfigured devices). Selected devices are added one per config entry
  — the first inline, the rest via auto-confirmed `integration_discovery` flows. Background-
  discovered devices land in `async_step_integration_discovery` → `async_step_discovery_confirm`
  (the confirmation card), and `_abort_if_unique_id_configured(updates=...)` refreshes a
  device's IP if it changed. `async_step_reconfigure` changes the host of an existing entry
  (verifies the **same** `unique_id`, writes `entry.data`, reloads); it replaced the old
  `OptionsFlow`, which wrote to `entry.options` and was silently ignored.

- **`discovery.py`** — tolerant LAN discovery over UDP broadcast (port 6091, PING/PONG
  datagrams), returning `DiscoveredDevice`s keyed by `unique_id`. It does **not** use
  `dohome-api`'s `discover()`: that helper validates responses against a misspelled
  `compandy_id` key while real devices send `company_id`, so it raises on every reply.
  `sta_ip` (not `host_ip`) is the device's routable LAN address. Broadcasts to every local
  /24 plus `255.255.255.255` because the library's `get_discovery_host()` returns `""` on
  multi-homed hosts.

- **`light.py`** — `DoHomeLightEntity(LightEntity)`, the only entity. Supports two color
  modes (`RGB` and `COLOR_TEMP`); the Kelvin range comes from `dohome-api` constants
  (`KELVIN_MIN`/`KELVIN_MAX`). Device commands map to `client.set_power / set_white /
  set_color`. It also exposes the 27 built-in hardware effects (`LightEntityFeature.EFFECT`)
  via the module-level `EFFECTS` label→`Effect` map and `client.set_effect`.
  - **State model is optimistic.** The `_state_known` flag means the device's real state is
    read from the bulb only once (first successful poll or first explicit `turn_on`), after
    which Home Assistant tracks brightness/color/mode/effect **locally** and stops overwriting
    them from polls. Be careful changing this — it is intentional, not a bug, because the
    hardware does not reliably report color state and never reports the active effect.
  - All `dohome-api` calls are wrapped to catch `(asyncio.TimeoutError, DoHomeException,
    OSError)` and flip `_attr_available = False` for connection resilience.

- **`constants.py`** — `DOMAIN` and the `CONF_*` keys used as config-entry data keys.

### Cross-cutting notes

- The integration is **polling** (`light.py` sets `SCAN_INTERVAL = 10s` with the default
  `should_poll`); `manifest.json` declares `iot_class: local_polling` to match. `dohome-api`
  has no push/subscribe mechanism — each request opens a fresh TCP connection.
- The `dohome-api` version is pinned identically in **both** `pyproject.toml` and
  `manifest.json` `requirements`; update both together.
- `homeassistant` is floored at the latest release (`>=2026.6.2`) in `pyproject.toml`; the
  Python requirement is `>=3.14` because HA 2026.6 needs Python 3.14.2. No `uv.lock` is kept,
  so re-running `uv sync` always pulls the newest matching versions.
- User-facing strings live **only** in `translations/en.json` + `translations/ru.json` (the
  runtime source for a custom component). There is intentionally no `strings.json`; note that
  `hassfest` CI normally expects one, so that check may warn.
- Bump `manifest.json` `version` for releases (HACS reads it).
