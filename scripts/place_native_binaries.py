

import json
import glob
import os
import sys
import tarfile

BIFOLD = r"E:\bifold-wallet"
CACHE = r"E:\tools\native-cache"

# package name -> cached tarball
TARBALLS = {
    "@openwallet-foundation/askar-react-native": "askar.tar.gz",
    "@hyperledger/anoncreds-react-native": "anoncreds.tar.gz",
    "@hyperledger/indy-vdr-react-native": "indyvdr.tar.gz",
}


def targets():
    """Every installed copy of the three packages, with its expected version."""
    found = []
    for pkg, tarball in TARBALLS.items():
        pattern = os.path.join(BIFOLD, "**", "node_modules", *pkg.split("/"), "package.json")
        for pkg_json in glob.glob(pattern, recursive=True):
            data = json.load(open(pkg_json, encoding="utf-8"))
            binary = data.get("binary")
            if not binary:
                continue
            found.append(
                {
                    "package": pkg,
                    "tarball": os.path.join(CACHE, tarball),
                    "native_dir": os.path.join(os.path.dirname(pkg_json), "native"),
                    "version": binary["version"],
                }
            )
    return found


def place(entry):
    tarball, native_dir, version = entry["tarball"], entry["native_dir"], entry["version"]

    if not os.path.exists(tarball):
        return f"MISSING tarball {tarball}"

    os.makedirs(native_dir, exist_ok=True)

    # installBinary.js extracts with strip:1, so drop the leading path segment.
    with tarfile.open(tarball, "r:gz") as tf:
        members = []
        for m in tf.getmembers():
            parts = m.name.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue
            m.name = parts[1]
            members.append(m)
        tf.extractall(native_dir, members=members)

    # This is what makes `yarn install` skip the download next time.
    with open(os.path.join(native_dir, "version.json"), "w", encoding="utf-8") as f:
        json.dump({"version": version}, f)

    count = sum(len(files) for _, _, files in os.walk(native_dir))
    return f"ok ({count} files)"


def main():
    entries = targets()
    if not entries:
        sys.exit("No target packages found - did yarn install run?")

    print(f"Placing native binaries into {len(entries)} location(s)\n")
    failures = 0
    for entry in entries:
        rel = os.path.relpath(entry["native_dir"], BIFOLD)
        result = place(entry)
        if not result.startswith("ok"):
            failures += 1
        print(f"  [{result:>16}] {rel}")

    print()
    if failures:
        sys.exit(f"{failures} location(s) failed")
    print("All native binaries placed. Re-run `yarn install` to verify.")


if __name__ == "__main__":
    main()
