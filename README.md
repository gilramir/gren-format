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

`--remove-unused-imports` drops an import if nothing in the module
references it, and trims an exposing list name by name the same way. It's
conservative: `exposing (..)` and an exposed `Type(..)` are always kept,
since there's no way to know what names they bring into scope.

Comments are only ever removed when they're clearly about what's being
removed. A trailing comment on the same line as a trimmed name goes with it:

| Before | After |
|---|---|
| `import Basics exposing`<br>`( max`<br>`, min -- unused but has a note`<br>`)` | `import Basics exposing (max)` |

An own-line comment is left in place, even next to a trimmed name — there's
no way to know which name below or above it a comment was actually about:

| Before | After |
|---|---|
| `import Dict exposing`<br>`( get`<br>`-- keep this comment, it's important`<br>`, insert`<br>`)` | `import Dict exposing`<br>`( get`<br>`-- keep this comment, it's important`<br>`)` |

Removing a whole import removes its trailing comment and any comment inside
its line range, but leaves an own-line comment directly above it in place,
with a `-- removed import Foo` placeholder marking what used to be there.
A trailing comment can itself be trailed — the whole chain was written about
the import, so the whole chain goes with it. A comment a row further down is
not part of that chain: it belongs to whatever comes next, and stays.

The same holds in front of the import. A comment glued to the `import`
keyword goes with it, however many rows it spans — `{- unused -} import Foo`
and its two-row form are treated alike. An own-line comment above that glued
one is not glued to anything, so it stays, with the usual placeholder below
it.

| Before | After |
|---|---|
| `import Dict`<br>`import Array -- unused, but noted here` | `import Dict` |
| `import Dict`<br>`-- Array is used for buffering`<br>`import Array` | `import Dict`<br>`-- Array is used for buffering`<br>`-- removed import Array` |
| `-- Module imports below`<br>`import Dict`<br>`import Array` | `-- Module imports below`<br>`import Dict` |
| `import Dict`<br>`import Array {- unused`<br>`and it wraps -} -- trailing that` | `import Dict` |
| `import Dict`<br>`{- unused, and this`<br>`wraps too -} import Array` | `import Dict` |
| `import Dict`<br>`-- an own-line note`<br>`{- glued -} import Array` | `import Dict`<br>`-- an own-line note`<br>`-- removed import Array` |
| `import Dict`<br>`import Array {- unused`<br>`and it wraps -}`<br>`-- a row lower, about Set`<br>`import Set` | `import Dict`<br>`-- a row lower, about Set`<br>`import Set` |

### When the last import goes

Gren reads a `{-| ... -}` that comes straight after the module line as the
module's own documentation. A doc comment on your first declaration is that
declaration's doc only because the imports sit between it and the module
line — so removing the *last* import would hand your function's
documentation to the module, and the function would be left with none.

To keep it where you wrote it, `gren-format` fills the module's doc slot
with a placeholder naming the import it removed:

```gren
module Buffer exposing (empty)

import Array


{-| An empty buffer. -}
empty =
    0
```

becomes

```gren
module Buffer exposing (empty)

{-| removed import Array -}


{-| An empty buffer. -}
empty =
    0
```

The placeholder is a real doc comment, so **you can replace it with your own
module documentation** — that is the better thing to have there, and once the
module has a doc of its own nothing is inserted again.

This only happens when all three are true: no import survives, the module has
no doc comment of its own, and the first declaration has one. Any one of them
being false means no placeholder — a module that still imports something, or
already documents itself, or whose first declaration is undocumented, is left
alone.


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
