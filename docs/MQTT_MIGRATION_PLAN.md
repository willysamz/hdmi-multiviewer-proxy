# MQTT-ify `hdmi-multiviewer-proxy` — same migration we just did for the matrix

## Context

We just finished MQTT-ifying `hdmi-matrix-proxy` in commit `69ba0bd`
(plus `abb9af7` + `87f73b8` on the homelab repo). Same pattern, applied
now to the multiviewer.

The multiviewer's HA footprint is **larger** than the matrix's by entity
count, and the device itself is structurally **different** (serial-over-
USB, not HTTP; 34 flat REST endpoints, no unified state model). Net
result of the migration is similar though — HA's configuration.yaml
loses ~150–170 lines of REST scaffolding and gains a native MQTT device
card with proper `switch` / `select` / `number` / `binary_sensor`
entities instead of `input_select` + `input_number` + REST sensors +
template switch.

The just-migrated `template: switch.multiviewer_power` block (commit
`3e25fc7`) becomes the FIRST thing replaced by MQTT discovery in Phase
2 — entity_id pinned so no script/dashboard breakage.

## Today (REST-only)

`hdmi-multiviewer-proxy` is a FastAPI service that talks to the
multiviewer over **serial** (`/dev/ttyUSB0` via the CH340 USB/IP
passthrough, busid 1-13). 34 endpoints across 5 routers (health,
system, multiview, audio, output). Heartbeat task every 30 s checks
device power; no other internal poller.

HA consumes it through **~150-170 lines** of `configuration.yaml`:

| HA config block | Count | Lines |
|---|---|---|
| REST sensors (status, audio, multiview, windows, output, pip) | 11 sensors + 2 binary_sensors | ~83 |
| `rest_command` (power on/off, mode, windows, audio src/vol/mute, pip) | 15 commands | ~84 |
| `input_select` (mode, audio_source, 4× window, pip_position, pip_size) | 7 selects | ~73 |
| `input_number` (volume) | 1 number | ~7 |
| `template: switch` (multiviewer_power — migrated in 3e25fc7) | 1 switch | ~25 |

Dashboard `lovelace.multi_viewer` references **12 entity_ids** from
the above.

## After (MQTT discovery + push)

Mirror the matrix proxy's v0.2.0 layout. The multiviewer proxy gets:
- `app/mqtt_client.py` — identical to the matrix's (just re-titled).
- `app/discovery.py` — multiviewer-specific entity builders.
- `app/poller.py` — polls multiple multiviewer endpoints in one cycle,
  publishes deltas.
- `app/controller.py` — subscribes to many command topics; calls the
  serial handler.

REST endpoints stay (additive, belt-and-suspenders), same decision
as the matrix.

### Entities published via discovery

13 HA entities, one device card. Entity_ids pinned via `object_id` so
the just-migrated `switch.multiviewer_power` keeps working and all 12
dashboard references survive:

| Entity | Type | Replaces today |
|---|---|---|
| `switch.multiviewer_power` | `switch` (state + command) | `template: switch` (we migrated this in `3e25fc7`) |
| `binary_sensor.multiviewer_connected` | `binary_sensor` (connectivity) | `binary_sensor.multiviewer_connected` (REST-derived) |
| `select.multiviewer_mode` | `select` (single/pip/pbp/triple/quad) | `input_select.multiviewer_mode` + REST sensor |
| `select.multiviewer_window_1_input` | `select` (HDMI 1-4) | `input_select.multiviewer_window_1_input` |
| `select.multiviewer_window_2_input` | `select` | (same) |
| `select.multiviewer_window_3_input` | `select` | (same) |
| `select.multiviewer_window_4_input` | `select` | (same) |
| `select.multiviewer_audio_source` | `select` (Follow Window 1 / HDMI 1-4) | `input_select.multiviewer_audio_source` |
| `number.multiviewer_volume` | `number` (0-100, step 5) | `input_number.multiviewer_volume` |
| `switch.multiviewer_muted` | `switch` (was read-only binary_sensor; now writable!) | `binary_sensor.multiviewer_muted` |
| `select.multiviewer_pip_position` | `select` (TL/TR/BL/BR) | `input_select.multiviewer_pip_position` |
| `select.multiviewer_pip_size` | `select` (Small/Medium/Large) | `input_select.multiviewer_pip_size` |
| `sensor.multiviewer_resolution` | `sensor` (read-only) | REST sensor |

Bonus over current state: `mute` becomes natively toggleable instead of
a read-only binary_sensor that requires a separate REST command to flip.

### Topic layout (under prefix `multiviewer/`)

- State topics (publisher → MQTT, retained):
  - `multiviewer/power/state` — `ON`/`OFF`
  - `multiviewer/connected/state` — `ON`/`OFF`
  - `multiviewer/mode/state` — `single` / `pip` / `pbp` / `triple` / `quad`
  - `multiviewer/windows/{1..4}/state` — `HDMI 1` etc.
  - `multiviewer/audio/source/state` — `Follow Window 1` / `HDMI 1..4`
  - `multiviewer/audio/volume/state` — `0`..`100`
  - `multiviewer/audio/muted/state` — `ON`/`OFF`
  - `multiviewer/pip/position/state` — `Top Left` etc.
  - `multiviewer/pip/size/state` — `Small`/`Medium`/`Large`
  - `multiviewer/output/resolution/state` — `1920x1080@60` etc.
  - `multiviewer/bridge/available` — `online`/`offline` (LWT)
- Command topics (HA → proxy):
  - `multiviewer/power/set` — `ON`/`OFF`
  - `multiviewer/mode/set` — one of the modes
  - `multiviewer/windows/{1..4}/set` — input name
  - `multiviewer/audio/source/set` — source name
  - `multiviewer/audio/volume/set` — `0`..`100`
  - `multiviewer/audio/muted/set` — `ON`/`OFF`
  - `multiviewer/pip/position/set` — position name
  - `multiviewer/pip/size/set` — size name

### Poll cycle

The current 30 s REST polls in HA become a single 10 s poll cycle in
the proxy, hitting `/api/status`, `/api/audio`, `/api/multiview`,
`/api/windows`, `/api/output`, `/api/pip` per cycle. Cycle publishes
only the topics whose value has changed since the last cycle. Matches
the matrix poller's pattern.

### Capability coverage (does MQTT-only do everything today does?)

| Today (REST + input_select + template switch) | MQTT-only equivalent | Match? |
|---|---|---|
| Power on/off (template switch) | `switch.multiviewer_power` + command topic | ✅ |
| Read all REST sensors (mode, audio, windows, output, pip) | Discovered sensors/selects + retained state topics | ✅ identical |
| Per-window input change | `select.multiviewer_window_N_input` command | ✅ |
| Mode change | `select.multiviewer_mode` | ✅ |
| Volume up/down/set | `number.multiviewer_volume` | ✅ (up/down done via JS step on the number) |
| Mute on/off/toggle | `switch.multiviewer_muted` (toggle is built into HA's switch) | ✅ improved |
| PIP position/size | Two selects | ✅ |
| Resolution display | `sensor.multiviewer_resolution` | ✅ |

No gaps. Bulk "preset"-style command isn't a concept on the multiviewer
(no atomic multi-route operation in the device's serial protocol), so
nothing like matrix's `matrix/routing/preset/set` is needed.

### Dashboard impact analysis

`lovelace.multi_viewer` references **13 multiviewer entity_ids** today.
Phase 1 ships MQTT entities *alongside* the existing ones (different
entity_ids because they live in different HA domains for 11 of 13
cases) — **so during Phase 1 the dashboard is unaffected**. The
breakage risk is in Phase 2 when we remove the legacy entities.

Side-by-side, with required dashboard edits flagged:

| Today's dashboard entity_id | After Phase 2 | Edit needed? |
|---|---|---|
| `switch.multiviewer_power` | `switch.multiviewer_power` (MQTT) | **No** — pinned `object_id` keeps the id |
| `binary_sensor.multiviewer_connected` | `binary_sensor.multiviewer_connected` (MQTT) | **No** — pinned |
| `input_select.multiviewer_mode` | `select.multiviewer_mode` | Yes — JSON search-and-replace |
| `input_select.multiviewer_window_{1..4}_input` (×4) | `select.multiviewer_window_{1..4}_input` | Yes ×4 |
| `input_select.multiviewer_audio_source` | `select.multiviewer_audio_source` | Yes |
| `input_select.multiviewer_pip_position` | `select.multiviewer_pip_position` | Yes |
| `input_select.multiviewer_pip_size` | `select.multiviewer_pip_size` | Yes |
| `input_number.multiviewer_volume` | `number.multiviewer_volume` | Yes |
| `binary_sensor.multiviewer_muted` | `switch.multiviewer_muted` (now writable!) | Yes — and consider switching the dashboard card from a state-display card to a toggle card so the new write capability is usable |
| `sensor.multiviewer_mode` | (redundant; use `select.multiviewer_mode.state`) | Yes — drop the duplicate card OR re-point to the select |

`input_select` ↔ `select` and `input_number` ↔ `number` render
identically in HA's standard dashboard cards (both are picker-style /
slider-style respectively). The Lovelace card type doesn't change;
only the `entity:` value needs updating in the dashboard JSON. ~10
single-line edits in `.storage/lovelace.multi_viewer` during Phase 2.

The `binary_sensor.multiviewer_muted` → `switch.multiviewer_muted` is
the only **upgrade** worth highlighting: today the dashboard can only
*display* mute state (HA had to call `rest_command.multiviewer_mute` /
`_unmute` via a button card to actually flip it); with the new
`switch` entity, a standard toggle card both displays + controls mute
in one card. Phase 2 dashboard sweep is a natural moment to simplify
that section.

## 🚫 Do NOT push to any remote during Phase 1

Same constraint as the matrix work, for the same reasons:
- `hdmi-multiviewer-proxy` is a **public GitHub repo**. Do not `git push` or `git push --tags`. No release will be created; no chart will be published to gh-pages.
- `homelab-gitops` (private repo) edits are also local-only. Do not `git push`.
- All commits stay on the local `main` branches until the user explicitly authorizes pushing.

## Phase 1 — proxy ships MQTT, REST stays (v0.2.0 of the chart)

0. **Persist this plan to the proxy repo first** — copy to
   `hdmi-multiviewer-proxy/docs/MQTT_MIGRATION_PLAN.md` so it survives
   beyond the plan file's session scope. (Same as we did with the
   matrix.)

1. Add `aiomqtt==2.0.1` to `requirements.txt`.

2. Add MQTT + HA settings to `app/config.py`:
   `mqtt_enabled` (opt-in default off), `mqtt_host`, `mqtt_port`,
   `mqtt_username`, `mqtt_password`, `mqtt_client_id`,
   `mqtt_topic_prefix` (default `multiviewer`), `mqtt_keepalive`,
   `mqtt_qos`, `ha_discovery_enabled`, `ha_discovery_prefix`,
   `ha_device_name`, `ha_device_id` (default `hdmi_multiviewer`).

3. **Copy `app/mqtt_client.py` verbatim from the matrix proxy** —
   the file is device-agnostic. The only differences are the default
   `availability_topic` and `client_id` strings.

4. Create `app/discovery.py`. Builders for each of the 13 entity types,
   each pinning `object_id` to match today's entity_ids:
   - `power_switch_payload()` → `switch.multiviewer_power`
   - `connected_binary_sensor_payload()` → `binary_sensor.multiviewer_connected`
   - `mode_select_payload()` → `select.multiviewer_mode`
   - `window_select_payload(n)` → `select.multiviewer_window_N_input`
   - `audio_source_select_payload()` → `select.multiviewer_audio_source`
   - `volume_number_payload()` → `number.multiviewer_volume`
   - `mute_switch_payload()` → `switch.multiviewer_muted`
   - `pip_position_select_payload()` → `select.multiviewer_pip_position`
   - `pip_size_select_payload()` → `select.multiviewer_pip_size`
   - `resolution_sensor_payload()` → `sensor.multiviewer_resolution`

5. Create `app/poller.py`. One cycle calls each of:
   `client.get_status()`, `get_audio()`, `get_multiview()`,
   `get_windows()`, `get_output()`, `get_pip()`. Tracks last-published
   value per topic and publishes deltas. On the first successful
   cycle, also publishes HA discovery payloads (retained). Re-publishes
   discovery when a name (currently none have configurable names — but
   keep the hook for future).

6. Create `app/controller.py`. Subscribes to the command-topic list
   above. Each branch translates payload → corresponding `client.set_*`
   call:
   - `power/set` → `client.set_power(True|False)`
   - `mode/set` → `client.set_multiview(payload)`
   - `windows/N/set` → resolve "HDMI X" → int, `client.set_window_input(N, x)`
   - `audio/source/set` → resolve to int code, `client.set_audio_source(...)`
   - `audio/volume/set` → `client.set_audio_volume(int(payload))`
   - `audio/muted/set` → `client.set_audio_mute(payload == "ON")`
   - `pip/position/set` → resolve to int code, `client.set_pip_position(...)`
   - `pip/size/set` → resolve to int code, `client.set_pip_size(...)`
   On success, fire `poller.trigger_immediate_poll()` so HA catches the
   confirmed state quickly.

7. Wire into `app/main.py`'s lifespan: matrix-pattern session ctx +
   poller + command subscriber. Opt-in via `MQTT_ENABLED`.

8. Bump `VERSION` to `0.2.0`. Bump `chart/Chart.yaml` version + appVersion to `0.2.0`.

9. Extend `chart/values.yaml` with `mqtt:` + `ha:` blocks (mirror
   matrix's structure). Add `chart/templates/secret.yaml` for
   `MQTT_USERNAME` + `MQTT_PASSWORD` when set. Update
   `chart/templates/configmap.yaml` with the new env vars. Update
   `chart/templates/deployment.yaml` envFrom to optionally include the
   Secret.

10. Update `homelab-gitops/bundles/04-hdmi-multiviewer-proxy/`:
    - `fleet.yaml`: bump chart version `0.x.y` → `0.2.0`.
    - `helm/values.yaml`: set `mqtt.enabled: "true"`, `mqtt.host:
      mqtt.mqtt.svc.cluster.local`, `ha.deviceName: "HDMI Multiviewer"`,
      `ha.deviceId: hdmi_multiviewer`.

11. Update `docs/content/architecture/apps/04-hdmi-multiviewer.md` to
    note the MQTT integration (mirror what we did for 05-hdmi-matrix).

12. Commit locally in both repos. **No push, no tag.**

## Phase 2 — HA-side cleanup (separate, after Phase 1 verified)

After 24 h of clean side-by-side operation (new MQTT entities reading
the same state as the legacy ones):

1. Verify the new MQTT-discovered entities exist with the pinned entity_ids:
   - `switch.multiviewer_power`, `switch.multiviewer_muted`,
   - `binary_sensor.multiviewer_connected`,
   - `select.multiviewer_{mode,audio_source,window_{1..4}_input,pip_position,pip_size}`,
   - `number.multiviewer_volume`,
   - `sensor.multiviewer_resolution`.
2. **Remove** these from `home-assistant/configuration.yaml`:
   - 7 REST resources for multiviewer (~83 lines).
   - 15 `rest_command` entries (~84 lines).
   - 7 `input_select` entries (~73 lines).
   - 1 `input_number.multiviewer_volume` (~7 lines).
   - The migrated `template: - switch: multiviewer_power` (~25 lines,
     since the MQTT-discovered `switch.multiviewer_power` takes over).
3. Push HA config (`bash push-ha-config.sh`).
4. Restart HA pod (`kubectl rollout restart sts/home-assistant`).
5. **Update `lovelace.multi_viewer`** (~10 single-line JSON edits):
   - 6× `input_select.multiviewer_{mode,audio_source,window_1_input,window_2_input,window_3_input,window_4_input}` → `select.…` (same suffix).
   - 2× `input_select.multiviewer_pip_{position,size}` → `select.…`.
   - 1× `input_number.multiviewer_volume` → `number.multiviewer_volume`.
   - 1× `binary_sensor.multiviewer_muted` → `switch.multiviewer_muted` — and consider swapping that card from a state-display to a toggle so the new write capability becomes usable in the UI.
   - 1× `sensor.multiviewer_mode` — either drop (redundant with `select.multiviewer_mode.state`) or re-point to the select.
   The two `switch.multiviewer_power` + `binary_sensor.multiviewer_connected` references are unchanged because their entity_ids are pinned.
6. Audit `scripts.yaml` / `automations.yaml` for any other references.
7. `bash sync-ha-config.sh` to capture the cleaned registry; commit
   locally to home-assistant repo.

## Phase 3 — proxy cleanup (much later, optional)

Mark REST endpoints deprecated in v0.2.x and remove them in a future
v0.3.0 after ~3 months of clean MQTT operation.

## Critical files (Phase 1 only)

| Repo | File | Action |
|---|---|---|
| `hdmi-multiviewer-proxy/app/` | `config.py`, `main.py` | Add MQTT settings; wire lifespan tasks |
| `hdmi-multiviewer-proxy/app/` | `mqtt_client.py`, `discovery.py`, `poller.py`, `controller.py` | New files |
| `hdmi-multiviewer-proxy/` | `requirements.txt`, `VERSION`, `chart/Chart.yaml`, `chart/values.yaml`, `chart/templates/configmap.yaml`, `chart/templates/deployment.yaml` | Bump + extend |
| `hdmi-multiviewer-proxy/chart/templates/` | `secret.yaml` | New |
| `hdmi-multiviewer-proxy/docs/` | `MQTT_MIGRATION_PLAN.md` | New — copy of this plan |
| `homelab-gitops/bundles/04-hdmi-multiviewer-proxy/` | `fleet.yaml`, `helm/values.yaml` | Bump chart version, wire MQTT host |
| `docs/content/architecture/apps/04-hdmi-multiviewer.md` | doc | Note MQTT integration |

## Verification (Phase 1)

1. `python3 -c "import ast; [ast.parse(open(p).read()) for p in ['app/config.py','app/main.py','app/mqtt_client.py','app/discovery.py','app/poller.py','app/controller.py']]; print('ok')"` — Python syntax.
2. `helm lint chart/` — chart syntax.
3. `git log --oneline origin/main..HEAD` — confirms commits exist locally, are NOT pushed.

When user authorizes push later:
- `hdmi-multiviewer-proxy`: `git push origin main && git push origin v0.2.0` (triggers chart publish).
- `homelab-gitops`: `git push origin main` (Fleet rolls v0.2.0 chart).
- Verify in HA: Settings → Devices & Services → MQTT → "HDMI Multiviewer" device card appears with all 13 entities.

## Decisions locked in (mirroring the matrix work)

- **MQTT + REST coexist.** REST endpoints stay indefinitely.
- **Opt-in via `MQTT_ENABLED`** — bundle sets it true; library users default off.
- **Entity_id pinning** via `object_id` so dashboards + scripts + the
  just-migrated `switch.multiviewer_power` template don't break.
- **Phase 1 only** — Phase 2 (HA-side cleanup) is a separate, later session.
- **No push** until user authorizes.

## Differences worth flagging vs the matrix migration

1. **More entity types** — multiviewer needs `switch`/`select`/`number`/
   `binary_sensor`/`sensor`. Matrix only needed `select` + `binary_sensor`.
   ~2× the discovery payload functions in `discovery.py`.
2. **Multi-endpoint poll cycle** — proxy polls 6 endpoints per cycle instead
   of 1. Same cadence (10 s); just more I/O per tick.
3. **Mute upgrade** — today's `binary_sensor.multiviewer_muted` is read-only
   in HA; MQTT-discovered `switch.multiviewer_muted` is writable, so dashboards
   can toggle it directly. Small UX win.
4. **Volume as `number` instead of `input_number`** — the new MQTT-discovered
   `number.multiviewer_volume` has a command topic that calls
   `set_audio_volume()` directly. Today there's a separate
   `input_number.multiviewer_volume` whose value an automation has to
   `rest_command` over to the device. One layer removed.
5. **No bulk-preset analog** — matrix had `matrix/routing/preset/set`
   for atomic multi-route. Multiviewer's serial protocol has no atomic
   multi-op, so no analog needed.
6. **Multiviewer is on USB/serial** — the proxy itself reaches the
   device through `/dev/ttyUSB0` (CH340 over USB/IP from Harvester).
   Doesn't change anything about the MQTT layer, but worth keeping in
   mind: if the multiviewer is powered off or USB drops, MQTT
   availability flips offline via LWT and HA marks the device card
   unavailable — same as today's `availability_template` on the power
   switch, but now automatic.
