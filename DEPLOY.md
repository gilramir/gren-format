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

This needs the sibling `../gren-format-lib` checkout: `gren.json` depends on it
as `"gilramir/gren-format-lib": "local:../gren-format-lib"`. That is a
*build*-time dependency only — the formatter is compiled into `app`, so nothing
about it reaches the published tarball. But it does mean `npm publish` cannot be
run from a bare clone of this repo alone, since `prepublishOnly` runs
`./build.sh`.

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

```bash
npm version <patch|minor|major> --no-git-tag-version   # bumps package.json only
./build.sh                        # regenerates src/Version.gren + rebuilds ./app
./app --version                   # sanity: matches the new package.json
git commit -am "Version $(node -p "require('./package.json').version")"
git tag "$(node -p "require('./package.json').version")"
npm publish                       # prepublishOnly rebuilds once more (a no-op now)
git push --follow-tags
```

`--no-git-tag-version` is deliberate: plain `npm version` tags immediately, which
would capture the *old* `src/Version.gren` — the regeneration only happens on the
next build. Bumping, building, then committing and tagging keeps the tagged tree
equal to what was published.

First publish only: `npm login`, and note the name `gren-format` was unclaimed
on the registry as of the initial release.
