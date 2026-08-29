# Targeted read-back after a set — design

**Repo:** `willysamz/hdmi-multiviewer-proxy` @ 0.6.5
**Files:** `app/poller.py` (~390 lines), `app/controller.py` (~172 lines), `tests/test_poller.py`

## Problem

0.6.5 made the post-command nudge force the config-class read, taking
confirmation from ≤60 s to ~6 s. Measured on the live garage HDS: 6.0 s and
7.5 s across two toggles.

~6 s is the duration of a *full* poll sweep (~25 serial round trips over the
ESPHome socket bridge). The confirming read for Source OSD sits at the very
end of it. The nudge guarantees the read happens on the next cycle; it does
not make that cycle short.

## Goal

After a successful set, read back **only the setting just changed** and
publish it — one round trip, target <1 s — then let the existing nudged
sweep refresh everything else.

## Why not optimistic publish

Publishing the commanded value without reading is one line and instant, and
it is wrong here: the HDS **silently ignores EDID writes** (returns OK, does
nothing). Optimistic publish would render a silently-ignored command as
success. The read-back reports what the device actually did, which is the
property worth paying a round trip for.

## Design

Every setting's read → value-mapping → publish is currently an inline block
inside `poll_once` / `_poll_config_settings`. Extract each into a named
method on `Poller`. The poll loop calls them in sequence; `Controller._send`
calls the single one its command changed. Each setting's command, parser,
value mapping and topic then live in exactly one place, used by both paths.

    # poller.py
    @property
    def _prefix(self) -> str: return self.settings.mqtt_topic_prefix.strip("/")

    async def refresh_source_osd(self) -> None:
        if not self.profile.supports(CAP_SOURCE_OSD): return
        v = await self._read(self.profile.GET_SOURCE_OSD, ResponseParser.parse_source_osd)
        if v is not None:
            await self._publish_delta(f"{self._prefix}/window/source_osd/state", "ON" if v else "OFF")

    async def refresh(self, key: str) -> None:
        """Read+publish one setting. Keys: 'source_osd', 'window:3',
        'layout:quad:aspect', ..."""

    # controller.py
    async def _send(self, command, descr, refresh: str | None = None) -> None:
        ...                                    # unchanged: send, raise on failure
        if refresh:
            try:
                await self.poller.refresh(refresh)
            except Exception as exc:           # never fail a command that succeeded
                log.warning("post_set_refresh_failed", action=descr, key=refresh, error=str(exc))
        self.poller.trigger_immediate_poll()   # unchanged: sweep the rest

Refreshers (20): `mode`, `window:{1..4}`, `input_source`, `audio_source`,
`audio_volume`, `audio_muted`, `pip_position`, `pip_size`, `auto_switch`,
`edid`, `resolution`, `hdcp`, `vka`, `video_mode`,
`layout:{quad,pbp,triple}:{mode,aspect}`, `window_border`, `border_colors`,
`source_osd`.

## Deliberate exclusions

- **`power`** — the UHD takes 30–60 s to act. An immediate read-back returns
  the pre-command value, so the toggle would spring back exactly as reported.
  That is already today's behaviour (power is in the fast group, read every
  cycle), so excluding it is not a regression, and including it would look
  like the bug we are fixing.
- **`reboot`** — the device is going away; nothing to read.

## Risks

1. **Device settle time.** If the unit needs time after a write before a read
   reflects it, the read-back publishes the *old* value. The nudged sweep
   corrects it within ~6 s, so worst case equals today's behaviour — but this
   must be measured on real hardware, not assumed.
2. **Serial ordering.** `SerialHandler` serialises on an `asyncio.Lock`, so
   the read-back queues behind the write and behind any in-flight poll read.
   Confirm no path bypasses the lock.
3. **Refactor regression.** 20 blocks move. The poll loop must publish exactly
   what it publishes today; `resolution` writes two topics and must keep both.

## Testing

- Unit: each refresher publishes its topic and nothing else; capability-gated
  refreshers no-op on the wrong profile; `refresh()` on an unknown key raises.
- Unit: `_send` with `refresh=` calls exactly that refresher, before the
  nudge; a raising refresher does not fail the command.
- Regression: the existing 0.6.5 tests still pass unchanged.
- Hardware: toggle garage Source OSD, measure command→state latency, restore
  the starting state. Target <1 s vs the measured 6.0/7.5 s.

---

# Revision after adversarial review

Accepted findings, all verified against the code before acceptance.

**R1 (was Critical). Generation guard — the race the plan created.**
`poller.start()` and `_command_subscriber` are separate tasks
(`main.py:101-104`), and `send_command` takes the lock per command, not per
sweep. A command landing mid-sweep lets the sweep publish its *stale* read
after the targeted publish: value appears, snaps back, corrects ~6 s later —
a visible flicker, worse than the bug. `trigger_immediate_poll` now bumps
`_generation`; `poll_once` captures it at entry and abandons publishing once
superseded.

**R2 (was Critical). Flush before write.** `reset_input_buffer()` runs only at
connect (`serial_handler.py:138`); the write path never flushes. A trailing
line from the SET can be read as the GET's answer — and the parsers accept
the set-echo wording, so the read-back would return *the value we commanded*.
That would silently turn this into optimistic publish wearing a disguise,
destroying the design's whole justification. Flush before every write.

**R3. Force-publish on the refresh path.** `_publish_delta` suppresses
unchanged values, so when the device *ignores* a write the read-back returns
the old value and publishes **nothing** — HA's optimistic toggle reverts and
the user sees the same spring-back. The one scenario used to justify the
read-back was the one it did not fix. The refresh path force-publishes.
`_publish_delta` also assigns its cache *after* the await; with two
publishers that guard is not atomic, so the assignment moves before it.

**R4. Per-window border switches are broken today, permanently.** Discovery
creates four `switch.multiviewer_window_{n}_border` for `border_scope ==
"window"` (`discovery.py:598-604`), the poller never publishes those topics,
and `GET_ALL_WINDOW_BORDERS` (`profiles.py:232`) is defined and never called.
On the basement UHD those four switches spring back forever. **Retracted in
the implementation review -- see S7: the read this would need has never been
verified against the UHD, so it is deliberately NOT fixed here.**

**R5. Preserve the fast/slow split** — extracted units take `slow`, the loop
keeps its gate. Traffic would otherwise roughly double.

**R6. Blocks that are not one-read-one-topic** must keep their shape: EDID
publishes to the select *or* the diagnostic topic depending on
`edid_options_verified`; border colours publish up to four topics from one
read; resolution publishes two. Silent drops (`pip_*` unmapped labels, layout
mode outside 1..2) must survive.

**R7. Connectivity gate** on `refresh()`, matching the sweep's early return,
so a refresh cannot publish settings while the device is off.

**R8. Fail loudly on a bad key.** A mistyped key would be swallowed by the
blanket `except` and silently degrade that entity to 6 s forever. Unknown key
raises; a test asserts every `refresh=` used in `controller.py` resolves; the
catch narrows to transport errors.

**R9. Characterization test first.** Five existing poller tests cover power
and the nudge; nothing pins the publish set. Snapshot every `(topic, value)`
for both profiles, fast and slow, *before* moving 26 blocks.

## Corrections to the original plan

- The `power` exclusion stands, but the stated reason was wrong: a power
  read-back is a **no-op** (the delta cache suppresses the unchanged
  pre-command value), not a spring-back.
- "One place, used by both paths" was false. Every REST router calls
  `handler.send_command` directly with the legacy `Commands` class and never
  touches the Controller or the profile. The claim is scoped to the MQTT path.
- The count is 26 refreshers, not 20.

## Rejected

- **Replace the read-back with optimistic publish** (reviewer's closing
  suggestion). With R3 the read-back reports what the device actually did;
  optimistic publish cannot, and the HDS's silently-ignored EDID writes are a
  live example. Keeping the round trip.
- **Drop `_force_slow` from the nudge** now that refreshers exist. Sweeps
  coalesce through one event, so the cost is bounded, and keeping it means a
  missing or mistyped refresher degrades to 6 s rather than 60 s. R8 makes
  that failure loud; this keeps it cheap.

---

# Revision after the implementation review

The review returned **DO NOT SHIP**, correctly.

**S1 (Critical, shipped regression). `what.split()` produced `layout:PBP:mode`.**
The PBP labels are capitalised; the layout table is not. `_resolve_refresh`
raised `ValueError`, which the narrowed `except (OSError, TimeoutError)` did
not catch, so `trigger_immediate_poll()` was skipped entirely — leaving PBP
mode and aspect confirming at **60 s**, the exact bug 0.6.5 fixed.
Reproduced before fixing. Now `what.lower().split()`, the catch is
`Exception`, and the nudge is in a `finally` so nothing the read-back does
can cancel the fallback.

**S2 (Critical). The test that should have caught S1 was tautological.**
It regexed `refresh=` literals out of the source and then substituted the
*placeholder names* (`{layout}` → `"quad"`), so the only layout key it ever
resolved was the one that worked. It asserted on a value it invented.
Replaced with a parametrised test that drives **every** setter on **both**
profiles for real and asserts the key resolves and the nudge fired.

**S3. The generation bump was in the wrong place — found while writing the
concurrency test, not by the review.** `trigger_immediate_poll()` ran in
`finally`, i.e. *after* the read-back published. A sweep sitting between its
own read and its publish has already passed its generation check, so its
stale value could still land on top. `refresh()` now bumps the generation at
entry, before publishing.

**S4. The heartbeat's power read bypassed the lock.**
`_check_power_state` called `_send_command_internal` directly while the
poller held the lock for a multi-line reply. Pre-existing, but the new flush
turned "sometimes garbled" into guaranteed data loss — and a truncated read
sets `UNAVAILABLE`, which triggers disconnect/reconnect churn on a live unit.
It now takes the lock. No reentrancy: the reconnect path runs on its own task.

**S5. The connectivity gate used a 30-second-stale cache.** `serial.state` is
written only by the heartbeat, so for up to `heartbeat_interval` after a
power-on every read-back published nothing — precisely when someone has just
switched the unit on. Gated on the live `is_connected` instead; a read
against a powered-off device returns None and publishes nothing anyway.

**S6. A superseded sweep now abandons** rather than issuing its remaining ~26
reads blind, which would contend with the very commands it was superseded by.

**S7. Per-window borders: dropped from this change.** `parse_window_borders`'
own docstring records that the UHD's reply format has never been captured,
and the test fixture was a fabrication that pinned the guess. The basement
unit was powered off when this was written — it answers `power off` to every
read — so it could not be verified. Shipping it would either publish nothing
or spend a serial timeout per sweep on a command the UHD may not answer. The
four switches stay stateless, as they are today, and the gap is recorded in
`refresh_window_border`. **Follow-up: capture `r window 0 border!` on the
powered-on UHD.**

**S8. The flush is a mitigation, not a fix**, and the comment now says so: a
segment still in flight arrives after it. The real fix is validating that a
reply matches the command issued, which needs the reply shapes captured first.

**S9. The EDID justification was overstated.** On the HDS
`edid_options_verified` is False, so the EDID *select* receives nothing on
either path — the read-back does not fix the entity the argument named. The
general point stands (a read-back reports what the device did); EDID is not
the demonstration.

Also: rollback is now conditional so a concurrent publisher's value is never
overwritten by a stale snapshot, and the dead `window_border:{n}` branch is
gone.

**Publish behaviour vs pre-refactor is now identical except one ordering
change**: `output/resolution/state` moves adjacent to the select topic. Same
topic, same value.
