# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-08-22

One new flag, `--diff`, and the CRLF bug that writing it exposed. The formatting
itself comes from `gilramir/gren-format-lib`, which this release pins at 1.0.1.

### Added

- **`--diff` / `-d`** — a dry run. Each changed file's unified diff goes to
  stdout, and no changes are written to disk. A file that is
  already formatted shows no diff, so a clean run prints nothing at all,
  and the exit status is 0 either way — only a real failure is nonzero. The
  header names a `.orig` original that does not exist, so the output pipes into
  `patch` and lands byte-identical to what the in-place run would have written.
  It combines with `--remove-unused-imports` and `--show-progress`, and cannot
  be combined with the single-file debug flags.
- A file that `--diff` would rewrite but whose line diff is empty — a CRLF-only
  change, say — now prints a `\ `-prefixed note instead of an empty hunk, rather
  than printing nothing for a file the very next in-place run rewrites.
- Under `--diff`, `--show-progress` reports each file as `would reformat` and
  sends its whole progress line to **stderr**, leaving stdout a clean patch.

### Fixed

- **The path-argument mode never normalized CRLF on disk.** `gren-format
  src/F.gren` on a CRLF-but-otherwise-formatted file saw its own LF output as
  unchanged and left the `\r`s there forever — while the no-argument project run
  rewrote those very same bytes. `readSource` now returns the raw text alongside
  the normalized one, and the project run, the path-argument run and `--diff`
  all answer "is this file changed?" through a single `isAlreadyFormatted`
  predicate.

### Changed

- Built against **`gilramir/gren-format-lib` 1.0.1** (was 1.0.0): `<|` and `|>`
  chain layouts are now stated rules, and several comment placements around them
  are fixed. See that package's changelog for the list.

## [1.0.0] - 2026-08-15

- First release, published to npm as `gren-format`. The standalone CLI: the
  in-place modes (a whole project, or named files and directories), the
  single-file debug flags (`--show`, `--lpt`, `--box`, the AST and context
  dumps, `--decisions`), `--remove-unused-imports` and `--show-progress`, built
  on `gilramir/gren-argparse` over the formatter in
  `gilramir/gren-format-lib` 1.0.0.
