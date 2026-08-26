# Deploying `gren-format` to npm

The built `app` is a single self-contained `#!/usr/bin/env node` script — pure
compiled Gren, no sibling JS and no runtime dependencies. `package.json` exposes
it as the `gren-format` command via `"bin"`, and `"files"` restricts the
published contents to `app` alone (npm always adds `README.md`, `LICENSE`, and
`package.json` itself). `build.sh` `chmod +x`'s it, which is what makes it usable
as a `bin` target and what makes `npx gren-format` work.

Once published, users get it either way:

```bash
npm install -g gren-format   # then: gren-format [flags] [file ...]
npx gren-format --show Foo.gren
```

The README ships too, and it carries three relative image links (the logo and
the two pipeline diagrams under `docs/`). Those files are *not* in the tarball —
npmjs.com rewrites relative links in a README against the `repository` field, so
the images resolve to GitHub. That only holds while the `repository` URL is
accurate and the images are committed on the default branch; check the rendered
package page after the first publish, and switch the three links to absolute
`https://raw.githubusercontent.com/...` URLs if they come up broken.

## Version

`package.json`'s `"version"` is the single source of truth, and
`npm version <patch|minor|major>` is the only thing that bumps it. Nothing else
needs editing:

- `build.sh` generates `src/Version.gren` from `package.json` before every build
- `Main.gren` passes `Version.version` to the CLI, so `gren-format --version`
  prints whatever `package.json` says
- `npm version` rewrites `package-lock.json`'s copy of the number too, and
  `check-release.py`'s V6 regenerates the lock and fails if it moved -- so a
  stale one cannot reach the tag. (It never reaches the tarball: npm always
  excludes it, and `files` is `["app"]` anyway.)

So a forgotten bump is not possible — there is no second string to forget. Do
**not** hand-edit `src/Version.gren`; the next build overwrites it. It is
committed (not ignored) only so a fresh clone compiles with a plain
`gren make Main`, and `build.sh` rewrites it only when the version actually
changed, so an unchanged build doesn't force a recompile.

`gren package bump` is not usable here and never will be: `gren-format` is a
Gren *application*, and bump refuses those outright ("CANNOT BUMP APPLICATIONS
— this project is defined as an application, so there is no version number to
bump"). It only works on packages, where it diffs the local API against the
published one. The sibling `gren-format-lib` *is* a package, so its `gren.json`
version is bumped that way — but that is the library's version, independent of
this CLI's npm version.

## Build

```bash
./build.sh   # devbox run build; produces ./app, chmod +x'd
```

`gren.json` depends on the formatter as a *published* package —
`"gilramir/gren-format-lib": "1.0.0"` — not as a `local:../gren-format-lib`
checkout, so a bare clone of this repo builds on its own and `npm publish` (whose
`prepublishOnly` runs `./build.sh`) works without any sibling directory. It is a
build-time dependency either way: the formatter is compiled into `app`, so
nothing about it reaches the published tarball.

The tradeoff is that the version pinned there is what actually gets compiled in.
If you are releasing CLI changes that depend on unreleased formatter work, the
library has to be published to the Gren registry and the pin bumped here *first*
— otherwise you ship a CLI built against the older formatter without noticing.
Switching the pin back to `local:../gren-format-lib` while developing is fine,
but never publish on a `local:` pin: the tarball would then depend on whatever
happened to be in your working copy.

## Test the packaged tarball locally

Always test from the actual tarball, not `npm link` — `npm link` symlinks your
working directory straight into the global `node_modules`, which won't catch
packaging bugs like a missing `"files"` entry or an `app` that never got its
executable bit.

```bash
npm pack                                # packs exactly what `npm publish` would ship
                                        # -> gren-format-<version>.tgz
tar tzf gren-format-<version>.tgz       # expect: app, package.json, README.md, LICENSE
npm install -g ./gren-format-<version>.tgz
gren-format --version                   # now on PATH; should match package.json
```

Then exercise the modes that matter, in a scratch copy of a real project (the
in-place modes write files — do not run them on a tree you care about):

```bash
gren-format --show SomeFile.gren > /dev/null && echo clean   # parse/format/AST/idempotency checks
cd /tmp/scratch-project && gren-format                       # no-arg project run, writes in place
gren-format src/                                             # positional path
gren-format --remove-unused-imports
```

`--show` is the strongest single check: it parses, formats, reparses,
AST-compares, and reformats to confirm idempotency, so a zero exit status means
the packaged binary is doing the real work.

Also confirm `npx` resolves it, since that is the other advertised entry point:

```bash
npm uninstall -g gren-format            # make sure the global copy isn't what answers
npx ./gren-format-<version>.tgz --version
```

When done testing:

```bash
npm uninstall -g gren-format
```

## Publish

Every release *after* the first:

```bash
npm version <patch|minor|major> --no-git-tag-version   # bumps package.json only
./build.sh                        # regenerates src/Version.gren + rebuilds ./app
./app --version                   # sanity: matches the new package.json
V="$(node -p "require('./package.json').version")"
git commit -am "Version $V"
git tag -a "$V" -m "$V"           # -a is load-bearing; see below
npm publish                       # prepublishOnly rebuilds once more (a no-op now)
git push --follow-tags
```

`git tag -a` is not cosmetic. **`--follow-tags` pushes only *annotated* tags** —
a plain `git tag $V` makes a *lightweight* one, which `--follow-tags` skips
without a word, so the branch goes up and the release tag silently stays local.
That is how 1.0.0 through 1.2.0 came to be tagged lightweight here; they were
pushed after the fact.

The other way round is worse, so do not reach for it: `--tags` *replaces* the
default refspec rather than adding to it, so `git push --follow-tags --tags`
pushes the tag and **not the commits** — a tag on origin naming a commit nobody
else has. If you ever do want `--tags`, the branch has to be named explicitly
(`git push origin main --tags`), and it sends every local tag.

`--no-git-tag-version` is deliberate: plain `npm version` tags immediately, which
would capture the *old* `src/Version.gren` — the regeneration only happens on the
next build. Bumping, building, then committing and tagging keeps the tagged tree
equal to what was published.

The bump comes first because npm rejects a re-publish of a version already on the
registry, so each release needs a number it has not seen.

**First publish only.** Skip the `npm version` step entirely: `package.json`
already says `1.0.0` and that is the version to ship, so bumping would publish
`1.0.1` and burn `1.0.0` for nothing. Run `npm login` first if `npm whoami`
does not already print your account, then:

```bash
./build.sh                        # regenerates src/Version.gren + rebuilds ./app
./app --version                   # sanity: 1.0.0
git tag -a 1.0.0 -m 1.0.0
npm publish
git push --follow-tags
```

The name `gren-format` was unclaimed on the registry as of the initial release.
