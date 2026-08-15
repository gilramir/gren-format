# gren-format internals

The CLI surface of `gren-format`: flag definitions, dispatch, project discovery,
the read/parse/verify pipeline, the `--remove-unused-imports` transform, and
error rendering. The formatting itself lives in
[`gren-format-lib`](../../gren-format-lib/).

```
src/
  Main.gren                    — entry point: FormatFlags, flag definitions, onCommand dispatch
  Format.gren                  — all format operations + the Error type and its pipeline
  RemoveUnusedImports.gren     — the --remove-unused-imports AST/comment transform
  ShiftPositions.gren          — row-renumbering traversal used by RemoveUnusedImports
  Terminal/
    ProjectOutline.gren        — locate gren.json, read the Outline, render discovery errors
```

`Report` and its pretty-printer are **not** in this repo — they come from
`gren-lang/compiler-node` (`Cli.Report`, `Cli.PrettyPrinter`).

## `Main.gren`

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
| `showProgress` | `--show-progress` | Print each file's path before formatting it, and its outcome on the same line (in-place modes only) |
| `show` | `--show <path>` | Parse + pretty-print one file to stdout (no write) |
| `preAst` | `--pre-ast <path>` | Print the original AST + parse context as JSON |
| `preContext` | `--pre-context <path>` | Print just the original parse `Context` (comments) as JSON |
| `postAst` | `--post-ast <path>` | Format, verify ASTs match, print the formatted AST as JSON |
| `postContext` | `--post-context <path>` | Format, verify ASTs match, print just the formatted file's parse `Context` as JSON |
| `lpt` | `--lpt <path>` | Print the Logical Printing Tree as JSON |
| `box` | `--box <path>` | Print the `Box` render tree as JSON |
| `auditPredicates` | `--audit-predicates <path>` | Print, as JSON, every layout predicate claiming a hard break the renderer does not emit (see `gren-format-lib/tests/audit-predicates.py`) |
| `decisions` | `--decisions <path>` | Format the file twice and print, as JSON, which layout *decisions* differed between the passes (see `gren-format-lib/tests/check-decision-stability.py`) |

## `Format.gren`

The `run` function is the whole-project path: finds source files via
`Outline.findSourceFiles`, then formats and atomically overwrites each changed
file. `formatPaths` does the same for explicit path arguments. All operations
share two helpers — `readSource` (read + UTF-8 decode) and `parseModule` (parse
to AST + parse context, taking the error constructor) — and the format core:

- `formatAndVerify` — parse → *(optionally remove unused imports)* → render →
  reparse → AST-compare → render again → idempotency-compare. Returns the
  canonical string, or an `Error` if any check fails.
- `renderModule` — build the LPT (`makeLogicalPrintingTree`) and render it
  (`renderRoot`), shared by `formatAndVerify` and `postAstFile`.

`Error` variants: `FailedToFindSources`, `NothingToFormat`, `ParseFailure`,
`PrettyPrintFailure`, `OverwriteFailure`, `ShowReadFailure`, `CheckReparseFailed`,
`AstMismatchAfterFormat`, `NotIdempotent`. `prettifyError` renders each to a
`Cli.Report.Report`.

### Progress reporting

`Progress` is a `Maybe (Stream.Writable Bytes)` on both in-place entry points —
`Nothing` (quiet) unless `--show-progress` passes stdout in. `withProgress`
wraps one file's task between the two halves of its line: `progressStart`
writes `<path> ... ` with **no newline** before the file is read, so the name is
on screen for as long as the formatter is working on it, and `progressEnd`
closes the line with the outcome (`rewriteOutcome` for a file that finished,
`errorOutcome` for one that did not — `parse error`, `format error`, `read
error`, `write error`). The error path closes the line before re-failing, so a
run that stops on a bad file does not leave that file's name dangling.

A progress run also drops the list of rewritten paths that normally precedes
`run`'s summary line: every one of those paths has already been printed next to
what happened to it.

## `RemoveUnusedImports.gren`

`removeUnusedImports` drops imports nothing in the module body references
(conservatively — `exposing (..)` and `Type(..)` are always kept), trims
individually-unused names out of a kept import's exposing list, removes comments
that lived inside a removed import, and leaves a `-- removed import Foo`
placeholder for a leading comment that would otherwise be orphaned. Removing rows
means renumbering everything after them → `ShiftPositions`.

Four rules exist because emptying or collapsing the import block changes what
the *parser* will make of what is left (found by `gen-random.py`'s
remove-unused-imports oracle, 2026-08-10):

- `docShield` — the module's docs slot is parsed BEFORE its imports, so a
  `{-| ... -}` above the first declaration is that declaration's doc only
  because an import stands between it and the header. Remove the last import
  and the same comment reparses as the MODULE's doc. When that would happen,
  the docs slot is handed a `{-| removed import Foo -}` of its own. No output
  spelling avoids it — the parser skips ordinary comments while looking for
  the slot, so the `-- removed import Foo` placeholder does not shield it.
- `gluedLeadStartRow` — the range also runs BACKWARDS through a comment glued
  to the `import` keyword. A one-row `{- a -} import Foo` was always inside the
  range; the two-row form was not, so the same `LeadsInline` comment survived
  or died on span length alone, and a survivor came to rest above a different
  import. An own-line run above the glued lead still survives, and
  `hasLeadingRun` is measured against the glued lead's first row so that run
  still gets its placeholder.
- `trailingChainEndRow` — a removed import's range runs to the end of its
  trailing comment CHAIN, not just its own last row. A comment on the row the
  previous trailing comment closes on is another link written about the same
  import; left behind, it lands directly above the next import and becomes its
  lead. A comment a row further down is not a link and is left alone.
- `chargeOverlappingComments` — a cut does not free a row a surviving comment
  is still standing on. **Believed unreachable since `gluedLeadStartRow`
  landed**: the only comment that could start before an import and end inside
  its rows is a glued lead, which is now removed with it, so nothing survives
  to overlap. Kept as the guard for the invariant those two range rules have
  to maintain, not as live behaviour. A block comment glued in front of an
  import opens on an earlier row and closes on the import's own; freeing that
  row shifted the next comment up into the middle of it, and the two came out
  in the wrong order.

## `ShiftPositions.gren`

A full, from-scratch traversal that adds a constant row delta to every source
position in a module's declarations — one function per `Compiler.Ast.Source`
type, mirroring `RemoveUnusedImports`'s `refsFrom*` family. Deliberately skips
`.name`/`.exports`/`.docs`/`.imports` and a `Manager`-kind `effects` (see its doc
comments for why).

## `Terminal/ProjectOutline.gren`

Locates the project root (`Compiler.Paths.projectRoot`), reads `gren.json` into
an `Outline`, and renders the three ways that can fail
(`ReadProjectOutlineNoProject`, `ReadProjectOutlineInvalidGrenJsonString`,
`ReadProjectOutlineInvalidGrenJson`).

## Dependencies

All local siblings except the published Gren packages:

- `gilramir/gren-argparse` (`../gren-argparse`) — `Argparse.Parser`,
  `Argparse.PrettyPrinter`, `Argparse.Program`
- `gilramir/gren-format-lib` (`local:../gren-format-lib`) — the formatter
  (`Formatter.Logical.MakeLogical`, `Formatter.Render`, `Formatter.Logical.LPTJson`)
  plus `Compiler.Ast.Compare`, `Compiler.Ast.Source.Json`,
  `Compiler.Parse.Context.Json`
- `gilramir/gren-diff` — the unified diff shown by the `NotIdempotent` error
- `gren-lang/compiler-common` — AST types, parser, outline, paths
- `gren-lang/compiler-node` — `Compiler.Outline`, `Compiler.Paths`, `Cli.Report`,
  `Cli.PrettyPrinter`
