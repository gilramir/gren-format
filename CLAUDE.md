# CLAUDE.md — gren-format

Standalone `gren-format` CLI. A Gren **application** (`platform: node`) that wires the formatter library (`gren-format-lib`) and the argument parser (`gren-argparse`) together into an executable.

The formatter logic itself lives entirely in `../gren-format-lib/src/Formatter/`. This repo owns only the CLI surface: flag definitions, dispatch, project discovery, the whole-file read/parse/verify pipeline, the `--remove-unused-imports` transform, and error rendering.

## Build

No top-level `gren.sh` wrapper anymore — build via **devbox** (`devbox.json`
pins a `gren@0.6` package resolving to a version-compatible published Gren
compiler):

```bash
# From this directory (gren-format/)
./build.sh          # wraps `devbox run build` (== `gren make Main`)
```

The built binary is `gren-format/app` (a Node.js script, executable directly
via its shebang). Run it as:

```bash
node app --show MyFile.gren
./app                          # format the whole project in place
```

## Source Layout

```
src/
  Main.gren                    — entry point: FormatFlags type, flag definitions, onCommand dispatch
  Format.gren                  — all format operations + the Error type and its pipeline
  RemoveUnusedImports.gren     — the --remove-unused-imports AST/comment transform
  ShiftPositions.gren          — row-renumbering traversal used by RemoveUnusedImports
  Terminal/
    ProjectOutline.gren        — locate gren.json, read the Outline, render discovery errors
```

`Report` and its pretty-printer are **not** in this repo — they come from
`gren-lang/compiler-node` (`Cli.Report`, `Cli.PrettyPrinter`).

### `Main.gren`

Defines `FormatFlags` and registers every CLI flag via `Argparse.Parser`, on top
of `Argparse.Program.runRootWithContext` (rootless — invoked directly as
`gren-format [flags] [paths]`, no command word). `onCommand` dispatches in this
order:

1. **Positional path args present** → format those files/directories in place
   (`Format.formatPaths`). Combining path args with any flag is an error.
2. **A single-file debug flag set** → run it (priority order below). The flags
   are folded to the first one set via a `Maybe (Task …)` list.
3. **Neither** → `formatProject` formats every source file in the project in
   place (needs a `gren.json` in the cwd or a parent).

`FormatFlags` fields:

| Field | Flag | Effect |
|---|---|---|
| `files` | *(positional)* | Files/directories to format in place |
| `removeUnusedImports` | `--remove-unused-imports` | Also strip unused imports while formatting |
| `show` | `--show <path>` | Parse + pretty-print one file to stdout (no write) |
| `preAst` | `--pre-ast <path>` | Print the original AST + parse context as JSON |
| `preContext` | `--pre-context <path>` | Print just the original parse `Context` (comment/whitespace stream) as JSON |
| `postAst` | `--post-ast <path>` | Format, verify ASTs match, print the formatted AST as JSON |
| `lpt` | `--lpt <path>` | Print the Logical Printing Tree as JSON |
| `renderDoc` | `--render-doc <path>` | Print the `Formatter.Render.Doc` tree as JSON |

### `Format.gren`

The `run` function is the whole-project path: finds source files via
`Outline.findSourceFiles`, then formats and atomically overwrites each changed
file. `formatPaths` does the same for explicit path arguments. All operations
share two helpers — `readSource` (read + UTF-8 decode) and `parseModule` (parse
to AST + parse context, taking the error constructor) — and the format core:

- `formatAndVerify` — parse → *(optionally remove unused imports)* → render →
  reparse → AST-compare → render again → idempotency-compare. Returns the
  canonical string, or an `Error` if any check fails.
- `renderModule` — build the LPT (`makeLogicalPrintingTree`) and render it
  (`makePrettyResult`), shared by `formatAndVerify` and `postAstFile`.

`Error` variants: `FailedToFindSources`, `NothingToFormat`, `ParseFailure`,
`PrettyPrintFailure`, `OverwriteFailure`, `ShowReadFailure`, `CheckReparseFailed`,
`AstMismatchAfterFormat`, `NotIdempotent`. `prettifyError` renders each to a
`Cli.Report.Report`.

### `RemoveUnusedImports.gren`

`removeUnusedImports` drops imports nothing in the module body references
(conservatively — `exposing (..)` and `Type(..)` are always kept), trims
individually-unused names out of a kept import's exposing list, removes comments
that lived inside a removed import, and leaves a `-- removed import Foo`
placeholder for a leading comment that would otherwise be orphaned. Removing rows
means renumbering everything after them → `ShiftPositions`.

### `ShiftPositions.gren`

A full, from-scratch traversal that adds a constant row delta to every source
position in a module's declarations — one function per `Compiler.Ast.Source`
type, mirroring `RemoveUnusedImports`'s `refsFrom*` family. Deliberately skips
`.name`/`.exports`/`.docs`/`.imports` and a `Manager`-kind `effects` (see its doc
comments for why).

### `Terminal/ProjectOutline.gren`

Locates the project root (`Compiler.Paths.projectRoot`), reads `gren.json` into
an `Outline`, and renders the three ways that can fail
(`ReadProjectOutlineNoProject`, `ReadProjectOutlineInvalidGrenJsonString`,
`ReadProjectOutlineInvalidGrenJson`).

## Tests

CLI integration tests live in `tests/` and are written in **Gren** on top of
`gilramir/gren-unit-node` (an xUnit-style runner). The test app shells out to the
built `../app` binary and asserts on its exit code, stdout/stderr, JSON output,
and in-place file edits — 30 tests across suites `NoArgs`, `ShowFlag`,
`JsonFlags`, `Positional`, `NoArgsFormat`, `RemoveUnusedImportsFlag`.

```bash
# From this directory (gren-format/)
devbox run test                # builds ./app and the test app, runs all 30

# Or from tests/ (rebuilds ../app first, then passes args through to the app):
cd tests && ./run-tests.sh
```

## Dependencies

All local siblings except the published Gren packages:

- `gilramir/gren-argparse` (`../gren-argparse`) — `Argparse.Parser`, `Argparse.PrettyPrinter`, `Argparse.Program`
- `gilramir/gren-format-lib` (`local:../gren-format-lib`) — `Formatter.Logical.MakeLogical`, `Formatter.Render.MakeRender` (`makePrettyResult`, `lptToRenderDocJson`), `Formatter.Logical.LPTJson`, plus the AST-comparison / JSON-encoder modules `Compiler.Ast.Compare`, `Compiler.Ast.Source.Json`, `Compiler.Parse.Context.Json`
- `gilramir/gren-diff` — the unified diff shown by the `NotIdempotent` error
- `gren-lang/compiler-common` — AST types, parser, outline, paths
- `gren-lang/compiler-node` — `Compiler.Outline`, `Compiler.Paths`, `Cli.Report`, `Cli.PrettyPrinter`
