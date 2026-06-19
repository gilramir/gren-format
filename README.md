# gren-format

Standalone CLI for formatting Gren source code.

## Usage

```
gren-format [flags] [file ...]
```

Format specific files in place:

```
gren-format src/Main.gren src/Util.gren
```

Format every source file in the project:

```
gren-format --all
```

Preview formatted output without writing:

```
gren-format --show src/Main.gren
```

Remove unused imports while formatting:

```
gren-format --remove-unused-imports --all
gren-format --remove-unused-imports src/Main.gren
gren-format --remove-unused-imports --show src/Main.gren
```

## Formatting pipeline

Every file goes through a format-and-verify pipeline before anything is
written to disk. The pipeline runs two full format passes and checks the
result at each stage to ensure correctness.

### Standard pipeline

```
source text
     │
     ▼
  [ parse ]
     │
     ├─ error → ParseFailure
     │
     ▼
 AST + Context  (ast1, ctx1)
     │
     ▼
  [ format ]  (AST → LPT → pretty-printer)
     │
     ├─ error → PrettyPrintFailure
     │
     ▼
 formatted text  (pretty1)
     │
     ▼
  [ reparse ]
     │
     ├─ error → CheckReparseFailed
     │
     ▼
 AST + Context  (ast2, ctx2)
     │
     ▼
  [ compare ASTs ]  ast1 == ast2?
     │
     ├─ mismatch → AstMismatchAfterFormat
     │
     ▼
  [ format again ]  (ast2 + ctx2)
     │
     ├─ error → PrettyPrintFailure
     │
     ▼
 formatted text  (pretty2)
     │
     ▼
  [ check idempotency ]  pretty1 == pretty2?
     │
     ├─ mismatch → NotIdempotent
     │
     ▼
  [ write to disk ]
```

The reparse + AST comparison step ensures the formatter never silently
changes the meaning of a program. The idempotency check ensures that
formatting twice produces the same result as formatting once — so a
file that has already been formatted is left unchanged on future runs.

### Pipeline with `--remove-unused-imports`

When `--remove-unused-imports` is passed, an AST transformation step is
inserted between parsing and the first format pass. The rest of the
pipeline is identical, but all comparisons are made against the
transformed AST rather than the original.

```
source text
     │
     ▼
  [ parse ]
     │
     ├─ error → ParseFailure
     │
     ▼
 AST + Context  (ast1, ctx1)
     │
     ▼
  [ remove unused imports ]
     │  · qualified imports with no qualified references → removed
     │  · explicit-expose imports with no used exposed names
     │    and no qualified references → removed
     │  · open-expose imports (exposing (..)) → always kept
     │  · comments inside a removed import → also removed
     │
     ▼
 AST + Context  (ast1', ctx1')   ← modified AST
     │
     ▼
  [ format ]
     │
     ├─ error → PrettyPrintFailure
     │
     ▼
 formatted text  (pretty1)
     │
     ▼
  [ reparse ]
     │
     ├─ error → CheckReparseFailed
     │
     ▼
 AST + Context  (ast2, ctx2)
     │
     ▼
  [ compare ASTs ]  ast1' == ast2?   ← compared against transformed AST
     │
     ├─ mismatch → AstMismatchAfterFormat
     │
     ▼
  [ format again ]  (ast2 + ctx2)
     │
     ├─ error → PrettyPrintFailure
     │
     ▼
 formatted text  (pretty2)
     │
     ▼
  [ check idempotency ]  pretty1 == pretty2?
     │
     ├─ mismatch → NotIdempotent
     │
     ▼
  [ write to disk ]
```

## Unused import analysis

The `--remove-unused-imports` pass scans the module body for three kinds
of reference:

- **Qualified references** — `Dict.get`, `Maybe.Just`, `List.Extra.member`.
  These carry the module name (or alias) directly in the AST node, so
  detection is exact.

- **Unqualified references** — bare names like `toUpper`, `Just`, `member`
  that come from an `exposing (...)` clause. These are detected
  conservatively: if the name appears anywhere in the module (even if
  shadowed by a local definition), the import is kept.

- **Operator references** — `+`, `|>`, `==`, etc., whether used inline
  (`a + b`) or as a value (`(+)`). These are matched against
  `ExposedOperator` entries in the expose list.

Open-expose imports (`exposing (..)`) are always kept because the pass
cannot know which names the imported module exports without resolving
the full module graph.

When an import is removed, any comments whose start line falls within
that import's source line range are removed with it. Comments elsewhere
(between imports, before or after the import block) are preserved.

## Debug flags

These flags operate on a single file and write to stdout instead of disk:

| Flag | Effect |
|---|---|
| `--show <file>` | Format and print result |
| `--pre-ast <file>` | Print parsed AST as JSON |
| `--post-ast <file>` | Format, verify ASTs match, print formatted AST as JSON |
| `--lpt <file>` | Print Logical Printing Tree as JSON |
| `--pex <file>` | Print PrettyExpressive Doc as JSON |

`--show` respects `--remove-unused-imports`. The other debug flags operate
on the raw AST and do not.
