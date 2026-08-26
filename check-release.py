#!/usr/bin/env python3
"""Every pre-deployment check for an npm release of `gren-format`, in one gate.

`DEPLOY.md` walks the release by hand. This runs the *checking* half of it and
deliberately stops short of the three irreversible steps -- `git tag`,
`npm publish`, `git push --follow-tags` -- which stay yours to type. Nothing
here writes to the repo except `./app`, `src/Version.gren` and
`package-lock.json` -- the first two are what a normal `./build.sh` already
does, and R3/V6 fail if either of the latter two actually moves; the tarball is
packed into a temp dir and the tarball's own install goes to a temp prefix,
never `-g`.

Exit status is 0 only if every check passed. WARN and SKIP never fail the run.

Repo state
  R1  the working tree is clean -- the tag has to capture what gets published
  R2  the branch is `main` (warn only)
  R3  `src/Version.gren` as committed is what `build.sh` generates: a diff here
      means the committed file was stale and the tag would disagree with `--version`

Version coherence -- `package.json` is the single source of truth (DEPLOY.md)
  V1  `package.json` has a parseable `"version"`
  V2  `src/Version.gren` states that same version
  V3  `CHANGELOG.md` has a `## [<version>]` entry
  V4  no `<version>` git tag exists yet, locally or on `origin`
  V5  the npm registry does not already carry `<version>` -- npm refuses a
      re-publish, so each release needs a number it has not seen
  V6  `package-lock.json` is exactly what npm generates from `package.json`.
      This one *regenerates* it (offline: gren-format has no npm dependencies)
      and fails if the file moved, the same contract R3 has for `Version.gren`

Dependencies -- what is pinned is what gets compiled in
  D1  no `local:` pin in `gren.json`. Publishing on one would ship a CLI built
      against whatever happened to be in a working copy
  D2  every direct `gren.json` dependency is actually published on the Gren
      registry at the pinned version

Build and test
  B1  `./build.sh` succeeds
  B2  `./app --version` prints the `package.json` version -- the real proof
      that the generated `Version.gren` reached the binary
  B3  `devbox run test` passes (the 82 CLI integration tests)

Packaging -- test the tarball, never `npm link` (DEPLOY.md)
  P1  `npm pack` succeeds
  P2  the tarball holds exactly `app`, `package.json`, `README.md`, `LICENSE`
  P3  `app` carries its executable bit -- what makes `bin`/`npx` work
  P4  installing that tarball into a temp prefix yields a runnable
      `gren-format` whose `--version` matches
  P5  `npm publish --dry-run` accepts the manifest

Functional, all run through the binary unpacked from the tarball
  F1  `--show` is clean and a fixed point on every `tests/testfiles/**/
      *.formatted.gren` -- each is parse -> format -> reparse -> AST-compare ->
      reformat -> idempotency-compare
  F2  a no-arg project run lands every file on its own `--show` output and
      reports the right count
  F3  a second run reformats 0 and changes no bytes
  F4  `--diff` writes nothing, exits 0, names both changed files, renders a
      CRLF-only change as a `\\ ` note rather than an empty hunk, and says
      nothing at all once the project is formatted
  F5  the 1.1.0 regression: a named CRLF-but-otherwise-formatted file is
      rewritten. `gren-format src/F.gren` used to compare its LF output against
      the normalized text and leave the `\\r`s there forever
  F6  `--remove-unused-imports` strips an unused import

Publish readiness
  A1  `npm whoami` succeeds -- `npm publish` needs it
"""

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

EXPECTED_TARBALL = {
    "package/app",
    "package/package.json",
    "package/README.md",
    "package/LICENSE",
}
GREN_REGISTRY = "https://packages.gren-lang.org/package/{pkg}/version/{version}/overview"

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"
COLOR = {PASS: "\033[32m", FAIL: "\033[31;1m", WARN: "\033[33m", SKIP: "\033[90m"}
RESET = "\033[0m"


class Report:
    def __init__(self, verbose=False):
        self.rows = []
        self.verbose = verbose
        self.color = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    def add(self, label, status, title, detail=""):
        self.rows.append((label, status, title, detail))
        tag = f"{COLOR[status]}{status}{RESET}" if self.color else status
        print(f"  {tag}  {label:<3} {title}")
        if detail and (status != PASS or self.verbose):
            for line in str(detail).rstrip().splitlines()[:20]:
                print(f"             {line}")
        sys.stdout.flush()
        return status == PASS

    def ok(self, label, title, detail=""):
        return self.add(label, PASS, title, detail)

    def fail(self, label, title, detail=""):
        return self.add(label, FAIL, title, detail)

    def warn(self, label, title, detail=""):
        return self.add(label, WARN, title, detail)

    def skip(self, label, title, detail=""):
        return self.add(label, SKIP, title, detail)

    def of(self, status):
        return [r for r in self.rows if r[1] == status]


def section(title):
    print(f"\n\033[1m{title}\033[0m" if sys.stdout.isatty() else f"\n{title}")


def run(cmd, cwd=None, timeout=1800):
    """Run a command, capturing text output. Never raises on nonzero exit."""
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, timeout=timeout,
    )


def run_bytes(cmd, cwd=None, timeout=600):
    """Same, but keeps stdout as bytes -- line endings are the point here."""
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None,
        capture_output=True, timeout=timeout,
    )


def tail(proc, n=12):
    out = ((proc.stdout or "") + (proc.stderr or "")).rstrip()
    if isinstance(out, bytes):
        out = out.decode("utf-8", "replace")
    lines = out.splitlines()
    return "\n".join(lines[-n:])


def http_status(url, timeout=15):
    """200 / other / None when the network itself did not answer."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read(1)
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


# --------------------------------------------------------------------------
# repo state and version coherence
# --------------------------------------------------------------------------

VERSION_RE = re.compile(r'^version\s*=\s*"([^"]*)"', re.M)


def read_package_version():
    return json.loads((HERE / "package.json").read_text())["version"]


def read_version_gren():
    m = VERSION_RE.search((HERE / "src" / "Version.gren").read_text())
    return m.group(1) if m else None


def check_repo(rep, allow_dirty):
    section("Repo state")

    p = run(["git", "status", "--porcelain"], cwd=HERE)
    if p.returncode != 0:
        rep.fail("R1", "not a git repository?", tail(p))
    elif p.stdout.strip():
        if allow_dirty:
            rep.warn("R1", "working tree is dirty (--allow-dirty)", p.stdout)
        else:
            rep.fail(
                "R1",
                "working tree is dirty -- commit or stash before tagging",
                p.stdout,
            )
    else:
        rep.ok("R1", "working tree is clean")

    p = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=HERE)
    branch = p.stdout.strip()
    if branch == "main":
        rep.ok("R2", "on branch main")
    else:
        rep.warn("R2", f"on branch {branch!r}, not main")

    p = run(["git", "log", "--oneline", "@{u}..HEAD"], cwd=HERE)
    if p.returncode == 0 and p.stdout.strip():
        n = len(p.stdout.strip().splitlines())
        rep.ok("R2", f"{n} unpushed commit(s) -- `git push --follow-tags` sends them", p.stdout)


def check_version(rep, version):
    section(f"Version coherence ({version})")

    rep.ok("V1", f"package.json version is {version}")

    got = read_version_gren()
    if got is None:
        rep.fail("V2", "could not parse a version out of src/Version.gren")
    elif got != version:
        rep.fail(
            "V2",
            f"src/Version.gren says {got!r}, package.json says {version!r}",
            "build.sh regenerates it -- do not hand-edit; rebuild and commit.",
        )
    else:
        rep.ok("V2", f"src/Version.gren agrees ({got})")

    changelog = HERE / "CHANGELOG.md"
    if not changelog.exists():
        rep.warn("V3", "no CHANGELOG.md")
    elif f"## [{version}]" in changelog.read_text():
        rep.ok("V3", f"CHANGELOG.md has a [{version}] entry")
    else:
        rep.fail("V3", f"CHANGELOG.md has no `## [{version}]` entry")

    p = run(["git", "tag", "-l", version], cwd=HERE)
    if p.stdout.strip():
        rep.fail("V4", f"tag {version} already exists locally")
    else:
        p = run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{version}"], cwd=HERE, timeout=60)
        if p.returncode != 0:
            rep.skip("V4", "tag is free locally; could not reach origin to confirm", tail(p, 3))
        elif p.stdout.strip():
            rep.fail("V4", f"tag {version} already exists on origin")
        else:
            rep.ok("V4", f"tag {version} is free, locally and on origin")

    name = json.loads((HERE / "package.json").read_text())["name"]
    p = run(["npm", "view", name, "versions", "--json"], timeout=180)
    if p.returncode != 0 and "E404" in (p.stderr or ""):
        rep.ok("V5", f"{name} is not on the registry yet -- this is the first publish")
    elif p.returncode != 0:
        rep.skip("V5", "could not query the npm registry", tail(p, 4))
    else:
        try:
            published = json.loads(p.stdout)
        except json.JSONDecodeError:
            rep.skip("V5", "could not parse `npm view` output")
            return
        if isinstance(published, str):
            published = [published]
        if version in published:
            rep.fail(
                "V5",
                f"{name}@{version} is ALREADY published -- npm will refuse it",
                "Bump first: npm version <patch|minor|major> --no-git-tag-version",
            )
        else:
            rep.ok("V5", f"{version} is free on npm (registry has: {', '.join(published[-4:])})")


def check_lockfile(rep, version, offline):
    """V6 -- `package-lock.json` is what npm generates from `package.json`.

    Regenerating it is this script's one write to the repo beyond `./app` and
    `src/Version.gren`, and it carries R3's contract: if the file moved, the
    committed copy was stale, so the run FAILS and you commit the new one. R1
    has already sworn the tree was clean, and the tag has to capture what gets
    published.

    `npm version` updates the lock on its own, so the drift this catches is the
    hand-edit and the never-generated-since case. Nothing is fetched -- there
    are no npm dependencies -- so the regeneration is offline and ~100ms.
    """
    lock = HERE / "package-lock.json"
    before = lock.read_bytes() if lock.exists() else None

    if offline or shutil.which("npm") is None:
        why = "--offline" if offline else "npm not on PATH"
        if before is None:
            rep.fail("V6", f"no package-lock.json, and cannot generate one ({why})")
            return
        try:
            got = json.loads(before).get("version")
        except json.JSONDecodeError:
            got = None
        if got != version:
            rep.fail(
                "V6",
                f"package-lock.json says {got!r}, package.json says {version!r}",
                "Regenerate it with `npm install --package-lock-only` and commit it.",
            )
        else:
            rep.skip("V6", f"package-lock.json states {version}; not regenerated ({why})")
        return

    p = run(
        ["npm", "install", "--package-lock-only", "--ignore-scripts",
         "--no-audit", "--no-fund"],
        cwd=HERE, timeout=300,
    )
    after = lock.read_bytes() if lock.exists() else None
    if p.returncode != 0:
        rep.fail("V6", "could not regenerate package-lock.json", tail(p))
    elif after is None:
        rep.fail("V6", "`npm install --package-lock-only` produced no lock file", tail(p))
    elif before is None:
        rep.fail(
            "V6",
            "package-lock.json did not exist -- it has just been generated",
            "`git add package-lock.json`, commit, and re-run.",
        )
    elif after != before:
        rep.fail(
            "V6",
            "package-lock.json was stale -- it has just been regenerated",
            "It now matches package.json. Commit it, or the tag captures a lock"
            "\nfile that disagrees with the version being published.",
        )
    else:
        rep.ok("V6", f"package-lock.json is what npm generates ({version})")


def check_deps(rep, offline):
    section("Dependencies")

    gren_json = json.loads((HERE / "gren.json").read_text())
    deps = gren_json.get("dependencies", {})
    direct = deps.get("direct", {})
    every = {**direct, **deps.get("indirect", {})}

    local = {k: v for k, v in every.items() if str(v).startswith("local:")}
    if local:
        rep.fail(
            "D1",
            "gren.json carries a local: pin -- never publish on one",
            "\n".join(f"{k}: {v}" for k, v in local.items()),
        )
    else:
        rep.ok("D1", f"no local: pins ({len(every)} pinned dependencies)")

    if offline:
        rep.skip("D2", "skipping Gren registry check (--offline)")
        return

    unpublished, unknown = [], []
    for pkg, ver in sorted(direct.items()):
        status = http_status(GREN_REGISTRY.format(pkg=pkg, version=ver))
        if status is None:
            unknown.append(f"{pkg} {ver}")
        elif status != 200:
            unpublished.append(f"{pkg} {ver} (HTTP {status})")
    if unpublished:
        rep.fail(
            "D2",
            "a pinned dependency is not published at that version",
            "\n".join(unpublished)
            + "\nPublish it to the Gren registry first, then rebuild -- otherwise"
            "\nyou ship a CLI built against something nobody else can compile.",
        )
    elif unknown and len(unknown) == len(direct):
        rep.skip("D2", "could not reach the Gren registry", "\n".join(unknown))
    else:
        checked = len(direct) - len(unknown)
        rep.ok("D2", f"all {checked} direct dependencies are published at their pinned version")


# --------------------------------------------------------------------------
# build, test, package
# --------------------------------------------------------------------------

def check_build(rep, version, skip_tests):
    section("Build and test")

    before = (HERE / "src" / "Version.gren").read_text()
    p = run(["./build.sh"], cwd=HERE)
    if p.returncode != 0:
        rep.fail("B1", "./build.sh failed", tail(p))
        return False
    rep.ok("B1", "./build.sh succeeded")

    after = (HERE / "src" / "Version.gren").read_text()
    if before != after:
        rep.fail(
            "R3",
            "build.sh rewrote src/Version.gren -- the committed copy was stale",
            "It now matches package.json. Commit it, or the tag will disagree"
            "\nwith what the binary reports.",
        )
    else:
        rep.ok("R3", "committed src/Version.gren is what build.sh generates")

    p = run(["node", str(HERE / "app"), "--version"])
    got = (p.stdout or "").strip()
    if p.returncode != 0:
        rep.fail("B2", "./app --version failed", tail(p))
    elif got != version:
        rep.fail("B2", f"./app --version printed {got!r}, expected {version!r}")
    else:
        rep.ok("B2", f"./app --version prints {got}")

    if skip_tests:
        rep.skip("B3", "skipping the integration tests (--skip-tests)")
    elif shutil.which("devbox") is None:
        rep.skip("B3", "devbox not on PATH -- cannot run `devbox run test`")
    else:
        p = run(["devbox", "run", "test"], cwd=HERE)
        summary = ""
        for line in (p.stdout or "").splitlines():
            if "passed" in line or "failed" in line or line.startswith("Ran "):
                summary = line.strip()
        if p.returncode != 0:
            rep.fail("B3", "integration tests failed", tail(p, 25))
        else:
            rep.ok("B3", f"integration tests pass ({summary or 'ok'})")
    return True


def check_package(rep, version, workdir):
    """Pack, inspect, and install into a temp prefix. Returns the binary path."""
    section("Packaging")

    packdir = workdir / "pack"
    packdir.mkdir(parents=True, exist_ok=True)
    p = run(["npm", "pack", "--pack-destination", str(packdir)], cwd=HERE, timeout=600)
    if p.returncode != 0:
        rep.fail("P1", "npm pack failed", tail(p))
        return None
    tarballs = sorted(packdir.glob("*.tgz"))
    if not tarballs:
        rep.fail("P1", "npm pack produced no tarball", tail(p))
        return None
    tarball = tarballs[0]
    rep.ok("P1", f"npm pack -> {tarball.name}")

    with tarfile.open(tarball) as tf:
        members = {m.name: m for m in tf.getmembers() if m.isfile()}
    names = set(members)
    if names != EXPECTED_TARBALL:
        rep.fail(
            "P2",
            "tarball contents are not what DEPLOY.md expects",
            "unexpected: " + (", ".join(sorted(names - EXPECTED_TARBALL)) or "-")
            + "\nmissing:    " + (", ".join(sorted(EXPECTED_TARBALL - names)) or "-"),
        )
    else:
        rep.ok("P2", f"tarball holds exactly the {len(names)} expected files")

    app = members.get("package/app")
    if app is None:
        rep.fail("P3", "no package/app in the tarball")
    elif not app.mode & stat.S_IXUSR:
        rep.fail(
            "P3",
            f"package/app is not executable (mode {app.mode:o})",
            "build.sh chmod +x's it -- that is what makes `bin` and `npx` work.",
        )
    else:
        rep.ok("P3", f"package/app is executable (mode {app.mode:o})")

    prefix = workdir / "prefix"
    prefix.mkdir(parents=True, exist_ok=True)
    p = run(["npm", "install", "--prefix", str(prefix), str(tarball)], timeout=600)
    if p.returncode != 0:
        rep.fail("P4", "installing the tarball failed", tail(p))
        return None
    binary = prefix / "node_modules" / ".bin" / "gren-format"
    if not binary.exists():
        rep.fail("P4", "no gren-format in the installed .bin -- check package.json's `bin`")
        return None
    p = run([str(binary), "--version"])
    got = (p.stdout or "").strip()
    if p.returncode != 0 or got != version:
        rep.fail("P4", f"installed binary printed {got!r} (exit {p.returncode}), expected {version!r}", tail(p))
        return None
    rep.ok("P4", f"tarball installs and runs; --version prints {got}")

    p = run(["npm", "publish", "--dry-run", str(tarball)], cwd=HERE, timeout=600)
    if p.returncode != 0:
        rep.warn("P5", "npm publish --dry-run was refused", tail(p, 8))
    else:
        rep.ok("P5", "npm publish --dry-run accepts the manifest")

    return binary


# --------------------------------------------------------------------------
# functional checks, all through the binary that came out of the tarball
# --------------------------------------------------------------------------

GREN_JSON = """\
{
    "type": "application",
    "platform": "node",
    "source-directories": ["src"],
    "gren-version": "0.6.6",
    "dependencies": { "direct": { "gren-lang/core": "7.4.2" }, "indirect": {} }
}
"""

DIRTY = b"module Foo exposing (..)\n\n\nbar   =    1\n"
CRLF_CLEAN = b"module Baz exposing (..)\r\n\r\n\r\nbaz : Int\r\nbaz =\r\n    2\r\n"
UNUSED_IMPORT = b"module Qux exposing (..)\n\nimport Dict\n\n\nqux =\n    1\n"


def reported_count(stdout):
    m = re.search(r"(\d+) files? reformatted", stdout or "")
    return int(m.group(1)) if m else None


def snapshot(src):
    return {p.name: p.read_bytes() for p in sorted(src.glob("*.gren"))}


def check_fixtures(rep, binary):
    """F1 -- --show over the repo's own formatted fixtures."""
    fixtures = sorted((HERE / "tests" / "testfiles").rglob("*.formatted.gren"))
    if not fixtures:
        rep.skip("F1", "no *.formatted.gren fixtures found")
        return
    bad_exit, not_fixed = [], []
    for f in fixtures:
        p = run_bytes([str(binary), "--show", str(f)])
        if p.returncode != 0:
            bad_exit.append(f"{f.relative_to(HERE)}: exit {p.returncode}")
        elif p.stdout != f.read_bytes():
            not_fixed.append(str(f.relative_to(HERE)))
    if bad_exit:
        rep.fail("F1", f"--show failed on {len(bad_exit)}/{len(fixtures)} fixtures", "\n".join(bad_exit))
    elif not_fixed:
        rep.fail(
            "F1",
            f"--show is not a fixed point on {len(not_fixed)}/{len(fixtures)} fixtures",
            "\n".join(not_fixed),
        )
    else:
        rep.ok("F1", f"--show clean and a fixed point on all {len(fixtures)} fixtures")


def build_scratch(root):
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (root / "gren.json").write_text(GREN_JSON)
    (src / "Foo.gren").write_bytes(DIRTY)
    (src / "Baz.gren").write_bytes(CRLF_CLEAN)
    return src


def check_functional(rep, binary, workdir):
    section("Functional (from the installed tarball)")

    check_fixtures(rep, binary)

    # --- F4 first: --diff must not write, so it can precede the write modes ---
    root = workdir / "diff"
    src = build_scratch(root)
    before = snapshot(src)
    p = run([str(binary), "--diff"], cwd=root)
    after = snapshot(src)
    problems = []
    if p.returncode != 0:
        problems.append(f"exit {p.returncode} (expected 0, like `gofmt -d`)")
    if after != before:
        problems.append("--diff WROTE to disk; it must be a dry run")
    for name in ("Foo.gren", "Baz.gren"):
        if name not in (p.stdout or ""):
            problems.append(f"{name} is changed but absent from the diff")
    if "Only the line endings differ" not in (p.stdout or ""):
        problems.append("the CRLF-only file produced no `\\ ` note")
    if problems:
        rep.fail("F4", "--diff misbehaved", "\n".join(problems) + "\n--- output ---\n" + (p.stdout or ""))
    else:
        run([str(binary)], cwd=root)  # format it, then --diff must go quiet
        q = run([str(binary), "--diff"], cwd=root)
        if q.stdout.strip():
            rep.fail("F4", "--diff printed something for an already-formatted project", q.stdout)
        else:
            rep.ok("F4", "--diff is a silent, writeless dry run (and quiet once clean)")

    # --- F2/F3: the no-arg project run, against each file's own --show ---
    root = workdir / "project"
    src = build_scratch(root)
    expected = {}
    for f in sorted(src.glob("*.gren")):
        expected[f.name] = run_bytes([str(binary), "--show", str(f)]).stdout
    changed = sum(1 for n, b in snapshot(src).items() if b != expected[n])

    p = run([str(binary)], cwd=root)
    got = snapshot(src)
    if p.returncode != 0:
        rep.fail("F2", "the no-arg project run failed", tail(p))
    elif got != expected:
        diffs = [n for n in expected if got.get(n) != expected[n]]
        rep.fail(
            "F2",
            "a file on disk does not equal its own --show output",
            "\n".join(f"{n}: on disk {got.get(n)!r} vs --show {expected[n]!r}" for n in diffs),
        )
    elif reported_count(p.stdout) != changed:
        rep.fail("F2", f"reported {reported_count(p.stdout)} reformatted, expected {changed}", p.stdout)
    else:
        rep.ok("F2", f"no-arg run lands every file on its --show output ({changed} reformatted)")

    p = run([str(binary)], cwd=root)
    if reported_count(p.stdout) != 0:
        rep.fail("F3", "a second run reformatted something -- not a fixed point", p.stdout)
    elif snapshot(src) != got:
        rep.fail("F3", "a second run changed bytes on disk")
    else:
        rep.ok("F3", "a second run reformats 0 and changes nothing")

    # --- F5: the 1.1.0 regression, through the path-argument mode ---
    root = workdir / "patharg"
    src = build_scratch(root)
    target = src / "Baz.gren"
    target.write_bytes(CRLF_CLEAN)
    p = run([str(binary), str(target)], cwd=root)
    body = target.read_bytes()
    if p.returncode != 0:
        rep.fail("F5", "the path-argument run failed", tail(p))
    elif b"\r\n" in body:
        rep.fail(
            "F5",
            "REGRESSION: a named CRLF file kept its \\r's",
            "This is the bug 1.1.0 fixed -- readSource must hand formatFile the"
            "\nraw text as well as the normalized one.",
        )
    elif reported_count(p.stdout) != 1:
        rep.fail("F5", f"CRLF file rewritten but reported {reported_count(p.stdout)}", p.stdout)
    else:
        rep.ok("F5", "a named CRLF-but-formatted file is normalized (the 1.1.0 fix)")

    # --- F6: --remove-unused-imports ---
    root = workdir / "rui"
    src = build_scratch(root)
    qux = src / "Qux.gren"
    qux.write_bytes(UNUSED_IMPORT)
    p = run([str(binary), "--remove-unused-imports", str(qux)], cwd=root)
    body = qux.read_bytes()
    if p.returncode != 0:
        rep.fail("F6", "--remove-unused-imports failed", tail(p))
    elif b"import Dict" in body:
        rep.fail("F6", "the unused import was not removed", body.decode("utf-8", "replace"))
    else:
        rep.ok("F6", "--remove-unused-imports strips an unused import")


def check_auth(rep):
    section("Publish readiness")
    p = run(["npm", "whoami"], timeout=120)
    if p.returncode != 0:
        rep.fail(
            "A1",
            "not logged in to npm -- `npm publish` will be rejected",
            "Run `npm login` (it is interactive, so it cannot happen here).",
        )
    else:
        rep.ok("A1", f"logged in to npm as {p.stdout.strip()}")


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Run every pre-deployment check for an npm release of gren-format.",
        epilog="Checks only. It never tags, publishes, or pushes.",
    )
    ap.add_argument("--skip-tests", action="store_true", help="skip `devbox run test` (B3)")
    ap.add_argument("--skip-build", action="store_true", help="reuse the existing ./app (skips B1-B3, R3)")
    ap.add_argument("--allow-dirty", action="store_true", help="downgrade the dirty-tree failure to a warning")
    ap.add_argument("--offline", action="store_true", help="skip the Gren registry lookups (D2)")
    ap.add_argument("--keep", action="store_true", help="keep the temp tarball/prefix/scratch dirs")
    ap.add_argument("-v", "--verbose", action="store_true", help="show detail for passing checks too")
    args = ap.parse_args()

    rep = Report(verbose=args.verbose)

    try:
        version = read_package_version()
    except Exception as e:
        print(f"V1 FAIL: cannot read package.json's version: {e}", file=sys.stderr)
        return 2
    print(f"gren-format release checks -- version {version}")

    check_repo(rep, args.allow_dirty)
    check_version(rep, version)
    check_lockfile(rep, version, args.offline)
    check_deps(rep, args.offline)

    built = True
    if args.skip_build:
        section("Build and test")
        rep.skip("B1", "skipping the build (--skip-build); ./app may be stale")
    else:
        built = check_build(rep, version, args.skip_tests)

    workdir = Path(tempfile.mkdtemp(prefix="gren-format-release-"))
    try:
        binary = check_package(rep, version, workdir) if built else None
        if binary:
            check_functional(rep, binary, workdir)
        else:
            section("Functional (from the installed tarball)")
            rep.skip("F", "no installed binary to exercise")
        check_auth(rep)
    finally:
        if args.keep:
            print(f"\nkept: {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)

    failures, warnings, skipped = rep.of(FAIL), rep.of(WARN), rep.of(SKIP)
    section("Summary")
    print(f"  {len(rep.of(PASS))} passed, {len(failures)} failed, "
          f"{len(warnings)} warned, {len(skipped)} skipped")
    for label, _, title, _ in failures:
        print(f"  FAIL  {label}  {title}")

    if failures:
        print("\nNot ready to publish.")
        return 1

    print(f"""
Ready to publish {version}. The irreversible steps, yours to type:

  git tag {version}
  npm publish
  git push --follow-tags

Afterwards, check the rendered page at npmjs.com/package/gren-format: the
README's relative image links are not in the tarball and only resolve while
npm's rewrite against the `repository` field holds (see DEPLOY.md).""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
