#!/usr/bin/env python3
"""
generate_versions_index.py – Build the per-device versions.json published
alongside manifest.json on Pages.

The panel's Firmware settings fetch two files per device:

    firmware/<slug>/manifest.json   – the current release (update check)
    firmware/<slug>/versions.json   – latest + previous releases (rollback)

We only ever published the manifest, so versions.json 404'd on every panel
(issue #55) and the "Previous firmware" panel had nothing to list.

This script assembles versions.json from the release manifests themselves,
so it is rebuilt from truth on every Pages deploy rather than accumulated as
release-time state.

Rollback floor — why old releases are skipped
---------------------------------------------
A release is only offered if its manifest's ota.path is an absolute release
asset URL. That is exactly the set of releases from v0.1.1 onward, and the
property matters twice over:

  * Before v0.1.1 the manifests used paths relative to the Pages firmware
    dir (`<slug>.ota.bin`). Pages no longer hosts the binaries — they are
    served from the release assets — so those paths 404 today.
  * v0.1.1 is also the release that shipped the enlarged http_request
    buffers (buffer_size_rx/tx 4096). Earlier firmware cannot follow the
    ~949-char redirect a release-asset download issues, so a panel rolled
    back below v0.1.1 could never OTA again and would need a USB reflash.

Skipping them is therefore both correctness and safety. The list starts at
one entry and grows to the five the UI supports as releases ship.

Usage:
    python3 community/scripts/generate_versions_index.py \\
        --assets-dir release-assets \\
        --tags community-v0.1.1-upstream.v2.6.3 community-v0.1.0-upstream.v2.6.3 \\
        --output-root community-pages/firmware
    python3 community/scripts/generate_versions_index.py --self-test

Manifests are read from <assets-dir>/<tag>/<slug>-manifest.json. --tags is
newest-first and authoritative: release order is never inferred by parsing
version strings, which carry an `-upstream.vX.Y.Z` suffix.
"""

import argparse
import json
import os
import re
import sys

# The UI lists at most the latest plus four previous versions; upstream's
# own published-firmware check rejects a longer list outright.
MAX_ENTRIES = 5

ABSOLUTE_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
MD5_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


def log(msg):
    print(f"[generate_versions_index] {msg}")


def manifest_path(assets_dir, tag, slug):
    return os.path.join(assets_dir, tag, f"{slug}-manifest.json")


def version_entry(manifest, slug):
    """
    Return the versions.json entry for ``manifest``, or None if the release
    must not be offered for rollback.

    Rejects anything the panel would choke on: the UI matches an entry by the
    basename of ota.path against "<slug>.ota.bin" and re-resolves the path
    against the versions.json URL, so a relative path from the Pages-hosted
    era would silently resolve to a 404 on our own domain.
    """
    if not isinstance(manifest, dict):
        return None
    version = str(manifest.get("version", "")).strip()
    if not version:
        return None

    builds = manifest.get("builds")
    if not isinstance(builds, list) or not builds:
        return None
    ota = builds[0].get("ota") if isinstance(builds[0], dict) else None
    if not isinstance(ota, dict):
        return None

    path = str(ota.get("path", "")).strip()
    # The rollback floor: only release-asset URLs, never a Pages-relative path.
    if not ABSOLUTE_URL_RE.match(path):
        return None
    if path.rsplit("/", 1)[-1] != f"{slug}.ota.bin":
        return None

    md5 = str(ota.get("md5", "")).strip()
    if not MD5_RE.fullmatch(md5):
        return None
    release_url = str(ota.get("release_url", "")).strip()
    if not release_url:
        return None

    return {
        "version": version,
        "release_url": release_url,
        "ota": {"path": path, "md5": md5},
    }


def build_index(slug, manifests):
    """
    Build the versions.json body for ``slug`` from ``manifests`` (newest
    first), or None if it must not be published.

    Returns None when the newest release is not itself offerable: the first
    entry has to be the version manifest.json advertises, so publishing a
    list headed by an older release would point the update UI at firmware
    behind the one it just told the user is available.
    """
    entries = []
    seen = set()
    for manifest in manifests:
        entry = version_entry(manifest, slug)
        if entry is None:
            # The newest release gates the whole file; older ones just drop out.
            if not entries:
                return None
            continue
        key = entry["version"].lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
        if len(entries) == MAX_ENTRIES:
            break

    if not entries:
        return None
    return {"device": slug, "versions": entries}


def load_manifests(assets_dir, tag, slug):
    """Read one release's manifest for ``slug``; None if absent or unparseable."""
    path = manifest_path(assets_dir, tag, slug)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log(f"WARNING: {path} is unreadable ({exc}) — skipping that release")
        return None


def generate(assets_dir, tags, slugs, output_root):
    """Write versions.json for every slug that has an offerable latest release."""
    written = []
    for slug in slugs:
        manifests = []
        for tag in tags:
            manifest = load_manifests(assets_dir, tag, slug)
            if manifest is not None:
                manifests.append(manifest)

        index = build_index(slug, manifests)
        if index is None:
            # Expected for a device whose latest release predates the switch
            # to release-asset URLs; the manifest still serves the update check.
            log(f"{slug}: no offerable release — versions.json not published")
            continue

        out_dir = os.path.join(output_root, slug)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "versions.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
            f.write("\n")
        versions = ", ".join(e["version"] for e in index["versions"])
        log(f"{slug}: wrote versions.json ({versions})")
        written.append(slug)
    return written


def self_test():
    import shutil
    import tempfile

    failures = []

    def manifest(slug, version, path, md5="0" * 32, release_url="https://x/y"):
        return {
            "name": "Device",
            "version": version,
            "home_assistant_domain": "esphome",
            "builds": [
                {
                    "chipFamily": "ESP32-S3",
                    "parts": [{"path": f"https://x/{slug}.factory.bin", "offset": 0}],
                    "ota": {"path": path, "md5": md5, "release_url": release_url},
                }
            ],
        }

    slug = "demo-panel"
    url = f"https://github.com/o/r/releases/download/t/{slug}.ota.bin"

    # A release-asset manifest is offerable and keeps its absolute path.
    entry = version_entry(manifest(slug, "v0.1.1-upstream.v2.6.3", url), slug)
    if not entry or entry["ota"]["path"] != url:
        failures.append(f"release-asset manifest not accepted: {entry}")

    # The rollback floor: pre-v0.1.1 manifests used a Pages-relative path.
    if version_entry(manifest(slug, "v0.1.0", f"{slug}.ota.bin"), slug) is not None:
        failures.append("relative ota path was accepted (rollback floor breached)")

    # The UI matches on the basename, so a URL for another device is useless.
    if version_entry(manifest(slug, "v0.1.1", "https://x/other.ota.bin"), slug):
        failures.append("ota path for a different slug was accepted")

    for bad in ({"md5": "nothex"}, {"release_url": ""}):
        if version_entry(manifest(slug, "v0.1.1", url, **bad), slug) is not None:
            failures.append(f"manifest with {bad} was accepted")

    # Newest first, capped, de-duplicated.
    many = [manifest(slug, f"v0.9.{i}", url) for i in range(9, 1, -1)]
    index = build_index(slug, many)
    if index["device"] != slug:
        failures.append(f"device field wrong: {index['device']}")
    if len(index["versions"]) != MAX_ENTRIES:
        failures.append(f"expected {MAX_ENTRIES} entries, got {len(index['versions'])}")
    if index["versions"][0]["version"] != "v0.9.9":
        failures.append("first entry is not the newest release")

    dupes = [manifest(slug, "v0.1.1", url), manifest(slug, "v0.1.1", url)]
    if len(build_index(slug, dupes)["versions"]) != 1:
        failures.append("duplicate versions were not collapsed")

    # An unofferable latest release suppresses the file entirely, rather than
    # publishing a list headed by something older than manifest.json.
    stale = [
        manifest(slug, "v0.1.0", f"{slug}.ota.bin"),
        manifest(slug, "v0.0.9", url),
    ]
    if build_index(slug, stale) is not None:
        failures.append("index published despite an unofferable latest release")
    if build_index(slug, []) is not None:
        failures.append("index published with no manifests at all")

    # End to end over a staged assets dir, including a device with no release.
    tmp = tempfile.mkdtemp(prefix="versions_index_test_")
    try:
        tags = ["tag-new", "tag-old"]
        for tag, version in zip(tags, ["v0.1.2", "v0.1.1"]):
            d = os.path.join(tmp, "assets", tag)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"{slug}-manifest.json"), "w") as f:
                json.dump(manifest(slug, version, url), f)

        out_root = os.path.join(tmp, "pages")
        written = generate(os.path.join(tmp, "assets"), tags, [slug, "absent"], out_root)
        if written != [slug]:
            failures.append(f"unexpected slugs written: {written}")
        with open(os.path.join(out_root, slug, "versions.json")) as f:
            written_index = json.load(f)
        if [e["version"] for e in written_index["versions"]] != ["v0.1.2", "v0.1.1"]:
            failures.append(f"staged order wrong: {written_index}")
        if os.path.exists(os.path.join(out_root, "absent")):
            failures.append("a dir was created for a device with no release")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        for msg in failures:
            print(f"[generate_versions_index] self-test: {msg}", file=sys.stderr)
        return 1
    print("[generate_versions_index] self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", help="dir holding <tag>/<slug>-manifest.json")
    parser.add_argument("--tags", nargs="*", default=[], help="release tags, newest first")
    parser.add_argument("--output-root", help="firmware dir to write <slug>/versions.json into")
    parser.add_argument(
        "--devices-json",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "devices.json"
        ),
        help="devices.json listing the slugs to publish",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    missing = [
        n
        for n, v in (
            ("--assets-dir", args.assets_dir),
            ("--tags", args.tags),
            ("--output-root", args.output_root),
        )
        if not v
    ]
    if missing:
        parser.error(f"missing required arguments: {', '.join(missing)}")

    with open(args.devices_json, encoding="utf-8") as f:
        slugs = json.load(f)["devices"]

    generate(args.assets_dir, args.tags, slugs, args.output_root)


if __name__ == "__main__":
    main()
