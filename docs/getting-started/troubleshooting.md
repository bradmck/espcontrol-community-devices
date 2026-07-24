---
title: Troubleshooting
description: "Common problems installing and building community EspControl firmware, and how to fix them."
---

# Troubleshooting

Common problems specific to **installing and building** community devices.
General panel usage — WiFi, Home Assistant, cards, display behaviour — is
identical to official EspControl, so those are covered in the
[upstream docs](https://jtenniswood.github.io/espcontrol/).

::: tip The browser installer avoids most of this
Flashing prebuilt firmware from your device page skips the ESPHome build
entirely, so most of the build/validation errors below simply can't happen
on that path. Reach for the manual ESPHome route only if you specifically
want to compile it yourself.
:::

## "… is an invalid option for …" when validating or compiling

Symptom — validating or compiling in the ESPHome builder fails immediately
with something like:

```
[priority] is an invalid option for [artwork_image]. Did you mean [setup_priority]?
```

**Cause.** ESPHome cached an older copy of an external component, so an
out-of-date component schema is checking newer config — the config uses an
option the cached component doesn't know about yet. It typically shows up when
a config has tracked a moving branch, or after an upstream version bump, and
it's a known ESPHome behaviour (external components aren't always re-fetched —
[esphome/issues#6299](https://github.com/esphome/issues/issues/6299)).

**Fix.**

1. **Easiest:** install with the **browser flasher** from your device page
   instead — it uses prebuilt firmware and never runs the ESPHome builder or
   its component cache.
2. **If you're building manually:** clear the cache so components re-fetch.
   Delete the `.esphome/` folder next to your config (or at least the
   `external_components/` and `packages/` folders inside it), then validate
   again.
3. **Use the snippet exactly as published** on your device page — it resolves
   the component from a pinned release, so the component and config stay in
   sync. Avoid pointing the config at a moving branch, which is what lets them
   drift apart.

When it still won't validate, the top of the output has a line like
`Cloning https://github.com/jtenniswood/espcontrol@v2.6.3` — that tells you
which version actually got pulled, which is the fastest way to spot a
mismatch.

## "Wrong firmware source" / a warning about your panel

Firmware on this site is **only** for the community devices in the sidebar.
Official panels are never published here and must not be flashed with
community firmware — if your panel is on the
[upstream supported list](https://jtenniswood.github.io/espcontrol/), use the
[upstream installer](https://jtenniswood.github.io/espcontrol/getting-started/install)
instead.

## A device won't build, or its status shows "Broken"

Device pages show a status: **Working** (hardware-verified), **Untested**
(compiles, awaiting verification), or **Broken**. A nightly job compiles every
device and flips a device to **Broken** if it stops building — usually after
an upstream change. If a device is Broken, that's known and tracked; check the
[open issues](https://github.com/lamiskin/espcontrol-community-devices/issues)
for it before filing a new one.

## WiFi, Home Assistant, cards, and general use

Anything past flashing works exactly like official EspControl and is
documented upstream:

- [Install walkthrough](https://jtenniswood.github.io/espcontrol/getting-started/install) (from the WiFi step)
- [Enable Home Assistant actions](https://jtenniswood.github.io/espcontrol/getting-started/home-assistant-actions)
- [Configure cards and pages](https://jtenniswood.github.io/espcontrol/features/setup)

## Still stuck?

Open an issue on the
[community tracker](https://github.com/lamiskin/espcontrol-community-devices/issues).
Please include your **device**, your **ESPHome version**, and the **full
validate/compile log** — especially any `Cloning …@…` lines, which show which
component versions were pulled.
