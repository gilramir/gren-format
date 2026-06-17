"""CLI integration tests for the gren-format binary."""

import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "gren-format.sh")
TESTFILES = os.path.join(HERE, "testfiles")

MINIMAL_GREN_JSON = {
    "type": "application",
    "platform": "node",
    "source-directories": ["src"],
    "gren-version": "0.6.5",
    "dependencies": {
        "direct": {},
        "indirect": {},
    },
}


class GrenFormatTestCase(unittest.TestCase):
    def run_app(self, *args, cwd=None):
        return subprocess.run(
            [APP, *args],
            capture_output=True,
            text=True,
            cwd=cwd or HERE,
        )

    def make_project(self, base_dir, src_files=None):
        """Write gren.json and any src_files (rel-path → content) under base_dir."""
        os.makedirs(os.path.join(base_dir, "src"), exist_ok=True)
        with open(os.path.join(base_dir, "gren.json"), "w") as f:
            json.dump(MINIMAL_GREN_JSON, f, indent=4)
        for rel_path, content in (src_files or {}).items():
            full_path = os.path.join(base_dir, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)


class TestNoArgs(GrenFormatTestCase):
    def test_prints_safety_message(self):
        result = self.run_app()
        self.assertEqual(result.returncode, 0)
        self.assertIn("default action is disabled", result.stdout)

    def test_help_flag(self):
        result = self.run_app("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--all", result.stdout)


class TestShowFlag(GrenFormatTestCase):
    def test_formats_file_to_stdout(self):
        hello = os.path.join(TESTFILES, "Hello.gren")
        result = self.run_app("--show", hello)
        self.assertEqual(result.returncode, 0)
        self.assertIn("module Hello", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_missing_file_exits_nonzero(self):
        result = self.run_app("--show", "/nonexistent/Missing.gren")
        self.assertNotEqual(result.returncode, 0)

    def test_unparseable_file_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "Bad.gren")
            with open(path, "w") as f:
                f.write("this is not valid gren syntax\n")
            result = self.run_app("--show", path)
            self.assertNotEqual(result.returncode, 0)


class TestJsonFlags(GrenFormatTestCase):
    def test_pre_ast_outputs_valid_json(self):
        hello = os.path.join(TESTFILES, "Hello.gren")
        result = self.run_app("--pre-ast", hello)
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertIn("module", data)
        self.assertIn("context", data)

    def test_post_ast_outputs_valid_json(self):
        hello = os.path.join(TESTFILES, "Hello.gren")
        result = self.run_app("--post-ast", hello)
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertIn("module", data)

    def test_lpt_outputs_valid_json(self):
        hello = os.path.join(TESTFILES, "Hello.gren")
        result = self.run_app("--lpt", hello)
        self.assertEqual(result.returncode, 0)
        json.loads(result.stdout)  # just verify it parses

    def test_pex_outputs_valid_json(self):
        hello = os.path.join(TESTFILES, "Hello.gren")
        result = self.run_app("--pex", hello)
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertIsInstance(data, list)


class TestPositionalArgs(GrenFormatTestCase):
    def test_formats_file_in_place(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "Hello.gren")
            with open(path, "w") as f:
                f.write("module Hello exposing (x)\nx : Int\nx =\n    1\n")
            result = self.run_app(path)
            self.assertEqual(result.returncode, 0)
            with open(path) as f:
                formatted = f.read()
            self.assertIn("\n\n\n", formatted)  # two blank lines before signature

    def test_formats_multiple_files_in_place(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dirty = "module {name} exposing (x)\nx : Int\nx =\n    1\n"
            path_a = os.path.join(tmpdir, "A.gren")
            path_b = os.path.join(tmpdir, "B.gren")
            with open(path_a, "w") as f:
                f.write(dirty.format(name="A"))
            with open(path_b, "w") as f:
                f.write(dirty.format(name="B"))
            result = self.run_app(path_a, path_b)
            self.assertEqual(result.returncode, 0)
            for path in [path_a, path_b]:
                with open(path) as f:
                    self.assertIn("\n\n\n", f.read())

    def test_flag_combined_with_positional_arg_exits_nonzero(self):
        hello = os.path.join(TESTFILES, "Hello.gren")
        result = self.run_app("--show", hello, hello)
        self.assertNotEqual(result.returncode, 0)


class TestAllFlag(GrenFormatTestCase):
    def test_formats_project_files_in_place(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.make_project(
                tmpdir,
                {"src/Hello.gren": "module Hello exposing (x)\nx : Int\nx =\n    1\n"},
            )
            result = self.run_app("--all", cwd=tmpdir)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Hello.gren", result.stdout)
            with open(os.path.join(tmpdir, "src", "Hello.gren")) as f:
                formatted = f.read()
            self.assertIn("\n\n\n", formatted)  # two blank lines before signature

    def test_no_gren_json_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.run_app("--all", cwd=tmpdir)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
