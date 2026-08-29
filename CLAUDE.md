# Claude · repo conventions

## What this is

A FastAPI proxy that drives an **OREI 401MV HDMI multiviewer** over RS-232 and
publishes it to Home Assistant via MQTT discovery. REST endpoints still exist
and still work, but MQTT is how the entities get created.

One image and one chart serve **two physical devices with different command
dialects**, selected at runtime by a **profile** (`app/profiles.py`):

| profile | device | bundle | transport |
|---|---|---|---|
| `uhd401mv` | basement UHD-401MV | `04-hdmi-multiviewer-proxy` | usbip, port pinned by-id |
| `hds401mv` | garage HDS-401MV | `57-hdmi-multiviewer-garage` | `socket://192.168.1.80:6638` (ESPHome bridge) |

The dialects differ by more than a prefix: the HDS wants `s power 1!` where the
UHD wants `power 1!`, its window border is global where the UHD's is per-window,
and each model rejects some of the other's commands. Anything model-specific belongs
in a profile field or a capability token — never an `if device == ...` at the
call site. Every setter is capability-gated and refuses rather than sends a
command the active model lacks.

## The firmware is authoritative

`help!` on the device is the source of truth for the command set. The vendor
manuals disagree with it in both directions — commands the manual omits, and
documented commands the firmware ignores. `docs/commands.md` records both command
sets with the discrepancies marked; read it before adding or changing a command
string.

An accepted range is not a set of distinct behaviours. Several parameters accept
values the device then treats identically, so verify a new setter changes
something observable rather than merely returning OK.

## Working with the hardware

Both units are **live in the house**. Someone may be watching the output.

- **Probes send reads only** (`r ...!`), and leave the box in the state you found
  it — capture the setting first, restore it after.
- **`reset` restores factory defaults including the serial baud rate.** Losing
  that costs all serial control until it is corrected through the on-screen menu.
  It is deliberately absent from MQTT discovery; keep it that way.
- **EDID-set renegotiates HDMI for all four sources** and can black the display
  or drop audio. Assert rendered command strings in tests; exercise it on real
  hardware only when the user asks.
- **UHD power commands take 30–60 s to land.** Checking state 5 s later reports
  the old value and reads as a broken switch — it isn't. Wait, then re-read.

## Releasing · the path crosses two repos

`make help` covers the local half (bump, tag). What it cannot tell you:

1. Pushing the tag triggers `release.yml`, which builds the image and publishes
   the chart. `verify-chart-published` gates on actually pulling the chart back
   and comparing digests, so a green run means the chart is really resolvable.
2. **The deploy is a second, manual step in the `homelab` repo** — bump
   `helm.version` in `homelab-gitops/bundles/04-hdmi-multiviewer-proxy/fleet.yaml`
   **and** `57-hdmi-multiviewer-garage/fleet.yaml`. Both instances run this chart;
   57 is the easy one to forget. Those bundles deliberately carry no `image.tag` —
   their `values.yaml` header explains why, and warns that sibling bundles differ.
3. Fleet's gitjob does not retry a failed sync. Check that it reconciled.

Verify a deploy by the structured log event `ha_discovery_published`, which
reports `profile`, `entities` and `retracted` per instance — the entity count
moving is the proof discovery re-ran, not just that the pod restarted.

## This repo is public

House configuration — `configuration.yaml`, automations, scripts, dashboards —
lives in the **private, local-only `home-assistant` repo**, which has its own sync
scripts. Documentation here describes how to integrate with the proxy; it does not
carry copies of the user's actual config.

## Git workflow

Finish work with a PR: branch, push, `gh pr create`.

**Work in a worktree, never the main checkout.** Several agent sessions share
this repo root, which has exactly one `HEAD`, so a commit made there lands on
whatever branch another session is using.

    git worktree add .worktrees/<topic> -b <branch>

`.worktrees/` is gitignored. Remove it when the branch merges:
`git worktree remove .worktrees/<topic>`.
