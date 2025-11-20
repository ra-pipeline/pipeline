"""
Pipeline Regression framework.

PipelineRegression class runs on pytest framework, so it needs to implement
test_* methods for testing.
"""
from __future__ import annotations

import ast
import shutil
import datetime
import glob
import os
import packaging.version
import platform
import pytest
import re
from typing import TYPE_CHECKING, Optional

from casatasks.private import tec_maps

from pipeline import environment, infrastructure, recipereducer
from pipeline.infrastructure import casa_tools, executeppr, executevlappr, launcher, utils
from pipeline.infrastructure.renderer import regression

if TYPE_CHECKING:
    from packaging.version import Version

LOG = infrastructure.logging.get_logger(__name__)


class PipelineRegression:
    regex_casa_pattern = re.compile(r'.*casa-([\d.]+(?:-\d+)?)')
    regex_pipeline_pattern = re.compile(r'.*pipeline-([\d.]+(?:\.\d+)*\d)(?=\b|[-_]|$)')

    def __init__(
            self,
            visname: list[str],
            ppr: Optional[str] = None,
            recipe: Optional[str] = None,
            project_id: Optional[str] = None,
            input_dir: Optional[str] = None,
            output_dir: Optional[str] = None,
            expectedoutput_file: Optional[str] = None,
            expectedoutput_dir: Optional[str] = None
            ):
        """
        Initializes a PipelineRegression instance.

        A list of MeasurementSet names (`visname`) is required. Either `ppr` or `recipe` must be provided;
        if both are given, `ppr` takes precedence.

        Args:
            visname: List of MeasurementSets used for testing.
            ppr: Path to the PPR file. Takes precedence over `recipe` if both are provided.
            recipe: Path to the recipe XML file.
            project_id: Project ID. If provided, it is prefixed to the `output_dir` name.
            input_dir: Path to the directory containing input files.
            output_dir: Path to the output directory. If `None`, it is derived using `visname` and/or `project_id`.
            expectedoutput_file: Path to a file defining the expected test output. Overrides `expectedoutput_dir` if set.
            expectedoutput_dir: Path to a directory containing expected output files. Ignored if `expectedoutput_file` is set.

        Raises:
            ValueError: If neither `ppr` nor `recipe` is provided.
        """
        self.visname = visname
        if not recipe and not ppr:
            raise ValueError("At least one of recipe or ppr must be provided.")
        self.ppr = ppr
        self.recipe = recipe
        self.project_id = project_id
        self.input_dir = input_dir
        if output_dir:
            self.output_dir = output_dir
        elif self.project_id:
            self.output_dir = f'{self.project_id}__{self.visname[0]}_test_output'
        else:
            self.output_dir = f'{self.visname[0]}_test_output'
        if expectedoutput_file:
            self.expectedoutput_file = casa_tools.utils.resolve(expectedoutput_file)
        else:
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

    def _pick_results_file(self, reference_data_files: list[str]) -> Optional[str]:
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

    def _results_file_heuristics(self, reference_dict: dict[str, dict[str, Version]]) -> Optional[str]:
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

    def __sanitize_regression_string(self, instring: str) -> tuple[str, str, Optional[float]]:
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
                "For the key: {}, value: {} cannot be converted to int/float/boolean/None.".format(keystring, value))

        try:
            tolerance = float(instring.split(':::')[-1].replace('\n', ''))
        except ValueError:
            tolerance = None

        return keystring, value, tolerance

    def run(self,
            telescope: str = 'alma',
            default_relative_tolerance: float = 1e-7,
            omp_num_threads: Optional[int] = None
            ) -> None:
        """
        Run test with PPR if supplied or recipereducer if no PPR and compared to expected results.

        The inputs and expected output are usually found in the pipeline data repository.

        Args:
            telescope: string 'alma' or 'vla'
            default_relative_tolerance: default relative tolerance of output value
            omp_num_threads: specify the number of OpenMP threads used for this regression test instance, regardless of
                             the default value of the current CASA session. An explicit setting could mitigate potential small
                             numerical difference from threading-sensitive CASA tasks (e.g. setjy/tclean, which relies
                             on the FFTW library).

        note: Because a PL execution depends on global CASA states, only one test can run under
        a CASA process at the same. Therefore a parallelization based on process-forking might not work
        properly (e.g., xdist: --forked).  However, it's okay to group tests under several independent
        subprocesses (e.g., xdist: -n 4)

        """
        # Run the Pipeline using cal+imag ALMA IF recipe
        # set datapath in ~/.casa/config.py, e.g. datapath = ['/users/jmasters/pl-testdata.git']
        input_vis = [casa_tools.utils.resolve(testinput) for testinput in self.testinput]

        if not self.compare_only:
            # optionally set OpenMP nthreads to a specified value.
            if omp_num_threads is not None:
                # casa_tools.casalog.ompGetNumThreads() and get_casa_session_details()['omp_num_threads'] are equivalent.
                default_nthreads = utils.get_casa_session_details()['omp_num_threads']
                casa_tools.casalog.ompSetNumThreads(omp_num_threads)

            last_casa_logfile = casa_tools.casalog.logfile()

        try:
            # run the pipeline for new results

            # switch from the pytest-call working directory to the root folder for this test.
            os.chdir(self.output_dir)

            if not(self.compare_only):
                # create the sub-directory structure for this test and switch to "working/"
                dd_list = ['products', 'working', 'rawdata'] if self.ppr else ['products', 'working']
                for dd in dd_list:
                    try:
                        os.mkdir(dd)
                    except FileExistsError:
                        pass
                os.chdir('working')

                # PIPE-1301: shut down the existing plotms process to avoid side-effects from changing CWD.
                # This is implemented as a workaround for CAS-13626
                utils.shutdown_plotms()

                # PIPE-1432: reset casatasks/tec_maps.workDir as it's unaware of a CWD change.
                if hasattr(tec_maps, 'workDir'):
                    tec_maps.workDir = os.getcwd()+'/'

                # switch to per-test casa/PL logfile paths and backup the default(initial) casa logfile name
                self.__reset_logfiles(prepend=True)

                if self.ppr:
                    self.__run_ppr(input_vis, self.ppr, telescope)
                else:
                    self.__run_reducer(input_vis)
            else:
                os.chdir('working')

            # Do sanity checks
            self.__do_sanity_checks()

            # Get new results
            new_results = self.__get_results_of_from_current_context()

            # new results file path
            new_file = f'{self.visname[0]}.NEW.results.txt'

            # Store new results in a file
            self.__save_new_results_to(new_file, new_results)

            # Compare new results with expected results
            self.__compare_results(new_file, default_relative_tolerance)

        finally:
            if not self.compare_only:
                # restore the default logfile state
                self.__reset_logfiles(casa_logfile=last_casa_logfile)

            os.chdir(self.current_path)

            # clean up if requested
            if not self.compare_only and self.remove_workdir and os.path.isdir(self.output_dir):
                shutil.rmtree(self.output_dir)

        # restore the OpenMP nthreads to the value saved before the Pipeline ppr/reducer call.
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
                    oldkey, oldval, tol = self.__sanitize_regression_string(old)
                    newkey, newval, _ = self.__sanitize_regression_string(new)
                except ValueError as e:
                    errorstr = "The results: {0} could not be parsed. Error: {1}".format(new, str(e))
                    errors.append(errorstr)
                    continue

                assert oldkey == newkey
                tolerance = tol if tol else relative_tolerance
                if newval is not None:
                    LOG.info(f'Comparing {oldval} to {newval} with a rel. tolerance of {tolerance}')
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
                    LOG.info(f'Comparing {oldval} and {newval}... both values are None.')

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

        # 2. *pipeline_manifest.xml is present under the products directory
        if not regression.manifest_present(context):
            msg = "pipeline_manifest.xml is not present under the products directory"
            LOG.warning(msg)
            pytest.fail(msg)

        # 3. Non-existence of errorexit-*.txt in working directory
        if regression.errorexit_present(context):
            msg = "errorexit-*.txt is present in working directory"
            LOG.warning(msg)
            pytest.fail(msg)

    def __run_ppr(self, input_vis: list[str], ppr: str, telescope: str) -> None:
        """
        Execute the recipe defined by PPR.

        Args:
            input_vis : MS name
            ppr : PPR file name
            telescope : string 'alma' or 'vla'

        note: this private method is expected be called under "working/"
        """

        # executeppr expects the rawdata in ../rawdata
        for vis in input_vis:
            os.symlink(vis, f'../rawdata/{os.path.basename(vis)}')

        # save a copy of PPR in the directory one level above "working/".
        ppr_path = casa_tools.utils.resolve(ppr)
        ppr_local = f'../{os.path.basename(ppr_path)}'
        shutil.copyfile(ppr_path, ppr_local)

        if telescope == 'alma':
            executeppr.executeppr(ppr_local, importonly=False)
        elif telescope == 'vla':
            executevlappr.executeppr(ppr_local, importonly=False)
        else:
            LOG.error("Telescope is not 'alma' or 'vla'. Can't run executeppr.")

    def __run_reducer(self, input_vis: list[str]) -> None:
        """
        Execute the recipe by recipereducer.

        Args:
            input_vis : MS name

        note: this private method is expected be called under "working/"
        """
        LOG.warning("Running without Pipeline Processing Request (PPR).  Using recipereducer instead.")
        recipereducer.reduce(vis=input_vis, procedure=self.recipe)

    def __reset_logfiles(self,
                         casacalls_logfile: Optional[str] = None,
                         casa_logfile: Optional[str] = None,
                         prepend: Optional[bool] = False
                         ) -> None:
        """Put CASA/Pipeline logfiles into the test working directory."""

        # reset casacalls-*.txt
        if casacalls_logfile is None:
            casacalls_logfile = 'casacalls-{!s}.txt'.format(platform.node().split('.')[0])
        else:
            casacalls_logfile = casacalls_logfile
        infrastructure.logging.get_logger('CASACALLS', stream=None, format='%(message)s', addToCasaLog=False,
                           filename=casacalls_logfile)
        # reset casa-*.log
        if casa_logfile is None:
            now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
            casa_logfile = os.path.abspath(f'casa-{now_str}.log')
        else:
            casa_logfile = os.path.abspath(casa_logfile)
        last_casa_logfile = casa_tools.casalog.logfile()
        casa_tools.casalog.setlogfile(casa_logfile)

        # prepend the content of the last CASA logfile in the new logfile.
        if prepend and os.path.exists(last_casa_logfile) and casa_logfile != last_casa_logfile:
            with open(last_casa_logfile, 'r') as infile:
                with open(casa_logfile, 'a') as outfile:
                    outfile.write(infile.read())


# The methods below are test methods called from pytest.
@pytest.mark.fast
@pytest.mark.alma
def test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small__procedure_hifa_calimage__regression():
    """Run ALMA cal+image regression on a small test dataset.

    PPR:                        pl-regressiontest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small/PPR.xml
    Dataset:                    uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms
    """
    pr = PipelineRegression(
        visname=['uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms'],
        ppr='pl-regressiontest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small/PPR.xml',
        input_dir='pl-unittest',
        expectedoutput_dir='pl-regressiontest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small/'
        )

    pr.run()


@pytest.mark.fast
@pytest.mark.alma
def test_E2E6_1_00010_S__uid___A002_Xd0a588_X2239_regression():
    """Run ALMA cal+image regression on a 12m moderate-size test dataset in ASDM.

    Recipe name:                procedure_hifa_calimage
    Dataset:                    E2E6.1.00010.S: uid___A002_Xd0a588_X2239
    """

    input_dir = 'pl-regressiontest/E2E6.1.00010.S'
    ref_directory = 'pl-regressiontest/E2E6.1.00010.S'

    pr = PipelineRegression(
        visname=['uid___A002_Xd0a588_X2239'],
        recipe='procedure_hifa_calimage.xml',
        input_dir=input_dir,
        expectedoutput_dir=ref_directory
        )

    pr.run()


@pytest.mark.fast
@pytest.mark.alma
def test_uid___A002_Xc845c0_X7366_cycle5_restore_regression():
    """
    Restore from Cycle 5 (with current pipeline)

    Recipe name:                procedure_hifa_image
    Dataset:                    uid___A002_Xc845c0_X7366
    """

    input_dir = 'pl-regressiontest/uid___A002_Xc845c0_X7366'
    ref_directory = 'pl-regressiontest/uid___A002_Xc845c0_X7366'

    pr = PipelineRegression(
        visname=['uid___A002_Xc845c0_X7366'],
        recipe='procedure_hifa_image.xml',
        input_dir=input_dir,
        expectedoutput_dir=ref_directory
        )

    # copy files for the restore into products folder
    if not pr.compare_only:
        input_products = casa_tools.utils.resolve(f'{input_dir}/products')
        shutil.copytree(input_products, f'{pr.output_dir}/rawdata')

    pr.run()


@pytest.mark.fast
@pytest.mark.alma
def test_uid___A002_Xc46ab2_X15ae_selfcal_restore_regression():
    """Restore selfcal from Cycle 10 (with current pipeline)

    Recipe name:                procedure_hifa_image_selfcal
    Dataset:                    uid___A002_Xc46ab2_X15ae
    """

    input_dir = 'pl-regressiontest/uid___A002_Xc46ab2_X15ae_selfcal_restore'
    ref_directory = 'pl-regressiontest/uid___A002_Xc46ab2_X15ae_selfcal_restore'

    pr = PipelineRegression(
        visname=['uid___A002_Xc46ab2_X15ae'],
        recipe='procedure_hifa_image.xml',
        input_dir=input_dir,
        expectedoutput_dir=ref_directory
        )

    # copy files into products folder for restore
    if not pr.compare_only:
        input_products = casa_tools.utils.resolve(f'{input_dir}/products')
        shutil.copytree(input_products, f'{pr.output_dir}/rawdata')

    pr.run()


@pytest.mark.fast
@pytest.mark.alma
def test_uid___A002_Xef72bb_X9d29_renorm_restore_regression():
    """Restore renorm from Cycle 8 (with current pipeline)

    Recipe name:                procedure_hifa_image
    Dataset:                    uid___A002_Xef72bb_X9d29
    """

    input_dir = 'pl-regressiontest/uid___A002_Xef72bb_X9d29'
    ref_directory = 'pl-regressiontest/uid___A002_Xef72bb_X9d29'

    pr = PipelineRegression(
        visname=['uid___A002_Xef72bb_X9d29'],
        recipe='procedure_hifa_image.xml',
        input_dir=input_dir,
        expectedoutput_dir=ref_directory
        )

    # copy files into products folder for restore
    if not pr.compare_only:
        input_products = casa_tools.utils.resolve(f'{input_dir}/products')
        shutil.copytree(input_products, f'{pr.output_dir}/rawdata')

    pr.run()


@pytest.mark.fast
@pytest.mark.alma
def test_uid___A002_X85c183_X36f__procedure_hsd_calimage__regression():
    """Run ALMA single-dish cal+image regression on the obseration data of M100.

    Recipe name:                procedure_hsd_calimage
    Dataset:                    uid___A002_X85c183_X36f
    """
    input_dir = 'pl-regressiontest/uid___A002_X85c183_X36f'

    pr = PipelineRegression(
        visname=['uid___A002_X85c183_X36f'],
        recipe='procedure_hsd_calimage.xml',
        input_dir=input_dir,
        expectedoutput_dir=input_dir
    )

    pr.run()


@pytest.mark.fast
@pytest.mark.alma
def test_uid___A002_X85c183_X36f_SPW15_23__PPR__regression():
    """Run ALMA single-dish restoredata regression on the observation data of M100.

    Dataset:                    uid___A002_X85c183_X36f_SPW15_23
    """
    input_dir = 'pl-regressiontest/uid___A002_X85c183_X36f_SPW15_23'

    pr = PipelineRegression(
        visname=['uid___A002_X85c183_X36f_SPW15_23.ms'],
        ppr=f'{input_dir}/PPR.xml',
        input_dir=input_dir,
        expectedoutput_dir=input_dir
    )

    # copy files use restore task into products folder
    if not pr.compare_only:
        input_products = casa_tools.utils.resolve(f'{input_dir}/products')
        shutil.copytree(input_products, f'{pr.output_dir}/products')

    pr.run()


@pytest.mark.fast
@pytest.mark.alma
def test_uid___mg2_20170525142607_180419__procedure_hsdn_calimage__regression():
    """Run ALMA single-dish cal+image regression for standard nobeyama recipe.

    Recipe name:                procedure_hsdn_calimage
    Dataset:                    mg2-20170525142607-180419
    """
    input_dir = 'pl-regressiontest/mg2-20170525142607-180419'

    pr = PipelineRegression(
        visname=['mg2-20170525142607-180419.ms'],
        recipe='procedure_hsdn_calimage.xml',
        input_dir=input_dir,
        expectedoutput_dir=input_dir
    )
    pr.run()


@pytest.mark.fast
@pytest.mark.alma
def test_uid___mg2_20170525142607_180419__PPR__regression():
    """Run ALMA single-dish cal+image regression for restore nobeyama recipe.

    Dataset:                    mg2-20170525142607-180419
    """

    input_dir = 'pl-regressiontest/mg2-20170525142607-180419_PPR'

    pr = PipelineRegression(
        visname=['mg2-20170525142607-180419.ms'],
        ppr=f'{input_dir}/PPR.xml',
        input_dir=input_dir,
        expectedoutput_dir=input_dir,
        output_dir='mg2-20170525142607-180419_PPR')

    # copy files use restore task into products folder
    if not pr.compare_only:
        input_products = casa_tools.utils.resolve(f'{input_dir}/products')
        shutil.copytree(input_products, f'{pr.output_dir}/products')

    pr.run()


@pytest.mark.fast
@pytest.mark.alma
def test_csv_3899_eb2_small__procedure_hifa_calimage__regression():
    """PIPE-2245: Run small ALMA cal+image regression to cover various heuristics

    Dataset:                    CSV-3899-EB2-small
    """

    input_dir = 'pl-regressiontest/CSV-3899-EB2-small'

    pr = PipelineRegression(recipe='procedure_hifa_calimage.xml',
                            input_dir=input_dir,
                            visname=['uid___A002_X1181695_X1c6a4_8ant.ms'],
                            expectedoutput_dir=input_dir,
                            output_dir='csv_3899_eb2_small')

    pr.run(omp_num_threads=1)


@pytest.mark.skip(reason="Recent failure needs longer investigation")
@pytest.mark.alma
def test_uid___A002_Xee1eb6_Xc58d_pipeline__procedure_hifa_calsurvey__regression():
    """Run ALMA cal+survey regression on a calibration survey test dataset

    Recipe name:                procedure_hifa_calsurvey
    Dataset:                    uid___A002_Xee1eb6_Xc58d_original.ms
    """
    input_directory = 'pl-regressiontest/uid___A002_Xee1eb6_Xc58d_calsurvey/'
    pr = PipelineRegression(
        visname=['uid___A002_Xee1eb6_Xc58d_original.ms'],
        recipe='procedure_hifa_calsurvey.xml',
        input_dir=input_directory,
        expectedoutput_dir=input_directory,
        output_dir='uid___A002_Xee1eb6_Xc58d_calsurvey_output'
        )

    pr.run()


@pytest.mark.vla
@pytest.mark.fast
def test_13A_537__procedure_hifv__regression():
    """Run VLA calibration regression for standard procedure_hifv.xml recipe.

    Recipe name:                procedure_hifv
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    """

    input_dir = 'pl-regressiontest/13A-537'
    pr = PipelineRegression(
        visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
        recipe='procedure_hifv.xml',
        input_dir=input_dir,
        expectedoutput_dir=input_dir,
        output_dir='13A_537__procedure_hifv__regression'
        )

    pr.run(telescope='vla', omp_num_threads=1)


@pytest.mark.vla
@pytest.mark.fast
def test_13A_537__calibration__PPR__regression():
    """Run VLA calibration regression with a PPR file.

    PPR name:                   PPR_13A-537.xml
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    """

    input_dir = 'pl-regressiontest/13A-537'

    pr = PipelineRegression(
        visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
        ppr=f'{input_dir}/PPR_13A-537.xml',
        input_dir=input_dir,
        expectedoutput_dir=input_dir,
        output_dir='13A_537__calibration__PPR__regression'
        )

    pr.run(telescope='vla', omp_num_threads=1)


@pytest.mark.vla
@pytest.mark.fast
def test_13A_537__restore__PPR__regression():
    """Run VLA calibration restoredata regression with a PPR file
    NOTE: results file frozen to CASA/Pipeline version below since products were created
    with that Pipeline version

    PPR name:                   PPR_13A-537_restore.xml
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    Expected results version:   casa-6.2.1.7-pipeline-2021.2.0.128
    """
    input_dir = 'pl-regressiontest/13A-537'
    pr = PipelineRegression(
        visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
        ppr=f'{input_dir}/PPR_13A-537_restore.xml',
        input_dir=input_dir,
        expectedoutput_file=f'{input_dir}/restore/' +
                             '13A-537.casa-6.2.1.7-pipeline-2021.2.0.128.restore.results.txt',
        output_dir='13A_537__restore__PPR__regression'
        )

    # copy files use restore task into products folder
    if not pr.compare_only:
        input_products = casa_tools.utils.resolve(f'{input_dir}/products')
        shutil.copytree(input_products, f'{pr.output_dir}/products')

    pr.run(telescope='vla')


@pytest.mark.vla
@pytest.mark.fast
def test_13A_537__restore__post1553__PPR__regression():
    """Run VLA calibration restoredata regression with a PPR file

    PPR name:                   PPR_13A-537_restore.xml
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    """
    input_dir = 'pl-regressiontest/13A-537'
    pr = PipelineRegression(
        visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
        ppr=f'{input_dir}/PPR_13A-537_restore.xml',
        input_dir=input_dir,
        expectedoutput_dir=f'{input_dir}/restore/',
        output_dir='13A_537__restore__post1553__PPR__regression'
        )

    # copy files use restore task into products folder
    if not pr.compare_only:
        input_products = casa_tools.utils.resolve(f'{input_dir}/post1553_products')
        shutil.copytree(input_products, f'{pr.output_dir}/products')

    pr.run(telescope='vla')


@pytest.mark.vlass
@pytest.mark.fast
def test_vlass_quicklook():
    """Run VLASS quicklook regression

    Recipe name: procedure_vlassQLIP.xml
    Dataset: TSKY0001.sb32295801.eb32296475.57549.31722762731_split_withcorrectdata.ms
    """

    input_dir = 'pl-regressiontest/vlass_quicklook'
    ref_directory = 'pl-regressiontest/vlass_quicklook'

    pr = PipelineRegression(
        visname=['TSKY0001.sb32295801.eb32296475.57549.31722762731_split_withcorrectdata.ms'],
        recipe='procedure_vlassQLIP.xml',
        input_dir=input_dir,
        expectedoutput_dir=ref_directory
        )

    # Copy parameter list file into the working directory

    try:
        os.mkdir(f'{pr.output_dir}/working/')
    except FileExistsError:
        pass
    if not pr.compare_only:
        parameter_list_file = casa_tools.utils.resolve(
            f'{input_dir}/TSKY0001.sb32295801.eb32296475.57549.31722762731_split_QLIP_parameter.list')
        shutil.copyfile(parameter_list_file, casa_tools.utils.resolve(f'{pr.output_dir}/working/QLIP_parameter.list'))
    pr.run(telescope='vla')


# Section for longer-running tests
@pytest.fixture(autouse=True)
def data_directory(scope="module") -> str:
    if hasattr(pytest, 'pytestconfig'):
        big_data_dir = pytest.pytestconfig.getoption('--data-directory')
    else:
        big_data_dir = "/lustre/cv/projects/pipeline-test-data/regression-test-data/"

    if not os.path.exists(big_data_dir):
        print("Warning! The large dataset directory {} does not exist, so any long-running tests will fail.".format(big_data_dir))
    else:
        print("Using: {} for data directory".format(big_data_dir))
    return big_data_dir


def setup_flux_antennapos(test_directory, output_dir):
    # Copy flux.csv and antennapos.csv into the working directory
    flux_file = casa_tools.utils.resolve(f'{test_directory}/flux.csv')
    anteannapos_file = casa_tools.utils.resolve(f'{test_directory}/antennapos.csv')

    try:
        os.mkdir(f'{output_dir}/working/')
    except FileExistsError:
        pass

    shutil.copyfile(flux_file, casa_tools.utils.resolve(f'{output_dir}/working/flux.csv'))
    shutil.copyfile(anteannapos_file, casa_tools.utils.resolve(f'{output_dir}/working/antennapos.csv'))


@pytest.mark.slow
class TestSlowerRegression:

    # ALMA-section
    @pytest.mark.alma
    @pytest.mark.twelve
    def test_2019_1_01094_S__uid___A002_Xecbc07_X6b0e_PPR__regression(self, data_directory):
        """Run longer regression test on this ALMA if dataset

        Dataset: 2019.1.01094.S: uid___A002_Xecbc07_X6b0e, uid___A002_Xecf7c7_X1d83
        """
        test_directory = f'{data_directory}/alma_if/2019.1.01094.S/'
        ref_directory = 'pl-regressiontest/2019.1.01094.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xecbc07_X6b0e', 'uid___A002_Xecf7c7_X1d83'],
            ppr=(test_directory + 'PPR.xml'),
            input_dir=test_directory,
            project_id="2019_1_01094_S",
            expectedoutput_dir=ref_directory
            )

        setup_flux_antennapos(test_directory, pr.output_dir)

        pr.run()

    @pytest.mark.alma
    @pytest.mark.twelve
    def test_E2E9_1_00061_S__uid___A002_Xfd764e_X5843_regression(self, data_directory):
        """Run longer regression test on this ALMA if dataset

        Dataset: E2E9.1.00061.S: uid___A002_Xfd764e_X5843, uid___A002_Xfd764e_X60e2
        """
        test_directory = f'{data_directory}/alma_if/E2E9.1.00061.S/'
        ref_directory = 'pl-regressiontest/E2E9.1.00061.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xfd764e_X5843', 'uid___A002_Xfd764e_X60e2'],
            ppr=(test_directory + 'PPR.xml'),
            input_dir=test_directory,
            project_id="E2E9_1_00061_S",
            expectedoutput_dir=ref_directory
            )

        setup_flux_antennapos(test_directory, pr.output_dir)

        pr.run()

    @pytest.mark.alma
    @pytest.mark.twelve
    def test_2018_1_01255_S__uid___A002_Xe0e4ca_Xb18_regression(self, data_directory):
        """Run longer regression test on this ALMA if dataset

        Dataset: 2018.1.01255.S: uid___A002_Xe0e4ca_Xb18, uid___A002_Xeb9695_X2fe5
        """
        test_directory = f'{data_directory}/alma_if/2018.1.01255.S/'
        ref_directory = 'pl-regressiontest/2018.1.01255.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xe0e4ca_Xb18', 'uid___A002_Xeb9695_X2fe5'],
            ppr=(test_directory + 'PPR.xml'),
            input_dir=test_directory,
            project_id="2018_1_01255_S",
            expectedoutput_dir=ref_directory
            )

        setup_flux_antennapos(test_directory, pr.output_dir)

        pr.run()

    @pytest.mark.alma
    @pytest.mark.twelve
    def test_2017_1_00912_S__uid___A002_Xc74b5b_X316a_regression(self, data_directory):
        """Run longer regression test on this ALMA if dataset

        Dataset: 2017.1.00912.S: uid___A002_Xe6a684_X7c41
        """
        test_directory = f'{data_directory}/alma_if/2017.1.00912.S/'
        ref_directory = 'pl-regressiontest/2017.1.00912.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xc74b5b_X316a'],
            ppr=(test_directory + 'PPR.xml'),
            input_dir=test_directory,
            project_id="2017_1_00912_S",
            expectedoutput_dir=ref_directory
            )

        setup_flux_antennapos(test_directory, pr.output_dir)
        pr.run()

    @pytest.mark.alma
    @pytest.mark.twelve
    def test_2019_1_01184_S__uid___A002_Xe1d2cb_X12782_regression(self, data_directory):
        """Run longer regression test on this ALMA if dataset

        Dataset: 2019_1_01184_S: uid___A002_Xe1d2cb_X12782, uid___A002_Xe850fb_X4efc
        """
        test_directory = f'{data_directory}/alma_if/2019.1.01184.S/'
        ref_directory = 'pl-regressiontest/2019.1.01184.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xe1d2cb_X12782', 'uid___A002_Xe850fb_X4efc'],
            ppr=(test_directory + 'PPR.xml'),
            input_dir=test_directory,
            project_id="2019_1_01184_S",
            expectedoutput_dir=ref_directory
            )

        setup_flux_antennapos(test_directory, pr.output_dir)
        pr.run()

    @pytest.mark.alma
    @pytest.mark.twelve
    def test_2019_1_00678_S__uid___A002_Xe6a684_X7c41__PPR__regression(self, data_directory):
        """Run longer regression test on this ALMA if dataset

        Dataset: 2019.1.00678.S: uid___A002_Xe6a684_X7c41
        """
        test_directory = f'{data_directory}/alma_if/2019.1.00678.S/'
        ref_directory =  'pl-regressiontest/2019.1.00678.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xe6a684_X7c41'],
            ppr=(test_directory + 'PPR.xml'),
            input_dir=test_directory,
            project_id="2019_1_00678_S",
            expectedoutput_dir=ref_directory
            )

        setup_flux_antennapos(test_directory, pr.output_dir)
        pr.run()

    @pytest.mark.alma
    @pytest.mark.twelve
    def test_2017_1_00670_S__uid___A002_Xca8fbf_X5733__PPR__regression(self, data_directory):
        """Run longer regression test on this ALMA if dataset

        Dataset: 2017.1.00670.S: uid___A002_Xca8fbf_X5733
        """
        test_directory = f'{data_directory}/alma_if/2017.1.00670.S/'
        ref_directory =  'pl-regressiontest/2017.1.00670.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xca8fbf_X5733'],
            ppr=(test_directory + 'PPR.xml'),
            input_dir = test_directory,
            project_id='2017_1_00670_S',
            expectedoutput_dir=ref_directory
            )

        setup_flux_antennapos(test_directory, pr.output_dir)
        pr.run()

    @pytest.mark.alma
    @pytest.mark.seven
    def test_2019_1_00847_S__uid___A002_Xe1f219_X1457_regression(self, data_directory):
        """Run longer regression test on this ALMA if dataset
        ALMA 7m

        Dataset: 2019.1.00847.S: uid___A002_Xe1f219_X1457, uid___A002_Xe1f219_X9dbf, uid___A002_Xe27761_X74f8
        """
        test_directory = f'{data_directory}/alma_if/2019.1.00847.S/'
        ref_directory = 'pl-regressiontest/2019.1.00847.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xe1f219_X1457', 'uid___A002_Xe1f219_X9dbf', 'uid___A002_Xe27761_X74f8'],
            ppr=(test_directory + 'PPR.xml'),
            input_dir=test_directory,
            project_id="2019_1_00847_S",
            expectedoutput_dir=ref_directory
            )

        setup_flux_antennapos(test_directory, pr.output_dir)
        pr.run()

    @pytest.mark.alma
    @pytest.mark.seven
    def test_2019_1_00994_S__uid___A002_Xe44309_X7d94__PPR__regression(self, data_directory):
        """Run longer regression test on this ALMA IF dataset

        ALMA 7m

        Dataset: 2019.1.00994.S: uid___A002_Xe44309_X7d94, uid___A002_Xe45e29_X59ee, uid___A002_Xe45e29_X6666, uid___A002_Xe48598_X8697
        """
        test_directory = f'{data_directory}/alma_if/2019.1.00994.S/'
        ref_directory = 'pl-regressiontest/2019.1.00994.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xe44309_X7d94', 'uid___A002_Xe45e29_X59ee', 'uid___A002_Xe45e29_X6666', 'uid___A002_Xe48598_X8697'],
            ppr=(test_directory + 'PPR.xml'),
            input_dir=test_directory,
            project_id="2019_1_00994_S",
            expectedoutput_dir=ref_directory
            )

        setup_flux_antennapos(test_directory, pr.output_dir)
        pr.run()

    @pytest.mark.alma
    @pytest.mark.seven
    def test_2019_1_01056_S__uid___A002_Xe1f219_X6d0b__PPR__regression(self, data_directory):
        """Run longer regression test on this ALMA IF dataset

        ALMA 7m

        Dataset: 2019.1.01056.S: uid___A002_Xe1f219_X6d0bm, uid___A002_Xe1f219_X7ee8
        """
        test_directory = f'{data_directory}/alma_if/2019.1.01056.S/'
        ref_directory = 'pl-regressiontest/2019.1.01056.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xe1f219_X6d0b', 'uid___A002_Xe1f219_X7ee8'],
            ppr=(test_directory + 'PPR.xml'),
            input_dir=test_directory,
            project_id="2019_1_01056_S",
            expectedoutput_dir=f'{ref_directory}'
            )

        setup_flux_antennapos(test_directory, pr.output_dir)
        pr.run()

    # SD Section
    @pytest.mark.alma
    @pytest.mark.sd
    def test_2019_2_00093_S__uid___A002_Xe850fb_X2df8_regression(self, data_directory):
        """Run longer regression test on this ALMA SD dataset

        Recipe name: procedure_hsd_calimage
        Dataset: 2019.2.00093.S: uid___A002_Xe850fb_X2df8, uid___A002_Xe850fb_X36e4, uid___A002_Xe850fb_X11e13
        """
        test_directory = f'{data_directory}/alma_sd/2019.2.00093.S/'
        ref_directory = 'pl-regressiontest/2019.2.00093.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xe850fb_X2df8', 'uid___A002_Xe850fb_X36e4', 'uid___A002_Xe850fb_X11e13'],
            recipe='procedure_hsd_calimage.xml',
            input_dir=test_directory,
            project_id="2019_2_00093_S",
            expectedoutput_dir=ref_directory
            )

        pr.run()

    @pytest.mark.alma
    @pytest.mark.sd
    def test_2019_1_01056_S__uid___A002_Xe1d2cb_X110f1_regression(self, data_directory):
        """Run weekly regression test on this ALMA SD dataset

        Recipe name: procedure_hsd_calimage
        Dataset: 2019.1.01056.S: uid___A002_Xe1d2cb_X110f1, uid___A002_Xe1d2cb_X11d0a, uid___A002_Xe1f219_X6eeb
        """
        test_directory = f'{data_directory}/alma_sd/2019.1.01056.S/'
        ref_directory = 'pl-regressiontest/2019.1.01056.S/'

        pr = PipelineRegression(
            visname=['uid___A002_Xe1d2cb_X110f1', 'uid___A002_Xe1d2cb_X11d0a', 'uid___A002_Xe1f219_X6eeb'],
            recipe='procedure_hsd_calimage.xml',
            input_dir=test_directory,
            project_id="2019_1_01056_S",
            expectedoutput_dir=f'{ref_directory}'
            )

        setup_flux_antennapos(test_directory, pr.output_dir)
        pr.run()

    @pytest.mark.alma
    @pytest.mark.sd
    def test_2016_1_01489_T__uid___A002_Xbadc30_X43ee_regression(self, data_directory):
        """Run weekly regression test on this ALMA SD dataset

        Recipe name: procedure_hsd_calimage
        Dataset: 2016.1.01489.T: uid___A002_Xbadc30_X43ee, uid___A002_Xbaedce_X7694
        """
        test_directory = f'{data_directory}/alma_sd/2016.1.01489.T/'
        ref_directory = 'pl-regressiontest/2016.1.01489.T/'

        pr = PipelineRegression(
            visname=['uid___A002_Xbadc30_X43ee', 'uid___A002_Xbaedce_X7694'],
            recipe='procedure_hsd_calimage.xml',
            input_dir=test_directory,
            project_id="2016_1_01489_T",
            expectedoutput_dir=ref_directory
            )

        pr.run()

    # VLA Section
    @pytest.mark.vla
    def test_13A_537__procedure_hifv_calimage__regression(self, data_directory):
        """Run VLA calibration regression for standard procedure_hifv_calimage_cont recipe.

        Recipe name:                procedure_hifv_calimage_cont
        Dataset:                    13A-537.sb24066356.eb24324502.56514.05971091435
        """
        dataset_name = '13A-537.sb24066356.eb24324502.56514.05971091435'
        input_dir = 'pl-regressiontest/13A-537/'
        ref_directory = 'pl-regressiontest/13A-537/'

        pr = PipelineRegression(
            visname=[dataset_name],
            recipe='procedure_hifv_calimage_cont.xml',
            input_dir=input_dir,
            expectedoutput_dir=ref_directory
            )

        pr.run(telescope='vla', omp_num_threads=1)

    @pytest.mark.vla
    def test_15B_342__procedure_hifv__regression(self, data_directory):
        """Run VLA calibration regression for standard recipe.

        Recipe name:                procedure_hifv_calimage_cont
        Dataset:                    15B-342.sb31041443.eb31041910.57246.076202627315
        """
        dataset_name = '15B-342.sb31041443.eb31041910.57246.076202627315'
        input_dir = f'{data_directory}/vla/15B-342/'
        ref_directory = 'pl-regressiontest/15B-342/'

        pr = PipelineRegression(
            visname=[dataset_name],
            recipe='procedure_hifv_calimage_cont.xml',
            input_dir=input_dir,
            expectedoutput_dir=ref_directory
            )

        pr.run(telescope='vla', omp_num_threads=1)

    @pytest.mark.vla
    def test_17B_188__procedure_hifv__regression(self, data_directory):
        """Run VLA calibration regression for standard recipe.

        Recipe name:                procedure_hifv_calimage_cont
        Dataset:                    17B-188.sb35564398.eb35590549.58363.10481791667
        """
        dataset_name = '17B-188.sb35564398.eb35590549.58363.10481791667'
        input_dir = f'{data_directory}/vla/17B-188/'
        ref_directory = 'pl-regressiontest/17B-188/'

        pr = PipelineRegression(
            visname=[dataset_name],
            recipe='procedure_hifv_calimage_cont.xml',
            input_dir=input_dir,
            expectedoutput_dir=ref_directory
            )

        pr.run(telescope='vla', omp_num_threads=1)

    @pytest.mark.vla
    def test_18A_228__procedure_hifv__regression(self, data_directory):
        """Run VLA calibration regression for standard procedure_hifv_calimage_cont.xml recipe.

        Recipe name:                procedure_hifv_calimage_cont
        Dataset:                    18A-228.sb35538192.eb35676319.58412.135923414358
        """
        input_dir = f'{data_directory}/vla/18A-228/'
        ref_directory = 'pl-regressiontest/18A-228/'

        pr = PipelineRegression(
            visname=['18A-228.sb35538192.eb35676319.58412.13592341435'],
            recipe='procedure_hifv_calimage_cont.xml',
            input_dir=input_dir,
            expectedoutput_dir=ref_directory
            )

        pr.run(telescope='vla', omp_num_threads=1)

    @pytest.mark.vla
    def test_18A_426__procedure_hifv__regression(self, data_directory):
        """Run VLA calibration regression for standard procedure_hifv_calimage_cont.xml recipe.

        Recipe name:                procedure_hifv_calimage_cont
        Dataset:                    18A-426.sb35644955.eb35676220.58411.96917952546
        """
        input_dir = f'{data_directory}/vla/18A-426/'
        ref_directory = 'pl-regressiontest/18A-426/'

        pr = PipelineRegression(
            visname=['18A-426.sb35644955.eb35676220.58411.96917952546'],
            recipe='procedure_hifv_calimage_cont.xml',
            input_dir=input_dir,
            expectedoutput_dir=ref_directory
            )

        pr.run(telescope='vla', omp_num_threads=1)

    @pytest.mark.vla
    def test_21A_423__procedure_hifv__regression(self, data_directory):
        """Run VLA calibration regression for standard recipe.

        Recipe name:                procedure_hifv_calimage_cont
        Dataset:                    21A-423.sb39709588.eb40006153.59420.64362002315
        """
        dataset_name = '21A-423.sb39709588.eb40006153.59420.64362002315'
        input_dir = f'{data_directory}/vla/21A-423/'
        ref_directory = 'pl-regressiontest/21A-423/'

        pr = PipelineRegression(
            visname=[dataset_name],
            recipe='procedure_hifv_calimage_cont.xml',
            input_dir=input_dir,
            expectedoutput_dir=ref_directory
            )

        pr.run(telescope='vla', omp_num_threads=1)

    @pytest.mark.vla
    def test_13A_537__procedure_hifv__cont__cube__selfcal(self):
        """PIPE-2357: Run VLA calibration regression for standard procedure_hifv_calimage_cont_cube_selfcal.xml recipe.

        Recipe name:                procedure_hifv_calimage_cont_cube_selfcal.xml
        Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
        """

        input_dir = 'pl-regressiontest/13A-537'

        pr = PipelineRegression(recipe='procedure_hifv_calimage_cont_cube_selfcal.xml',
                                input_dir=input_dir,
                                visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
                                expectedoutput_dir=input_dir)

        pr.run(telescope='vla', omp_num_threads=1)

    # VLASS section
    @pytest.mark.vlass
    def test_vlass_se_cont_mosaic(self, data_directory):
        """Run VLASS regression

        Recipe name: procedure_vlassSEIP_cv.xml
        Dataset: VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms
        """
        dataset_name = 'VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms'
        input_dir = f'{data_directory}/vlass/se_cont_mosaic/'
        ref_directory = 'pl-regressiontest/vlass_se_cont_mosaic/'

        pr = PipelineRegression(
            visname=[dataset_name],
            recipe=f'{input_dir}/procedure_vlassSEIP_cv.xml',
            input_dir=input_dir,
            expectedoutput_dir=ref_directory
            )

        try:
            os.mkdir(f'{pr.output_dir}/working/')
        except FileExistsError:
            pass

        # Copy parameter list file into the working directory
        if not pr.compare_only:
            parameter_list_file = casa_tools.utils.resolve(f'{input_dir}/SEIP_parameter.list')
            shutil.copyfile(parameter_list_file, casa_tools.utils.resolve(
                f'{pr.output_dir}/working/SEIP_parameter.list'))

        pr.run(telescope='vla')

    @pytest.mark.vlass
    def test_vlass_se_cont_awp32(self, data_directory):
        """Run VLASS regression

        Recipe name: procedure_vlassSEIP_cv.xml
        Dataset: VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms
        """
        dataset_name = 'VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms'
        input_dir = f'{data_directory}/vlass/se_cont_awp32/'
        ref_directory = 'pl-regressiontest/vlass_se_cont_awp32/'

        pr = PipelineRegression(
            visname=[dataset_name],
            recipe=f'{input_dir}/procedure_vlassSEIP_cv.xml',
            input_dir=input_dir,
            expectedoutput_dir=ref_directory
            )


        try:
            os.mkdir(f'{pr.output_dir}/working/')
        except FileExistsError:
            pass

        # Copy parameter list file into the working directory
        if not pr.compare_only:
            parameter_list_file = casa_tools.utils.resolve(f'{input_dir}/SEIP_parameter_awp32.list')
            shutil.copyfile(parameter_list_file, casa_tools.utils.resolve(
                f'{pr.output_dir}/working/SEIP_parameter.list'))

        pr.run(telescope='vla')

    @pytest.mark.vlass
    def test_vlass_se_cube(self, data_directory):
        """Run VLASS regression

        Recipe name: procedure_vlassCCIP.xml
        Dataset: VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms
        """
        dataset_name = 'VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms'
        input_dir = f'{data_directory}/vlass/se_cube/'
        ref_directory = 'pl-regressiontest/vlass_se_cube/'

        pr = PipelineRegression(
            visname=[dataset_name],
            recipe='procedure_vlassCCIP.xml',
            input_dir=input_dir,
            expectedoutput_dir=ref_directory
            )

        try:
            os.mkdir(f'{pr.output_dir}/working/')
        except FileExistsError:
            pass

        # Copy parameter list files and reimaging resources into the working directory
        if not pr.compare_only:
            seip_parameter_list_file = casa_tools.utils.resolve(f'{input_dir}/SEIP_parameter.list')
            shutil.copyfile(seip_parameter_list_file, casa_tools.utils.resolve(
                f'{pr.output_dir}/working/SEIP_parameter.list'))

            ccip_parameter_list_file = casa_tools.utils.resolve(f'{input_dir}/CCIP_parameter_sg16.list')
            shutil.copyfile(ccip_parameter_list_file, casa_tools.utils.resolve(
                f'{pr.output_dir}/working/CCIP_parameter.list'))

            reimaging_resources_file = casa_tools.utils.resolve(f'{input_dir}/reimaging_resources.tgz')
            shutil.copyfile(reimaging_resources_file, casa_tools.utils.resolve(
                f'{pr.output_dir}/working/reimaging_resources.tgz'))

        pr.run(telescope='vla')

    @pytest.mark.vlass
    def test_vlass_cal(self, data_directory):
        """Run VLASS regression

        Recipe name: procedure_hifvcalvlass.xml
        Dataset: VLASS2.1.sb39020033.eb39038648.59173.7629213426
        """
        dataset_name = 'VLASS2.1.sb39020033.eb39038648.59173.7629213426'
        input_dir = f'{data_directory}/vlass/cal/'
        ref_directory = 'pl-regressiontest/vlass_cal'

        pr = PipelineRegression(
            visname=[dataset_name],
            recipe='procedure_hifvcalvlass.xml',
            input_dir=input_dir,
            expectedoutput_dir=ref_directory
            )

        pr.run(telescope='vla')
