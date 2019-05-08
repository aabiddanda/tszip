# MIT License
#
# Copyright (c) 2019 Tskit Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""
Test cases for the command line interface for tszip.
"""
import io
import sys
import tempfile
import pathlib
import unittest
from unittest import mock

import tskit
import msprime
import numpy as np

import tszip
import tszip.cli as cli


class TestException(Exception):
    """
    Custom exception we can throw for testing.
    """


def capture_output(func, *args, **kwargs):
    """
    Runs the specified function and arguments, and returns the
    tuple (stdout, stderr) as strings.
    """
    buffer_class = io.BytesIO
    if sys.version_info[0] == 3:
        buffer_class = io.StringIO
    stdout = sys.stdout
    sys.stdout = buffer_class()
    stderr = sys.stderr
    sys.stderr = buffer_class()

    try:
        func(*args, **kwargs)
        stdout_output = sys.stdout.getvalue()
        stderr_output = sys.stderr.getvalue()
    finally:
        sys.stdout.close()
        sys.stdout = stdout
        sys.stderr.close()
        sys.stderr = stderr
    return stdout_output, stderr_output


class TestTszipArgumentParser(unittest.TestCase):
    """
    Tests for the tszip argument parser.
    """

    def test_default_values(self):
        parser = cli.tszip_cli_parser()
        infile = "tmp.trees"
        args = parser.parse_args([infile])
        self.assertEqual(args.files, [infile])
        self.assertEqual(args.keep, False)
        self.assertEqual(args.force, False)
        self.assertEqual(args.decompress, False)
        self.assertEqual(args.list, False)
        self.assertEqual(args.variants_only, False)
        self.assertEqual(args.suffix, ".tsz")

    def test_many_files(self):
        parser = cli.tszip_cli_parser()
        infiles = ["{}.trees".format(j) for j in range(1025)]
        args = parser.parse_args(infiles)
        self.assertEqual(args.files, infiles)

    def test_suffix(self):
        parser = cli.tszip_cli_parser()
        infile = "tmp.trees"
        args = parser.parse_args([infile, "-S", ".XYZ"])
        self.assertEqual(args.suffix, ".XYZ")
        args = parser.parse_args([infile, "--suffix=abx"])
        self.assertEqual(args.suffix, "abx")

    def test_decompress(self):
        parser = cli.tszip_cli_parser()
        infile = "tmp.trees.tsz"
        args = parser.parse_args([infile, "-d"])
        self.assertTrue(args.decompress)
        args = parser.parse_args([infile, "--decompress"])
        self.assertTrue(args.decompress)


class TestCli(unittest.TestCase):
    """
    Superclass of tests that run the CLI.
    """
    # Need to mock out setup_logging here or we spew logging to the console
    # in later tests.
    @mock.patch("tszip.cli.setup_logging")
    def run_cli(self, command, mock_setup_logging):
        stdout, stderr = capture_output(cli.tszip_main, command)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout, "")
        self.assertTrue(mock_setup_logging.called)


class TestBadFiles(TestCli):
    """
    Tests that we deal with IO errors appropriately.
    """
    def test_compress_missing(self):
        with mock.patch("sys.exit", side_effect=TestException) as mocked_exit:
            with self.assertRaises(TestException):
                self.run_cli(["/no/such/file"])
            mocked_exit.assert_called_once_with(
                "Error loading '/no/such/file': No such file or directory")

    def test_decompress_missing(self):
        with mock.patch("sys.exit", side_effect=TestException) as mocked_exit:
            with self.assertRaises(TestException):
                self.run_cli(["-d", "/no/such/file.tsz"])
            mocked_exit.assert_called_once_with(
                "[Errno 2] No such file or directory: '/no/such/file.tsz'")

    def test_list_missing(self):
        with mock.patch("sys.exit", side_effect=TestException) as mocked_exit:
            with self.assertRaises(TestException):
                self.run_cli(["-l", "/no/such/file.tsz"])
            mocked_exit.assert_called_once_with(
                "[Errno 2] No such file or directory: '/no/such/file.tsz'")


class TestCompressSemantics(TestCli):
    """
    Tests that the semantics of the CLI work as expected.
    """
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="tszip_cli_")
        self.trees_path = pathlib.Path(self.tmpdir.name) / "msprime.trees"
        self.ts = msprime.simulate(10, mutation_rate=10, random_seed=1)
        self.ts.dump(self.trees_path)

    def tearDown(self):
        del self.tmpdir

    def test_simple(self):
        self.assertTrue(self.trees_path.exists())
        self.run_cli([str(self.trees_path)])
        self.assertFalse(self.trees_path.exists())
        outpath = pathlib.Path(str(self.trees_path) + ".tsz")
        self.assertTrue(outpath.exists())
        ts = tszip.decompress(outpath)
        self.assertEqual(ts.tables, self.ts.tables)

    def test_suffix(self):
        self.assertTrue(self.trees_path.exists())
        self.run_cli([str(self.trees_path), "-S", ".XYZasdf"])
        self.assertFalse(self.trees_path.exists())
        outpath = pathlib.Path(str(self.trees_path) + ".XYZasdf")
        self.assertTrue(outpath.exists())
        ts = tszip.decompress(outpath)
        self.assertEqual(ts.tables, self.ts.tables)

    def test_variants_only(self):
        self.assertTrue(self.trees_path.exists())
        self.run_cli([str(self.trees_path), "--variants-only"])
        self.assertFalse(self.trees_path.exists())
        outpath = pathlib.Path(str(self.trees_path) + ".tsz")
        self.assertTrue(outpath.exists())
        ts = tszip.decompress(outpath)
        self.assertNotEqual(ts.tables, self.ts.tables)
        G1 = ts.genotype_matrix()
        G2 = self.ts.genotype_matrix()
        self.assertTrue(np.array_equal(G1, G2))

    def test_keep(self):
        self.assertTrue(self.trees_path.exists())
        self.run_cli([str(self.trees_path), "--keep"])
        self.assertTrue(self.trees_path.exists())
        outpath = pathlib.Path(str(self.trees_path) + ".tsz")
        self.assertTrue(outpath.exists())
        ts = tszip.decompress(outpath)
        self.assertEqual(ts.tables, self.ts.tables)

    def test_overwrite(self):
        self.assertTrue(self.trees_path.exists())
        outpath = pathlib.Path(str(self.trees_path) + ".tsz")
        outpath.touch()
        self.assertTrue(self.trees_path.exists())
        self.run_cli([str(self.trees_path), "--force"])
        self.assertFalse(self.trees_path.exists())
        self.assertTrue(outpath.exists())
        ts = tszip.decompress(outpath)
        self.assertEqual(ts.tables, self.ts.tables)

    def test_no_overwrite(self):
        self.assertTrue(self.trees_path.exists())
        outpath = pathlib.Path(str(self.trees_path) + ".tsz")
        outpath.touch()
        self.assertTrue(self.trees_path.exists())
        with mock.patch("sys.exit", side_effect=TestException) as mocked_exit:
            with self.assertRaises(TestException):
                self.run_cli([str(self.trees_path)])
            mocked_exit.assert_called_once_with(
                "'{}' already exists; use --force to overwrite".format(outpath))


class TestDecompressSemantics(TestCli):
    """
    Tests that the decompress semantics of the CLI work as expected.
    """
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="tszip_cli_")
        self.trees_path = pathlib.Path(self.tmpdir.name) / "msprime.trees"
        self.ts = msprime.simulate(10, mutation_rate=10, random_seed=1)
        self.compressed_path = pathlib.Path(self.tmpdir.name) / "msprime.trees.tsz"
        tszip.compress(self.ts, self.compressed_path)

    def tearDown(self):
        del self.tmpdir

    def test_simple(self):
        self.assertTrue(self.compressed_path.exists())
        self.run_cli([str(self.compressed_path), "--decompress"])
        self.assertFalse(self.compressed_path.exists())
        outpath = self.trees_path
        self.assertTrue(outpath.exists())
        ts = tskit.load(outpath)
        self.assertEqual(ts.tables, self.ts.tables)

    def test_suffix(self):
        suffix = ".XYGsdf"
        self.compressed_path = self.compressed_path.with_suffix(suffix)
        tszip.compress(self.ts, self.compressed_path)
        self.assertTrue(self.compressed_path.exists())
        self.run_cli([str(self.compressed_path), "-d", "-S", suffix])
        self.assertFalse(self.compressed_path.exists())
        outpath = self.trees_path
        self.assertTrue(outpath.exists())
        ts = tskit.load(outpath)
        self.assertEqual(ts.tables, self.ts.tables)

    def test_keep(self):
        self.assertTrue(self.compressed_path.exists())
        self.run_cli([str(self.compressed_path), "--decompress", "--keep"])
        self.assertTrue(self.compressed_path.exists())
        outpath = self.trees_path
        self.assertTrue(outpath.exists())
        ts = tskit.load(outpath)
        self.assertEqual(ts.tables, self.ts.tables)

    def test_overwrite(self):
        self.assertTrue(self.compressed_path.exists())
        outpath = self.trees_path
        outpath.touch()
        self.run_cli([str(self.compressed_path), "-df"])
        self.assertFalse(self.compressed_path.exists())
        self.assertTrue(outpath.exists())
        ts = tskit.load(outpath)
        self.assertEqual(ts.tables, self.ts.tables)

    def test_no_overwrite(self):
        self.assertTrue(self.compressed_path.exists())
        outpath = self.trees_path
        outpath.touch()
        with mock.patch("sys.exit", side_effect=TestException) as mocked_exit:
            with self.assertRaises(TestException):
                self.run_cli([str(self.compressed_path), "-d"])
            mocked_exit.assert_called_once_with(
                "'{}' already exists; use --force to overwrite".format(outpath))

    def test_decompress_bad_suffix(self):
        with mock.patch("sys.exit", side_effect=TestException) as mocked_exit:
            with self.assertRaises(TestException):
                self.run_cli([str(self.compressed_path), "-d", "-S", "asdf"])
            mocked_exit.assert_called_once_with(
                "Compressed file must have 'asdf' suffix")
