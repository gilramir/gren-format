# CLAUDE.md — gren-format

Standalone `gren-format` CLI. A Gren **application** (`platform: node`) that wires the formatter library (`gren-format-lib`) and the argument parser (`gren-argparse`) together into an executable.

The formatter logic itself lives entirely in `../gren-format-lib/src/Formatter/`. This repo owns only the CLI surface: flag definitions, dispatch, project discovery, and error rendering.

## Build

```bash
# From this directory (gren-format/)
../gren.sh make Main --output=app
```

The built binary is `gren-format/app` (a Node.js script). Run it as:

```bash
node app --show MyFile.gren
node app --dangerous
```

Or via the parent helper which sets `GREN_BIN`:

```bash
# From the workspace root (gren-format/)
./gren-format/app --show MyFile.gren
```

## Source Layout

```
src/
  Main.gren                   — entry point: FormatFlags type, flag definitions, onCommand dispatch
  Terminal/
    Format.gren               — all format operations (showFile, checkFile, run, etc.) and Error type
    ProjectOutline.gren       — locate gren.json, read Outline, render project-discovery errors
    Report.gren               — Report type and terminal/JSON rendering
```

### `Main.gren`

Defines `FormatFlags` and registers every CLI flag via `Argparse.Parser`. The `onCommand` function dispatches on flags in priority order: single-file debug flags (`--show`, `--pre-ast`, `--post-ast`, `--lpt`, `--check`, `--pex`) take precedence; if none is set, `formatProject` runs the whole-project format.

`FormatFlags` fields:

| Field | Flag | Effect |
|---|---|---|
| `rename` | `--rename` | Write `<file>.gren.fmt` instead of overwriting |
| `all` | `--all` | Format all source files under src/, overwriting in place |
| `show` | `--show <path>` | Pretty-print one file to stdout |
| `preAst` | `--pre-ast <path>` | Print original AST as JSON |
| `postAst` | `--post-ast <path>` | Format, verify ASTs match, print formatted AST |
| `lpt` | `--lpt <path>` | Print Logical Printing Tree as JSON |
| `check` | `--check <path>` | Format and compare ASTs; prints Success or Failure |
| `pex` | `--pex <path>` | Print PrettyExpressive Doc as JSON |

Without `--all` or `--rename`, the default action prints a warning and exits — the same safety guard as `gren format`.

### `Terminal/Format.gren`

The `run` function is the whole-project path: finds source files via `Outline.findSourceFiles`, parses each, formats, re-parses to verify AST equivalence, then writes. All single-file debug operations follow the same parse → LPT → pretty pipeline but write to stdout instead.

`Error` variants cover every failure mode: `ParseFailure`, `PrettyPrintFailure`, `CheckReparseFailed`, `AstMismatchAfterFormat`, `OverwriteFailure`, `FmtWriteFailure`, `ShowReadFailure`, `NothingToFormat`, `FailedToFindSources`.

### `Terminal/ProjectOutline.gren`

Locates the project root (via `Compiler.Paths.projectRoot`), reads `gren.json` into an `Outline`, and renders the three ways that can fail (`ReadProjectOutlineNoProject`, `ReadProjectOutlineInvalidGrenJsonString`, `ReadProjectOutlineInvalidGrenJson`).

### `Terminal/Report.gren`

`Report` is either `Empty` or a titled error with an optional file path and a `PP.Document` body. `toString` renders to terminal (80-column, optional ANSI color) or JSON.

## Dependencies

All local (sibling directories):

- `gilramir/gren-argparse` (`../gren-argparse`) — `Argparse.Parser`, `Argparse.PrettyPrinter`, `Argparse.Program`
- `gilramir/gren-format-lib` (`../gren-format-lib`) — `Formatter.MakeLogical`, `Formatter.MakePretty`, `Formatter.LPTJson`, `Formatter.PExJson`
- `gren-lang/compiler-common` (`../compiler-common`) — AST types, parser, outline, paths
- `gren-lang/compiler-node` (`../compiler-node`) — `Compiler.Outline`, `Compiler.Paths`
