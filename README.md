![gren-format logo](docs/gren-format-logo.png)

# gren-format

`gren-format` is a code formatter for the [Gren](https://gren-lang.org)
programming language. It rewrites Gren source files into a canonical style, so
code looks the same no matter who wrote it. Importantly, the formatter also
honors the author's choice of line breaks: if the author chose a single-line version
of an expression, it stays as a single line, but if it's broken up across
multiple lines, it takes on a canonical multi-line format.
Following the philosphy of [elf-format](https://github.com/avh4/elm-format)
and the [Elm Style Guide](https://elm-lang.org/docs/style-guide),
the format is in a style that helps diffs stay focused on real
changes. `gren-format`'s output is very similar to that of `elm-format`, but
not identical.

This README documents the usage of the tool.  The actual formatting rules
are documented in the
[Gren Formatter Library](https://github.com/gilramir/gren-format-lib), the code
which does the actual formatting and can be used in other Gren programs.

The formatter is super careful when changing your code.
* It re-parses its output to ensure it didn't change the meaning of your code.
* It re-formats its output to ensure its own formatting is idempotent,
  guarding against diffs for no reason.

If either check fails, it reports a bug to the user instead of overwriting the file.

## A formatted example

One function, showing several rules at once: a `let` with multiple bindings,
a pipeline, a binary-operator chain that breaks at its loosest operators, an
`if`, a `when`, and a record update. (`order` is a record with `isMember`,
`hasCoupon`, `status`, and `total` fields; `Status` is a custom type that
includes `Cancelled`.)

```gren
summarize : Order -> Array Float -> Order
summarize order prices =
    let
        subtotal =
            prices
                |> Array.keepIf (\price -> price > 0)
                |> Array.foldl (+) 0

        eligible =
            order.isMember && subtotal > 100
                || order.hasCoupon && order.status /= Cancelled

        discount =
            if eligible then
                subtotal * 0.1

            else
                0
    in
    when order.status is
        Cancelled ->
            { order | total = 0 }

        _ ->
            { order
                | total = subtotal - discount
                , hasCoupon = False
            }
```

A few things worth noticing:

- `subtotal` is a pipeline: each `|>` step lands on its own line, indented +4
  from `prices` (see [Pipelines](https://github.com/gilramir/gren-format-lib/blob/main/docs/formatterRules.md#pipelines)).
- `eligible` is a binop chain the author wrote across two rows. `||` is the
  loosest operator here, so it's the only one that breaks; `&&` and `/=` bind
  tighter and stay glued to their operands (see
  [Binary operators](https://github.com/gilramir/gren-format-lib/blob/main/docs/formatterRules.md#binary-operators)).
- `discount`'s `if` branches always drop to their own line, whether or not
  they'd fit inline (see
  [If expressions](https://github.com/gilramir/gren-format-lib/blob/main/docs/formatterRules.md#if-expressions)).
- Both `when` branches return a record update, `{ order | ... }` — the
  `Cancelled` branch's field was written on one line and stays inline, while
  the other branch's two fields were written across rows and stay that way.
  Neither is about length; it's however the author wrote it (see
  [Record updates](https://github.com/gilramir/gren-format-lib/blob/main/docs/formatterRules.md#record-updates)).

Every one of these decisions follows from how the code was written, not from
any line-width target — see the
[Gren Formatter Library README](https://github.com/gilramir/gren-format-lib#background)
for the background, and the full
[Gren Formatter Rules](https://github.com/gilramir/gren-format-lib/blob/main/docs/formatterRules.md)
for the complete reference.

## Usage

```
gren-format [flags] [file ...]
```

Format every source file in the project (needs a `gren.json` in the current
directory or a parent):

```
gren-format
```

Format specific files or directories in place:

```
gren-format src/Main.gren src/Util.gren
```

Preview formatted output without writing:

```
gren-format --show src/Main.gren
```

Remove unused imports while formatting:

```
gren-format --remove-unused-imports
gren-format --remove-unused-imports src/Main.gren
gren-format --remove-unused-imports --show src/Main.gren
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
the full module graph. An exposed `Type(..)` is kept for the same reason:
it brings the type's constructors into scope unqualified, and a bare
constructor name elsewhere in the file can't be attributed to this import
versus another module's same-named constructor.

A *kept* import still has its exposing list trimmed name by name: any
exposed name that itself fails the "used anywhere" check is dropped even
though the import survives — `import Dict exposing (get, insert)` becomes
`import Dict exposing (get)` when only `get` is referenced.

A trailing comment on the *same source line* as a name being trimmed is
treated as attached to that name, and is removed along with it — the same
rule as a whole removed import's own trailing comment:

| Before | After |
|---|---|
| `import Basics exposing`<br>`( max`<br>`, min -- unused but has a note`<br>`)` | `import Basics exposing (max)` |

A comment on its *own line* near a trimmed name is left exactly where it
is, even though the name it may have been about is now gone — there's no
way to know whether an own-line comment was about the name below it, the
name above it, or something else entirely, so nothing here risks deleting
a comment that wasn't actually about the trimmed name:

| Before | After |
|---|---|
| `import Dict exposing`<br>`( get`<br>`-- keep this comment, it's important`<br>`, insert`<br>`)` | `import Dict exposing`<br>`( get`<br>`-- keep this comment, it's important`<br>`)` |

When an import is removed, any comments whose start line falls within
that import's source line range are removed with it. Comments elsewhere
(between imports, before or after the import block) are preserved. A
comment on its own line directly above a removed import is left in place
and the import is replaced by a `-- removed import Foo` placeholder, so
the comment is never silently reattached to whatever moves up into the
gap.

Assuming `Array` goes unused in each example below:

| Before | After |
|---|---|
| `import Dict`<br>`import Array -- unused, but noted here` | `import Dict` |
| `import Dict`<br>`-- Array is used for buffering`<br>`import Array` | `import Dict`<br>`-- Array is used for buffering`<br>`-- removed import Array` |
| `-- Module imports below`<br>`import Dict`<br>`import Array` | `-- Module imports below`<br>`import Dict` |


## Formatting pipeline

Every file goes through a format-and-verify pipeline before anything is
written to disk. The pipeline runs two full format passes and checks the
result at each stage to ensure correctness.

### Standard pipeline

![Standard formatting pipeline](docs/diagrams/standard-pipeline.png)

The reparse + AST comparison step ensures the formatter never silently
changes the meaning of a program. The idempotency check ensures that
formatting twice produces the same result as formatting once — so a
file that has already been formatted is left unchanged on future runs.

### Pipeline with `--remove-unused-imports`

When `--remove-unused-imports` is passed, an AST transformation step is
inserted between parsing and the first format pass. The rest of the
pipeline is identical, but all comparisons are made against the
transformed AST rather than the original.

![Formatting pipeline with --remove-unused-imports](docs/diagrams/remove-unused-imports-pipeline.png)

## Debug flags

These flags operate on a single file and write to stdout instead of disk:

| Flag | Effect |
|---|---|
| `--show <file>` | Format and print result |
| `--pre-ast <file>` | Print parsed AST as JSON |
| `--pre-context <file>` | Print parsed parse Context (comments) as JSON |
| `--post-ast <file>` | Format, verify ASTs match, print formatted AST as JSON |
| `--post-context <file>` | Format, print parse Context (comments) as JSON |
| `--lpt <file>` | Print Logical Printing Tree as JSON |
| `--box <file>` | Print the `Box` render tree as a JSON |

`--show` respects `--remove-unused-imports`. The other debug flags operate
on the raw AST and do not.

## Getting help / reporting bugs

Found a bug, or have formatting output that looks wrong? Open an issue at
[github.com/gilramir/gren-format/issues](https://github.com/gilramir/gren-format/issues).

Read more about the [Gren Community](https://gren-lang.org/community) and how
to join the Discord server, the official meeting place for people who
are curious about Gren. The core team posts development updates there
at regular intervals, and there are channels for people to ask questions.

---

Gilbert Ramirez <gram@alumni.rice.edu>
