from __future__ import annotations

import ast
import glob
import os
import re
import shutil
from typing import TYPE_CHECKING

import packaging.version
import pytest

from pipeline import environment, infrastructure, recipereducer
from pipeline.infrastructure import casa_tools, executeppr, executevlappr, launcher, utils
from pipeline.infrastructure.renderer import regression

if TYPE_CHECKING:
    from typing import Any, Literal

    from packaging.version import Version

LOG = infrastructure.logging.get_logger(__name__)


def ensure_working_dir(pt: PipelineTester) -> None:
    """Ensure the working directory exists for a PipelineTester instance.

    Args:
        pt: PipelineTester instance whose output_dir working directory should be created.

    Raises:
        OSError: If the directory cannot be created due to permission or other OS-level errors.
    """
    try:
        os.makedirs(f'{pt.output_dir}/working/', exist_ok=True)
    except OSError as exc:
        LOG.warning("Failed to create working directory for %s: %s", pt.output_dir, exc)
        raise


def setup_flux_antennapos(test_directory: str, output_dir: str) -> None:
    """Copy flux.csv and antennapos.csv into the working directory.
    Args:
        test_directory: Directory where flux.csv and antennapos.csv are located.
        output_dir: Output directory where the working directory is located.

    Raises:
        OSError: If the files cannot be copied due to permission or other OS-level errors.
    """
    flux_file = casa_tools.utils.resolve(f'{test_directory}/flux.csv')
    antennapos_file = casa_tools.utils.resolve(f'{test_directory}/antennapos.csv')

    try:
        os.makedirs(f'{output_dir}/working/', exist_ok=True)
    except OSError as exc:
        LOG.warning("Failed to create working directory for %s: %s", output_dir, exc)
        raise

    shutil.copyfile(flux_file, casa_tools.utils.resolve(f'{output_dir}/working/flux.csv'))
    shutil.copyfile(antennapos_file, casa_tools.utils.resolve(f'{output_dir}/working/antennapos.csv'))


class PipelineTester:
    """Pipeline Testing Framework.

    This module provides the `PipelineTester` base class and associated pytest test functions
    for automated testing of the NRAO pipeline.
    """
    regex_casa_pattern = re.compile(r'.*casa-([\d.]+(?:-\d+)?)')
    regex_pipeline_pattern = re.compile(r'.*pipeline-([\d.]+(?:\.\d+)*\d)(?=\b|[-_]|$)')

    def __init__(
            self,
            visname: list[str],
            *,
            mode: Literal['regression', 'component'] = 'regression',
            ppr: str | None = None,
            recipe: str | None = None,
            tasks: list[tuple[str, dict[str, Any]] | None] | None = None,
            project_id: str | None = None,
            input_dir: str | None = None,
            output_dir: str | None = None,
            expectedoutput_file: str | None = None,
            expectedoutput_dir: str | None = None,
            ):
        """Initializes a PipelineTester instance.

        Args:
            visname: List of MeasurementSets used for testing.
            mode: Signifies testing workflow to follow. Options are 'regression' and 'component'. Default is 'regression'.
            ppr: Path to the PPR file, only used in regression tests. Takes precedence over `recipe` if both are provided.
            recipe: Path to the recipe XML file.
            tasks: List of tuples with pipeline stage strings first and optional parameters second. Only used in
                component tests.
            project_id: Project ID. If provided, it is prefixed to the `output_dir` name.
            input_dir: Path to the directory containing input files.
            output_dir: Path to the output directory. If `None`, it is derived using `visname` and/or `project_id`.
            expectedoutput_file: Path to a file defining the expected test output. Overrides `expectedoutput_dir` if set.
            expectedoutput_dir: Path to a directory containing expected output files. Ignored if `expectedoutput_file` is set.

        Raises:
            ValueError: For `mode='regression'`, if neither `recipe` nor `ppr` is provided.
                        For `mode='component'`, if `tasks` is not provided.
        """
        self.visname = visname
        self.mode = mode
        if self.mode == 'regression':
            if not recipe and not ppr:
                raise ValueError("At least one of recipe or ppr must be provided.")
        elif self.mode == 'component':
            if not tasks:
                raise ValueError("A list of tasks must be provided.")
        self.ppr = ppr
        self.recipe = recipe
        self.tasks = tasks
        self.project_id = project_id
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.expectedoutput_file = expectedoutput_file
        if output_dir:
            self.output_dir = output_dir
        elif self.project_id:
            self.output_dir = f'{self.project_id}__{self.visname[0]}_test_output'
        else:
            self.output_dir = f'{self.visname[0]}_test_output'
        if expectedoutput_file:
            self.expectedoutput_file = casa_tools.utils.resolve(expectedoutput_file)
        else:
            self.expectedoutput_dir = expectedoutput_dir
            # Find the reference file in expectedoutput_dir that matches the current CASA version and use that.
            if expectedoutput_dir:
                reference_data_files = glob.glob(casa_tools.utils.resolve(expectedoutput_dir)+'/*.results.txt')
                if reference_data_files:
                    self.expectedoutput_file = self._pick_results_file(reference_data_files=reference_data_files)
                    if self.expectedoutput_file:
                        LOG.info("Using %s for the reference value file.", self.expectedoutput_file)
                    else:
                        LOG.warning(
                            "None of the reference files in %s match the current CASA/Pipeline version. This test will fail.",
                            expectedoutput_dir
                            )
                else:
                    LOG.warning("No reference files found in %s. This test will fail.", expectedoutput_dir)

        self.testinput = [f'{input_dir}/{vis}' for vis in self.visname]
        self.current_path = os.getcwd()

        if hasattr(pytest, 'pytestconfig'):
            self.remove_workdir = pytest.pytestconfig.getoption('--remove-workdir')
            self.compare_only = pytest.pytestconfig.getoption('--compare-only')
        else:
            self.remove_workdir = False
            self.compare_only = False

        if not self.compare_only:
            self.__initialize_working_folder()

    def __initialize_working_folder(self) -> None:
        """Initialize a root folder for task execution."""
        if os.path.isdir(self.output_dir):
            shutil.rmtree(self.output_dir)
        os.mkdir(self.output_dir)

    def _pick_results_file(self, reference_data_files: list[str]) -> str | None:
        """Picks results file based on the active CASA version from the given list of file_names

        Args:
            reference_data_files: results filenames to analyze for usage
        Returns:
            results filename determined to be most relevant for comparison
        """
        reference_dict = {}

        for file_name in reference_data_files:
            casa_match = self.regex_casa_pattern.match(file_name)
            pipeline_match = self.regex_pipeline_pattern.match(file_name)

            if casa_match and pipeline_match:
                try:
                    # remove '-' from version number in the CASA version for proper comparison
                    casa_version = casa_match.group(1).replace("-", ".")
                    reference_dict[file_name] = {
                        "CASA version": packaging.version.parse(casa_version),
                        "Pipeline version": packaging.version.parse(pipeline_match.group(1))
                        }
                except Exception as e:
                    LOG.warning("Error parsing version from reference file '%s': %s. Skipping.", file_name, e)
            else:
                # Determine which one(s) failed to match
                missing_parts = []
                if not casa_match:
                    missing_parts.append("CASA version")
                if not pipeline_match:
                    missing_parts.append("Pipeline version")

                LOG.warning("Couldn't determine %s from reference file '%s'. Skipping.", " or ".join(missing_parts), file_name)

        return self._results_file_heuristics(reference_dict=reference_dict)

    def _results_file_heuristics(self, reference_dict: dict[str, dict[str, Version]]) -> str | None:
        """Analyze the relevant results files and pick the one that matches the closest to the current running versions

        Current heuristics will reject any file with CASA or Pipeline versions that exceed the current running versions

        Args:
            reference_dict: filenames as keys and dictionaries as values containing CASA and Pipeline versions 
                extracted from the filenames
        Returns:
            best_match: results filename determined to be most relevant for comparison
        """
        current_versions = {}
        current_versions["CASA version"] = packaging.version.parse(environment.casa_version_string)
        pipeline_revision_pattern = re.compile(r'([\d.]+)')
        current_versions["Pipeline version"] = packaging.version.parse(
            pipeline_revision_pattern.match(environment.pipeline_revision).group(1)
            )

        best_match = None
        best_versions = None

        for filename, versions in reference_dict.items():
            # Filter out files that exceed any of the current software versions
            if any(version > current_versions[software]
                   for software, version in versions.items()):
                continue  # Skip this file

            if best_match is None:
                best_match = filename
                best_versions = versions
                continue

            # Compare against the current best, determining if it is a better match
            better_match = False
            for software in current_versions:
                version = versions[software]
                best_version = best_versions[software]
                running_version = current_versions[software]

                # Prefer a file with a version closer to, but not exceeding, the running version
                if version > best_version and version <= running_version:
                    better_match = True
                elif version < best_version:  # If it's worse for any software, reject it
                    better_match = False
                    break

            if better_match:
                best_match = filename
                best_versions = versions

        return best_match

    def __sanitize_results_string(self, instring: str) -> tuple[str, str, float | None]:
        """Sanitize to get numeric values, remove newline chars and change to float.

        instring format: "[quantity_name]=[quantity value]:::tolerance"
        Example:
        s2.hifv_statwt.13A-537.sb24066356.eb24324502.56514.05971091435.mean=1.6493377758284253:::0.000001

        Args:
            instring: input string
        Returns:
            tuple(key, value, optional tolerance)
        """
        # Get string with the quantity name and value (everything but the tolerance)
        # example: s2.hifv_statwt.13A-537.sb24066356.eb24324502.56514.05971091435.mean=1.6493377758284253
        keyval = instring.split(':::')[0]

        # Get just the quantity name
        # example: s2.hifv_statwt.13A-537.sb24066356.eb24324502.56514.05971091435.mean
        keystring = keyval.split('=')[0]

        # Try to convert the value in string to int, float, Boolean, or None
        try:
            value = ast.literal_eval(keyval.split("=")[-1])
        except ValueError:
            value = keyval.split("=")[-1]
        if not isinstance(value, (float, int, bool, type(None))):
            value = keyval.split("=")[-1]
            raise ValueError(
                f"For key '{keystring}', value '{value}' of type {type(value).__name__} "
                "cannot be converted to int/float/boolean/None.")

        try:
            tolerance = float(instring.split(':::')[-1].replace('\n', ''))
        except ValueError:
            tolerance = None

        return keystring, value, tolerance

    def run(
            self,
            *,
            telescope: Literal['alma', 'vla'] = 'alma',
            default_relative_tolerance: float = 1e-7,
            omp_num_threads: int | None = None,
            ) -> None:
        """
        Run test with recipereducer and compared to expected results.

        The inputs and expected output are usually found in the pipeline data repository.

        Args:
            telescope: Name of the telescope used to take the data. Options are 'alma' or 'vla'. Defaults to 'alma'.
            default_relative_tolerance: Default relative tolerance of output value.
            omp_num_threads: Specify the number of OpenMP threads used for this regression test instance, regardless of
                             the default value of the current CASA session. An explicit setting could mitigate potential small
                             numerical difference from threading-sensitive CASA tasks (e.g. setjy/tclean, which relies
                             on the FFTW library).

        NOTE: Because a PL execution depends on global CASA states, only one test can run under
        a CASA process at the same. Therefore a parallelization based on process-forking might not work
        properly (e.g., xdist: --forked).  However, it's okay to group tests under several independent
        subprocesses (e.g., xdist: -n 4)

        """
        # Run the Pipeline using cal+imag ALMA IF recipe
        # set datapath in ~/.casa/config.py, e.g. datapath = ['/users/jmasters/pl-testdata.git']
        input_vis = [casa_tools.utils.resolve(testinput) for testinput in self.testinput]

        if not self.compare_only and omp_num_threads is not None:
            # optionally set OpenMP nthreads to a specified value.
            # casa_tools.casalog.ompGetNumThreads() and utils.get_casa_session_details()['omp_num_threads'] are equivalent.
            default_nthreads = utils.get_casa_session_details()['omp_num_threads']
            casa_tools.casalog.ompSetNumThreads(omp_num_threads)

        try:
            with utils.work_directory(self.output_dir, create=True, subdir=True, reraise_on_error=True):
                if not self.compare_only:
                    # run the pipeline for new results
                    if self.mode == 'regression':
                        if self.ppr:
                            self.__run_ppr(input_vis, telescope)
                        else:
                            LOG.warning("Running without Pipeline Processing Request (PPR). Using recipereducer instead.")
                            recipereducer.reduce(vis=input_vis, procedure=self.recipe)
                    elif self.mode == 'component':
                        recipereducer.run_named_tasks(self.tasks)

                # Do sanity checks
                self.__do_sanity_checks()

                # Copy the reference results file to current working directory for record
                if self.expectedoutput_file and os.path.exists(self.expectedoutput_file):
                    shutil.copyfile(self.expectedoutput_file, os.path.basename(self.expectedoutput_file))

                # Get new results
                new_results = self.__get_results_of_from_current_context()

                # new results file path
                if self.mode == 'component':
                    new_file = f'{self.output_dir}.NEW.results.txt'
                else:
                    new_file = f'{self.visname[0]}.NEW.results.txt'

                # Store new results in a file
                self.__save_new_results_to(new_file, new_results)

                # Compare new results with expected results
                self.__compare_results(new_file, default_relative_tolerance)

        finally:
            # clean up if requested
            self._cleanup()

        # restore the OpenMP nthreads to the value saved before the Pipeline reducer call.
        if not self.compare_only and omp_num_threads is not None:
            casa_tools.casalog.ompSetNumThreads(default_nthreads)

    def __compare_results(self, new_file: str, relative_tolerance: float) -> None:
        """
        Compare results between new one loaded from file and old one.

        Args:
            new_file : file path of new results
            relative_tolerance : relative tolerance of output value
        """
        with open(self.expectedoutput_file) as expected_fd, open(new_file) as new_fd:
            expected_results = expected_fd.readlines()
            new_results = new_fd.readlines()
            errors = []
            worst_diff = (0, 0)
            worst_percent_diff = (0, 0)
            for old, new in zip(expected_results, new_results):
                try:
                    oldkey, oldval, tol = self.__sanitize_results_string(old)
                    newkey, newval, _ = self.__sanitize_results_string(new)
                except ValueError as e:
                    errorstr = "The results: {0} could not be parsed. Error: {1}".format(new, str(e))
                    errors.append(errorstr)
                    continue

                assert oldkey == newkey, f"Expected key {oldkey} does not match new key {newkey}."
                tolerance = tol if tol else relative_tolerance
                if newval is not None:
                    LOG.info('Comparing %s to %s with a rel. tolerance of %s', oldval, newval, tolerance)
                    if oldval != pytest.approx(newval, rel=tolerance):
                        diff = oldval-newval
                        percent_diff = (oldval-newval)/oldval * 100 if oldval != 0 else 100
                        if abs(diff) > abs(worst_diff[0]):
                            worst_diff = diff, oldkey
                        if abs(percent_diff) > abs(worst_percent_diff[0]):
                            worst_percent_diff = percent_diff, oldkey
                        errorstr = f"{oldkey}\n\tvalues differ by > a relative difference of {tolerance}\n\texpected: {oldval}\n\tnew:      {newval}\n\tdiff: {diff}\n\tpercent_diff: {percent_diff}%"
                        errors.append(errorstr)
                elif oldval is not None:
                    # If only the new value is None, fail
                    errorstr = f"{oldkey}\n\tvalue is None\n\texpected: {oldval}\n\tnew:      {newval}"
                    errors.append(errorstr)
                else:
                    # If old and new values are both None, this is expected, so pass
                    LOG.info('Comparing %s and %s... both values are None.', oldval, newval)

            [LOG.warning(x) for x in errors]
            n_errors = len(errors)
            if n_errors > 0:
                summary_str = f"Worst absolute diff, {worst_diff[1]}: {worst_diff[0]}\nWorst percentage diff, {worst_percent_diff[1]}: {worst_percent_diff[0]}%"
                errors.append(summary_str)
                pytest.fail("Failed to match {0} result value{1} within tolerance{1} :\n{2}".format(
                    n_errors, '' if n_errors == 1 else 's', '\n'.join(errors)), pytrace=True)

    def __save_new_results_to(self, new_file: str, new_results: list[str]) -> None:
        """
        Compare results between new one and old one, both results are loaded from specified files.

        Args:
            new_file : file path of new results to save
            new_results : a list of new results
        """
        with open(new_file, 'w') as fd:
            fd.writelines([str(x) + '\n' for x in new_results])

    def __get_results_of_from_current_context(self) -> list[str]:
        """
        Get results of current execution from context.

        Returns: a list of new results
        """
        context = launcher.Pipeline(context='last').context
        new_results = sorted(regression.extract_regression_results(context))
        return new_results

    def __do_sanity_checks(self):
        """
        Do the following sanity-checks on the pipeline run

        1. rawdata, working, products directories are present
        2. *.pipeline_manifest.xml is present under the products directory
        3. Non-existence of errorexit-*.txt in working directory
        """
        context = launcher.Pipeline(context='last').context

        # 1. rawdata, working, products directories are present
        # The rawdata directory is only present for PPR runs
        missing_directories = regression.missing_directories(context, include_rawdata=self.ppr)
        if len(missing_directories) > 0:
            msg = f"The following directories are missing from the pipeline run: {', '.join(missing_directories)}"
            LOG.warning(msg)
            pytest.fail(msg)

        # 2. Non-existence of errorexit-*.txt in working directory
        if regression.errorexit_present(context):
            msg = "errorexit-*.txt is present in working directory"
            LOG.warning(msg)
            pytest.fail(msg)

        # 3. *pipeline_manifest.xml is present under the products directory; regression mode only
        if self.mode == 'regression':
            if not regression.manifest_present(context):
                msg = "pipeline_manifest.xml is not present under the products directory"
                LOG.warning(msg)
                pytest.fail(msg)

    def __run_ppr(self, input_vis: list[str], telescope: str) -> None:
        """Execute the recipe defined by PPR.

        Args:
            input_vis : relative path of MSes (`input_dir`+`visname`)
            telescope : string 'alma' or 'vla'

        NOTE: this private method is expected be called under "working/"
        """

        # executeppr expects the rawdata in ../rawdata
        for vis in input_vis:
            os.symlink(vis, f'../rawdata/{os.path.basename(vis)}')

        # save a copy of PPR in the directory one level above "working/".
        ppr_path = casa_tools.utils.resolve(self.ppr)
        ppr_local = f'../{os.path.basename(ppr_path)}'
        shutil.copyfile(ppr_path, ppr_local)

        if telescope == 'alma':
            executeppr.executeppr(ppr_local, importonly=False)
        elif telescope == 'vla':
            executevlappr.executeppr(ppr_local, importonly=False)
        else:
            LOG.error("Telescope is not 'alma' or 'vla'. Can't run executeppr.")

    def _cleanup(self):
        """Cleans up the working directory if it exists."""
        if not self.compare_only and self.remove_workdir and os.path.isdir(self.output_dir):
            try:
                shutil.rmtree(self.output_dir)
                LOG.info("Removing working directory %s as requested.", self.output_dir)
            except FileNotFoundError:
                LOG.debug("Working directory %s already removed before cleanup.", self.output_dir)
            except OSError as exc:
                LOG.warning("Failed to remove working directory %s: %s", self.output_dir, exc)
