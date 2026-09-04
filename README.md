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

Links:
 * The application
   * [gren-format npmjs page](https://www.npmjs.com/package/gren-format)
   * [gren-format GitHub page](https://github.com/gilramir/gren-format)
 * The library
   * [gren-format-lib Gren package page](https://packages.gren-lang.org/package/gilramir/gren-format-lib)
   * [gren-format-lib GitHub page](https://github.com/gilramir/gren-format-lib)
   * [Gren Formatter Library Documentation](https://github.com/gilramir/gren-format-lib/blob/main/docs/index.md)

This README documents the usage of the tool.  The actual formatting rules
are documented in the
[Gren Formatter Library Documentation](https://github.com/gilramir/gren-format-lib),
the code which does the actual formatting and can be used in other Gren programs.

The formatter is very careful when changing your code.
* It re-parses its output to ensure it didn't change the meaning of your code.
* It re-formats its output to ensure its own formatting is idempotent,
  guarding against diffs for no reason.

If either check fails, it reports a bug to the user instead of overwriting the file.

## A real example

One function, showing several rules at once: a `let` with multiple bindings,
a pipeline, a binary-operator chain that breaks at its loosest operators, an
`if`, a `when`, a record update, and all three kinds of comment. (`order` is a
record with `isMember`, `hasCoupon`, `status`, and `total` fields; `Status` is
a custom type that includes `Cancelled`.)

```gren
{- Only members and coupon holders get the discount, and it always
   applies to the pre-tax subtotal.
-}
summarize : Order -> Array Float -> Order
summarize order prices =
    let
        subtotal =
            prices
                |> Array.keepIf (\price -> price > 0) -- refunds are recorded as negatives
                |> Array.foldl (+) 0

        eligible =
            order.isMember && subtotal > 100
                || order.hasCoupon && order.status /= Cancelled

        discount =
            if eligible then
                subtotal * {- ten percent -} 0.1

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
- All three comments stay exactly where they were written. The `{- ... -}`
  above the signature keeps its own lines and its inner indentation; the `--`
  note stays trailing on the pipeline step it was written on, rather than being
  pushed to a line of its own; and the one-line `{- ten percent -}` sits *inside*
  the expression, between the `*` and its right operand, so the line it's on has
  to stay flat — a comment is never a reason to break a line, and a line is
  never re-broken around a comment (see
  [Comments](https://github.com/gilramir/gren-format-lib/blob/main/docs/formatterRules.md#comments)).

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

A directory argument is **not** recursed into: `gren-format src/` formats the
Gren sources sitting directly in `src/` and nothing below it. Pass `-r` /
`--recurse` to walk the whole subtree:

```
gren-format -r src/
```

A recursive walk skips dotted directories (`.git`, `.gren`), `node_modules` and
`gren_packages` — those hold other people's source, and rewriting every
installed dependency is not what anyone means by `gren-format -r .`.

Symbolic links are never followed and never formatted. A recursive walk passes
over one whether it points at a directory or at a `.gren` file, and naming it on
the command line does not change that:

```
$ gren-format Link.gren
Link.gren: skipped (symbolic link)
0 files reformatted, 0 files already formatted.
```

The note goes to stderr and the run still exits 0, so one link caught by a glob
does not stop the real files beside it. The reason a link cannot be formatted is
how the write works: `gren-format` renames a temporary file onto the path, which
would leave a regular file where the link was and the link's target still
unformatted — a link quietly turned into a copy.

Preview formatted output without writing:

```
gren-format --show src/Main.gren
```

See what a run would change, without changing anything:

```
gren-format --diff
gren-format --diff src/Main.gren src/Util.gren
```

Remove unused imports while formatting:

```
gren-format --remove-unused-imports
gren-format --remove-unused-imports src/Main.gren
gren-format --remove-unused-imports --show src/Main.gren
```

Watch a large project go by, one file at a time:

```
gren-format --show-progress
```

Each file's name is printed *before* it is parsed, with no newline, and its
outcome — `reformatted`, `already formatted`, `parse error`, `format error` —
lands on that same line once the file is done:

```
src/Formatter/Render/FlowPolicy.gren ... already formatted
src/Formatter/Render/MakeRenderBox.gren ... reformatted
2 files reformatted, 24 files already formatted.
```

So a run that spends a second on one module says which module it is spending
it on. `--show-progress` applies to both in-place modes (the no-argument
project run and positional paths); the single-file debug flags ignore it.

## Line endings

`gren-format` always writes LF (`\n`) line endings, whatever the file had
before. A file written with Windows CRLF endings formats to LF, including
inside a multiline string.

This is not a Gren-specific choice: `elm-format` does the same, and has done
since 0.6.0-alpha. Both tools accept CRLF happily on the way in and emit LF on
the way out, and neither has a flag to keep the endings you wrote.

The practical consequence is that **line endings are formatting**. A file whose
only defect is CRLF is not "already formatted": a run rewrites it, it is
counted in the "N files reformatted" total, and `--diff` reports it. Because
its *line* diff is empty, `--diff` names the reason on a `\ ` note line rather
than printing nothing (see below).

## Previewing changes with `--diff`

`--diff` (or `-d`) makes an in-place run a dry run. It looks at exactly the
same files it would otherwise rewrite; the whole project with no arguments, or
the paths you name. But instead of writing anything it prints each changed
file's unified diff to stdout:

```
$ gren-format --diff
diff src/Main.gren.orig src/Main.gren
--- src/Main.gren.orig
+++ src/Main.gren
@@ -4,6 +4,8 @@
 
 
 main =
-  let x = 1
-  in
-  x + 2
+    let
+        x =
+            1
+    in
+    x + 2
```

A file that is already formatted contributes no output, so a clean run
prints nothing at all. Exit status is 0 either way; only a real failure
(a file that doesn't parse, or a formatter bug) is non-zero.

The header names a `.orig` original that doesn't exist, so the output is a
plain patch against your working tree and pipes straight into `patch`:

```
gren-format --diff | patch -p0
```

Applying it lands the same bytes the in-place run would have written.

Occasionally a file needs rewriting but its *line* diff is empty, because the
change is in bytes a line-based diff can't show — CRLF line endings being
normalized, or a missing newline at the end of the file. Printing nothing there
would be a lie about a file the very next in-place run rewrites, so `--diff`
names the reason instead, on a `\ ` line — the marker unified diff already
reserves for notes about a file rather than about a line:

```
diff src/Main.gren.orig src/Main.gren
--- src/Main.gren.orig
+++ src/Main.gren
\ Only the line endings differ (CRLF becomes LF).
```

`--diff` combines with `--remove-unused-imports` and with `--show-progress`;
it cannot be combined with the single-file debug flags below. Under
`--diff`, `--show-progress` reports each file as `would reformat` and sends
its whole progress line to **stderr**, so stdout stays a clean patch:

```
$ gren-format --diff --show-progress > changes.patch
src/Main.gren ... would reformat
src/Util.gren ... already formatted
```

## Removing unused import statements

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


## The Formatting Pipeline

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
| `--rt <file>` | Print the render tree as JSON — the same tree with the source positions stripped, as the renderer receives it |
| `--box <file>` | Print the `Box` tree — the render plan — as JSON |

`--show` respects `--remove-unused-imports`. The other debug flags operate
on the raw AST and do not. None of them can be combined with `--diff`, which
works on whole file sets rather than a single named file.

## Getting help / reporting bugs

Found a bug, or have formatting output that looks wrong? Open an issue at
[github.com/gilramir/gren-format/issues](https://github.com/gilramir/gren-format/issues) or
[https://github.com/gilramir/gren-format-lib/issues](https://github.com/gilramir/gren-format-lib/issues).
It doesn't matter which GitHub project you file it in; we're flexible.

Read more about the [Gren Community](https://gren-lang.org/community) and how
to join the Discord server, the official meeting place for people who
are curious about Gren. The core team posts development updates there
at regular intervals, and there are channels for people to ask questions.

---

Gilbert Ramirez <gram@alumni.rice.edu>
