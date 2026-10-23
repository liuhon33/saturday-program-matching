"""Synthetic staged-content release checks; never modify the actual Git index."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZIP_DEFLATED, ZipFile


BASE = Path(__file__).resolve().parents[1]
TOOLS = BASE / "tools"


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


demo = load_tool("generate_demo_data")
with patch.dict(sys.modules, {"generate_demo_data": demo}):
    release = load_tool("check_release")


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples = {f"version_1/data/{name}": (BASE / 'data' / name).read_bytes() for name in demo.datasets()}
        cls.manifest = (TOOLS / 'sample_hashes.json').read_bytes()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="saturday-release-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.staged = {**self.examples, "version_1/tools/sample_hashes.json": self.manifest, "README.md": b"Synthetic release example\n", "version_1/saturday_match/example.py": b"# Synthetic source\n"}
        self.git_reads = []

    def fake_git(self, root, *args):
        self.git_reads.append(args)
        if args == ("rev-parse", "--show-toplevel"):
            return str(self.root).encode()
        if args == ("ls-files", "-z"):
            return ("\0".join(self.staged) + "\0").encode()
        if len(args) == 2 and args[0] == "show" and args[1].startswith(":"):
            return self.staged[args[1][1:]]
        raise AssertionError(f"Unexpected Git operation: {args[0]}")

    def inspect(self, *, dirty=False):
        with patch.object(release, "VERSION", self.root / "version_1"), patch.object(release, "git", self.fake_git), patch.object(release.subprocess, "run", return_value=SimpleNamespace(returncode=int(dirty))), contextlib.redirect_stderr(io.StringIO()):
            return release.inspect()

    def test_only_approved_public_paths_are_allowed(self):
        for path in ("README.md", ".gitignore", "version_0/2024dataframe.py", "version_0/README.md", "version_1/config/default.yaml", "version_1/tests/test_matcher.py", "version_1/data/2024tutee.xlsx", "version_1/tools/sample_hashes.json"):
            with self.subTest(path=path):
                self.assertTrue(release.approved(path, "version_1/"))
        for path in ("version_0/data/2024tutee.xlsx", "version_1/data/real_export.xlsx", "version_1/private_inputs/private.xlsx", "version_1/local_runs/run/matches.xlsx", "version_1/local_runs/run/summary.json", "review_output/sandbox_run/private.xlsx", ".git/config", "archive/old.py", "version_1/data/2024tutee.xlsx.bak", "version_10/config/default.yaml"):
            with self.subTest(path=path):
                self.assertFalse(release.approved(path, "version_1/"))

    def test_self_contained_version_one_paths_are_allowed(self):
        for path in ("README.md", "run_matching.py", "data/2024tutor.xlsx", "saturday_match/matcher.py"):
            self.assertTrue(release.approved(path, ""))
        self.assertFalse(release.approved("private_inputs/raw.xlsx", ""))

    def test_exact_synthetic_staged_content_passes(self):
        self.assertEqual(self.inspect(), self.staged)
        self.assertTrue(all(args[0] in {"rev-parse", "ls-files", "show"} for args in self.git_reads))

    def test_unexpected_tracked_private_path_is_rejected_before_read(self):
        private_path = "version_0/data/private.xlsx"
        self.staged[private_path] = b"PRIVATE-SOURCE-SENTINEL"
        with self.assertRaises(ValueError):
            self.inspect()
        self.assertNotIn(("show", ":" + private_path), self.git_reads)

    def test_missing_example_and_unstaged_changes_are_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect(dirty=True)
        del self.staged["version_1/data/2024tutor.xlsx"]
        with self.assertRaises(ValueError):
            self.inspect()

    def test_manifest_must_be_staged_and_have_exact_unique_entries(self):
        del self.staged['version_1/tools/sample_hashes.json']
        with self.assertRaises(ValueError):
            self.inspect()
        digest = '0' * 64
        for payload in (b'{}', b'[]', b'not JSON', json.dumps({name: 'bad-hash' for name in demo.datasets()}).encode(), ('{"2024tutor.xlsx":"' + digest + '","2024tutor.xlsx":"' + digest + '"}').encode()):
            with self.subTest(payload_type=payload[:1]):
                with self.assertRaises(ValueError):
                    release.sample_hashes(payload)

    def test_changed_workbook_cell_is_rejected(self):
        rows = demo.datasets()["2024tutee.xlsx"]
        rows[1][rows[0].index("Tutee 1 First Name")] = "PRIVATE-CELL-SENTINEL"
        self.staged["version_1/data/2024tutee.xlsx"] = demo.workbook_bytes(rows)
        with self.assertRaises(ValueError):
            self.inspect()

    def test_manifest_change_does_not_bypass_declared_rows(self):
        name = '2024tutee.xlsx'
        rows = demo.datasets()[name]
        rows[1][rows[0].index("Tutee 1 First Name")] = 'PRIVATE-CELL-SENTINEL'
        payload = demo.workbook_bytes(rows)
        self.staged['version_1/data/' + name] = payload
        hashes = json.loads(self.manifest)
        hashes[name] = hashlib.sha256(payload).hexdigest()
        self.staged['version_1/tools/sample_hashes.json'] = json.dumps(hashes).encode()
        with self.assertRaises(ValueError):
            self.inspect()

    def test_manifest_change_cannot_hide_extra_sheet_edits_or_omissions(self):
        name = 'scratch_tutee.xlsx'
        sheets = demo.workbook_sheets()[name]
        changed_rows = [row.copy() for row in sheets['Sheet2']]
        changed_rows[1][0] = 'PRIVATE-SECOND-SHEET-SENTINEL'
        variants = {
            'changed_extra_sheet': demo.workbook_bytes(sheets['Sheet1'], extra_sheets={'Sheet2': changed_rows}),
            'missing_extra_sheet': demo.workbook_bytes(sheets['Sheet1']),
            'undeclared_extra_sheet': demo.workbook_bytes(sheets['Sheet1'], extra_sheets={'Sheet2': sheets['Sheet2'], 'Private': [['PRIVATE-SHEET-SENTINEL']]}),
        }
        for case, payload in variants.items():
            with self.subTest(case=case):
                self.staged['version_1/data/' + name] = payload
                hashes = json.loads(self.manifest)
                hashes[name] = hashlib.sha256(payload).hexdigest()
                self.staged['version_1/tools/sample_hashes.json'] = json.dumps(hashes).encode()
                with self.assertRaises(ValueError):
                    self.inspect()

    def test_hidden_zip_member_is_rejected(self):
        path = "version_1/data/2024tutee.xlsx"
        buffer = io.BytesIO(self.staged[path])
        with ZipFile(buffer, "a", ZIP_DEFLATED) as book:
            book.writestr("private-extra.xml", b"PRIVATE-MEMBER-SENTINEL")
        self.staged[path] = buffer.getvalue()
        with self.assertRaises(ValueError):
            self.inspect()

    def test_hidden_zip_comments_and_appended_bytes_are_rejected(self):
        path = "version_1/data/2024tutee.xlsx"
        original = self.staged[path]
        buffer = io.BytesIO(original)
        with ZipFile(buffer, "a") as book:
            book.comment = b"PRIVATE-ARCHIVE-COMMENT-SENTINEL"
        variants = {"archive_comment": buffer.getvalue(), "appended_bytes": original + b"PRIVATE-TRAILING-SENTINEL", "prepended_bytes": b"PRIVATE-PREFIX-SENTINEL" + original}
        # Member comments are outside the decompressed XML member content too.
        buffer = io.BytesIO()
        with ZipFile(io.BytesIO(original)) as source, ZipFile(buffer, "w", ZIP_DEFLATED) as target:
            for index, entry in enumerate(source.infolist()):
                if index == 0:
                    entry.comment = b"PRIVATE-MEMBER-COMMENT-SENTINEL"
                target.writestr(entry, source.read(entry.filename))
        variants["member_comment"] = buffer.getvalue()
        buffer = io.BytesIO()
        with ZipFile(io.BytesIO(original)) as source, ZipFile(buffer, 'w', ZIP_DEFLATED) as target:
            for index, entry in enumerate(source.infolist()):
                if index == 0:
                    private = b'PRIVATE-EXTRA-FIELD-SENTINEL'
                    entry.extra = b'\xfe\xca' + len(private).to_bytes(2, 'little') + private
                target.writestr(entry, source.read(entry.filename))
        variants['member_extra_field'] = buffer.getvalue()
        for name, payload in variants.items():
            with self.subTest(name=name):
                self.staged[path] = payload
                with self.assertRaises(ValueError):
                    self.inspect()

    def test_duplicate_zip_entries_are_rejected(self):
        buffer = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(buffer, "w") as book:
                book.writestr("sheet.xml", b"first")
                book.writestr("sheet.xml", b"second")
        with self.assertRaises(ValueError):
            release.zip_parts(buffer.getvalue())

    def test_text_checks_reject_email_credentials_and_account_paths(self):
        examples = {
            "email": "person" + "@" + "non-example.test",
            "credential": "gh" + "p_" + "A" * 25,
            "account_path": "C:" + chr(92) + "Users" + chr(92) + "Synthetic Account" + chr(92) + "private",
        }
        for kind, value in examples.items():
            with self.subTest(kind=kind):
                self.staged["README.md"] = value.encode()
                with self.assertRaises(ValueError):
                    self.inspect()

    def test_zip_exports_only_verified_staged_files_and_refuses_overwrite(self):
        destination = self.root / "release.zip"
        argv = ["check_release.py", "--export", str(destination)]
        with patch.object(release, "VERSION", self.root / "version_1"), patch.object(release, "git", self.fake_git), patch.object(release.subprocess, "run", return_value=SimpleNamespace(returncode=0)), patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(release.main(), 0)
            before = destination.read_bytes()
            self.assertEqual(release.main(), 1)
            self.assertEqual(destination.read_bytes(), before)
        with ZipFile(destination) as archive:
            self.assertEqual(set(archive.namelist()), set(self.staged))
            self.assertEqual({name: archive.read(name) for name in archive.namelist()}, self.staged)


if __name__ == "__main__":
    unittest.main()
