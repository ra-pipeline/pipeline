"""Tests for calibPipeIF.py.

calibPipeIF.py drives pipelineMakeRequest, file copies (old --flag products
into the new run's working dir), and casa itself. Those three kinds of call
are the only ones these tests care about: everything else calibPipeIF.py
shells out to (hostname, whoami, ls, grep, git, uname, free -- all read-only
or harmless against a throwaway fixture tree) is left to run for real,
against a fake pipeline-output directory tree these tests build under a
temp dir standing in for SCIPIPE_ROOTDIR.

pipelineMakeRequest and casa itself are never actually runnable in a test
environment, so both are faked: subprocess.getoutput calls that start with
"pipelineMakeRequest" return a canned "Project root directory is ..."
response instead of invoking the real binary, and log.run/log.runquiet
(which calibPipeIF.py uses to shell out to casa, among other bookkeeping
commands) never execute anything -- only the ones that look like an actual
casa invocation (xvfb-run of casa/mpicasa) get recorded.

shutil.copy/shutil.copytree calls ARE allowed to run for real (they're just
copying files around inside the temp fixture tree, which is harmless) --
but every call is also recorded, in order, alongside the pipelineMakeRequest
and casa calls.

The reference for each scenario is the resulting call sequence, stored in
reference/calibpipeif_calls.txt (see that file's own comment) so it can be
reviewed/diffed by hand -- that file IS the spec these tests check against.
The only nondeterministic part of any recorded call is the path to this
test run's temp fixture tree, normalized to <TMP> before comparison.

Run with: python3 -m unittest discover -s tests -v
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import calibPipeIF  # noqa: E402

REFERENCE_FILE = Path(__file__).resolve().parent / "reference" / "calibpipeif_calls.txt"

MOUS = "uid://A001/X1/X1"
PPMR_REL_DIR = "2019.1.01234.S_run1"
SOUS_DIR = "SOUS_uid___A001_X1_Xa"
GOUS_DIR = "GOUS_uid___A001_X1_Xb"
MOUS_DIR = "MOUS_uid___A001_X1_Xc"
PRODUCTS_BASENAME = "uid___A001_X1_Xc"

PPR_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<PipelineProcessingRequest>
  <RelativePath>{PPMR_REL_DIR}/{SOUS_DIR}/{GOUS_DIR}/{MOUS_DIR}</RelativePath>
  <ProjectSummary>
    <ExecBlockId>uid://A002/Xaaa/Xbbb</ExecBlockId>
  </ProjectSummary>
</PipelineProcessingRequest>
"""

PMR_OUTPUT = (
    "Running pipelineMakeRequest...\n"
    f"Project root directory is {PPMR_REL_DIR}\n"
    "no files missing\n"
)


def _write_config(path, rootdir, logdir):
    path.write_text(f"""
default_env = "main"

[paths]
scipipe_rootdir = "{rootdir}"
scipipe_logdir = "{logdir}"
heuristics_root = "/fake/heuristics"

[envs.main]
casa_root = "/fake/casa/main"
""")


def _build_ppmr_tree(root):
    """Fake the on-disk layout a real pipelineMakeRequest run would leave
    behind under SCIPIPE_ROOTDIR -- this is what calibPipeIF.py looks for
    (via ls/grep) once its (faked) pipelineMakeRequest call returns."""
    mous_dir = root / PPMR_REL_DIR / SOUS_DIR / GOUS_DIR / MOUS_DIR
    working = mous_dir / "working"
    rawdata = mous_dir / "rawdata"
    products = mous_dir / "products"
    for d in (rawdata, products, working / "pipeline-0" / "html", working / "pipeline-1" / "html"):
        d.mkdir(parents=True, exist_ok=True)

    (working / f"PPR_{PRODUCTS_BASENAME}.xml").write_text(PPR_XML)
    # Stand-in for the fixes file the (faked) casa run would otherwise write.
    (working / "casa_pipescript.py.txt").write_text("print('fixes placeholder')\n")
    (products / f"{PRODUCTS_BASENAME}.casa_pipescript.py").write_text(
        "hifa_importdata(vis=['uid___A001_X1_Xc.ms'])\n"
    )
    (products / f"{PRODUCTS_BASENAME}.casa_piperestorescript.py").write_text(
        "hifa_restoredata(vis=['uid___A001_X1_Xc.ms'])\n"
    )


def _build_flag_dir(flagdir):
    """A --flag dir with old flag/tsys templates and a WVR table, but no old
    PPR -- exercises the shutil.copy/copytree calls without also dragging in
    the (much more involved) old-PPR-reuse code path."""
    flagdir.mkdir(parents=True, exist_ok=True)
    (flagdir / f"{PRODUCTS_BASENAME}.flagtsystemplate.txt").write_text("# flags\n")
    (flagdir / f"{PRODUCTS_BASENAME}.ms.wvr").mkdir()


def _normalize(text, tmp_root):
    return text.replace(str(tmp_root), "<TMP>")


def _format_calls(calls, tmp_root):
    lines = []
    for entry in calls:
        normalized = [_normalize(str(field), tmp_root) for field in entry]
        lines.append(" | ".join(normalized))
    return "\n".join(lines) + "\n"


def _load_reference():
    text = REFERENCE_FILE.read_text()
    blocks = {}
    name = None
    body = []
    for line in text.splitlines(keepends=True):
        if line.startswith("=====BEGIN "):
            name = line[len("=====BEGIN "):].split("=====")[0]
            body = []
        elif line.startswith("=====END "):
            blocks[name] = "".join(body)
            name = None
        elif name is not None:
            body.append(line)
    return blocks


class CalibPipeIFCaptureCase(unittest.TestCase):
    """Base class: runs calibPipeIF.main() against a fake pipelineMakeRequest
    output tree, with pipelineMakeRequest and casa itself faked out, and
    captures the ordered sequence of pipelineMakeRequest/copy/casa calls
    instead of ever invoking either of the first two for real."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        # calibPipeIF.main() chdir()s into the fixture tree; restore the
        # real cwd before the tmpdir above gets removed out from under it.
        self.addCleanup(os.chdir, os.getcwd())
        self.tmp = Path(self._tmpdir.name)

        self.root = self.tmp / "rootdir"
        self.logdir = self.tmp / "logdir"
        self.config = self.tmp / "config.toml"
        _write_config(self.config, self.root, self.logdir)
        _build_ppmr_tree(self.root)

    def run_and_capture(self, extra_args):
        calls = []
        real_getoutput = subprocess.getoutput
        real_copy = shutil.copy
        real_copytree = shutil.copytree

        def fake_getoutput(cmd):
            if cmd.startswith("pipelineMakeRequest"):
                calls.append(("pipelineMakeRequest", cmd))
                return PMR_OUTPUT
            if cmd.startswith("cp "):
                calls.append(("copy", cmd))
            return real_getoutput(cmd)

        def fake_copy(src, dst, *a, **kw):
            calls.append(("copy", "shutil.copy", src, dst))
            return real_copy(src, dst, *a, **kw)

        def fake_copytree(src, dst, *a, **kw):
            calls.append(("copy", "shutil.copytree", src, dst))
            return real_copytree(src, dst, *a, **kw)

        def fake_run(cmd):
            # Only the casa/mpicasa invocation counts as a "casa call" --
            # log.run/runquiet is also used for bookkeeping (git log, env
            # dump, weblog symlinks) that isn't part of this sequence, and
            # none of it needs to actually execute for these tests.
            if "xvfb-run" in cmd and ("/bin/casa " in cmd or "/bin/mpicasa " in cmd):
                calls.append(("casa", cmd))
            return 0

        argv = ["calibPipeIF.py"] + [
            f"--mous={MOUS}", f"--config={self.config}", "--env=main", "--recipe=calimage",
        ] + extra_args

        with patch.object(calibPipeIF, "argv", argv), \
             patch.object(calibPipeIF, "getoutput", side_effect=fake_getoutput), \
             patch.object(calibPipeIF.shutil, "copy", side_effect=fake_copy), \
             patch.object(calibPipeIF.shutil, "copytree", side_effect=fake_copytree), \
             patch.object(calibPipeIF.log, "run", side_effect=fake_run), \
             patch.object(calibPipeIF.log, "runquiet", side_effect=fake_run), \
             patch.dict(calibPipeIF.os.environ, {}, clear=False), \
             redirect_stdout(io.StringIO()):
            calibPipeIF.main()

        return calls

    def assert_matches_reference(self, name, calls):
        reference = _load_reference()
        self.assertIn(name, reference, f"no reference block named {name!r} in {REFERENCE_FILE}")
        actual = _format_calls(calls, self.tmp)
        self.assertEqual(actual, reference[name], f"call sequence mismatch for {name}")


class TestFlagDirCopiesOldProducts(CalibPipeIFCaptureCase):
    def test_flag_dir_yields_pipelineMakeRequest_then_copies_then_casa(self):
        flagdir = self.tmp / "flagdir"
        _build_flag_dir(flagdir)
        calls = self.run_and_capture([f"--flag={flagdir}"])

        categories = [c[0] for c in calls]
        self.assertEqual(
            categories, ["pipelineMakeRequest", "copy", "copy", "copy", "casa"],
            "expected pipelineMakeRequest, then the old-flag-file/wvr copies, then casa",
        )
        self.assert_matches_reference("with_flag_dir", calls)


class TestNoFlagDirSkipsCopies(CalibPipeIFCaptureCase):
    def test_no_flag_dir_yields_pipelineMakeRequest_then_casa_with_no_copies(self):
        calls = self.run_and_capture([])

        categories = [c[0] for c in calls]
        self.assertEqual(
            categories, ["pipelineMakeRequest", "casa"],
            "with no --flag dir there's nothing old to copy",
        )
        self.assert_matches_reference("without_flag_dir", calls)


if __name__ == "__main__":
    unittest.main()
