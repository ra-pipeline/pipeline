"""
Pipeline Regression framework.

PipelineRegression class runs on pytest framework, so it needs to implement
test_* methods for testing. 
"""

import os
import shutil
import datetime
import platform
import pytest
from typing import Tuple, Optional, List

import casatasks.private.tec_maps as tec_maps 

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.casa_tools as casa_tools
import pipeline.recipereducer
from pipeline.infrastructure.renderer import regression
import pipeline.infrastructure.executeppr as almappr
import pipeline.infrastructure.executevlappr as vlappr
import pipeline.infrastructure.logging as logging
from pipeline.infrastructure.utils import shutdown_plotms, get_casa_session_details

LOG = infrastructure.get_logger(__name__)


class PipelineRegression(object):
    """Pipeline regression test class called from pytest."""

    def __init__(self, recipe: Optional[str] = None, input_dir: Optional[str] = None, visname: Optional[str] = None,
                 expectedoutput: Optional[str] = None, output_dir: Optional[str] = None):
        """Constractor of PilelineRegression.
        
        Args:
            recipe: recipe XML file name
            input_dir: path to directory contains input files
            visname: name of MeadurementSet
            expectedoutput: path to a file that defines expected output of a test
            output_dir: path to directory to output. If None, it sets visname
        """
        self.recipe = recipe
        self.input_dir = input_dir
        self.visname = visname
        self.expectedoutput = expectedoutput
        self.testinput = f'{input_dir}/{visname}'
        self.current_path = os.getcwd()
        self.output_dir = output_dir if output_dir else visname
        self.__initialize_working_folder()

    def __initialize_working_folder(self):
        """Initialize a root folder for task execution."""
        if os.path.isdir(self.output_dir):
            shutil.rmtree(self.output_dir)
        os.mkdir(self.output_dir)

    def __sanitize_regression_string(self, instring: str) -> Tuple:
        """Sanitize to get numeric values, remove newline chars and change to float.

        Args:
            instring: input string
        Returns:
            tuple(key, value, optional tolerance)
        """
        keyval = instring.split(':::')[0]

        keystring = keyval.split('=')[0]
        value = float(keyval.split('=')[-1])
        try:
            tolerance = float(instring.split(':::')[-1].replace('\n', ''))
        except ValueError:
            tolerance = None

        return keystring, value, tolerance

    def run(self, ppr: Optional[str] = None, telescope: str = 'alma',
            default_relative_tolerance: float = 1e-7, omp_num_threads: Optional[int] = None):
        """
        Run test with PPR if supplied or recipereducer if no PPR and compared to expected results.

        The inputs and expectd output are usually found in the pipeline data repository.

        Args:
            ppr: PPR file name
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
        input_vis = casa_tools.utils.resolve(self.testinput)

        # optionally set OpenMP nthreads to a specified value.
        if omp_num_threads is not None:
            # casa_tools.casalog.ompGetNumThreads() and get_casa_session_details()['omp_num_threads'] are equivalent.
            default_nthreads = get_casa_session_details()['omp_num_threads']
            casa_tools.casalog.ompSetNumThreads(omp_num_threads)

        try:
            # run the pipeline for new results

            # switch from the pytest-call working directory to the root folder for this test.
            os.chdir(self.output_dir)

            # create the sub-directory structure for this test and switch to "working/"
            dd_list = ['products', 'working', 'rawdata'] if ppr else ['products', 'working']
            for dd in dd_list:
                try:
                    os.mkdir(dd)
                except FileExistsError:
                    LOG.warning(f"Directory \'{dd} exists.  Continuing")
            os.chdir('working')

            # PIPE-1301: shut down the existing plotms process to avoid side-effects from changing CWD.
            # This is implemented as a workaround for CAS-13626
            shutdown_plotms()
            
            # PIPE-1432: reset casatasks/tec_maps.workDir as it's unaware of a CWD change.
            if hasattr(tec_maps, 'workDir'):
                tec_maps.workDir = os.getcwd()+'/'            

            # switch to per-test casa/PL logfile paths and backup the default(initial) casa logfile name
            _, _, last_casa_logfile = self.__reset_logfiles(prepend=True)

            if ppr:
                self.__run_ppr(input_vis, ppr, telescope)
            else:
                self.__run_reducer(input_vis)

            # Get new results
            new_results = self.__get_results_of_from_current_context()

            # new results file path
            new_file = f'{self.visname}.NEW.results.txt'

            # Store new results in a file
            self.__save_new_results_to(new_file, new_results)

            # Compare new results with expected results
            self.__compare_results(new_file, default_relative_tolerance)

            # restore the default logfile state
            self.__reset_logfiles(casa_logfile=last_casa_logfile)

        finally:
            os.chdir(self.current_path)

        # restore the OpenMP nthreads to the value saved before the Pipeline ppr/reducer call.
        if omp_num_threads is not None:
            casa_tools.casalog.ompSetNumThreads(default_nthreads)

    def __compare_results(self, new_file: str, relative_tolerance: float):
        """
        Compare results between new one loaded from file and old one.

        Args:
            new_file : file path of new results
            relative_tolerance : relative tolerance of output value
        """
        expected = casa_tools.utils.resolve(self.expectedoutput)
        with open(expected) as expected_fd, open(new_file) as new_fd:
            expected_results = expected_fd.readlines()
            new_results = new_fd.readlines()
            errors = []
            for old, new in zip(expected_results, new_results):
                oldkey, oldval, tol = self.__sanitize_regression_string(old)
                newkey, newval, _ = self.__sanitize_regression_string(new)
                assert oldkey == newkey
                tolerance = tol if tol else relative_tolerance
                LOG.info(f'Comparing {oldval} to {newval} with a rel. tolerance of {tolerance}')
                if oldval != pytest.approx(newval, rel=tolerance):
                    errorstr = f"{oldkey}\n\tvalues differ by > a relative difference of {tolerance}\n\texpected: {oldval}\n\tnew:      {newval}"
                    errors.append(errorstr)
            [LOG.warning(x) for x in errors]
            n_errors = len(errors)
            if n_errors > 0:
                pytest.fail("Failed to match {0} result value{1} within tolerance{1} :\n{2}".format(
                    n_errors, '' if n_errors == 1 else 's', '\n'.join(errors)), pytrace=True)

    def __save_new_results_to(self, new_file: str, new_results: List[str]):
        """
        Compare results between new one and old one, both results are loaded from specified files.

        Args:
            new_file : file path of new results to save
            new_results : List[str] of new results
        """
        with open(new_file, 'w') as fd:
            fd.writelines([str(x) + '\n' for x in new_results])

    def __get_results_of_from_current_context(self) -> List[str]:
        """
        Get results of current execution from context.

        Returns: List[str] of new results
        """
        context = pipeline.Pipeline(context='last').context
        new_results = sorted(regression.extract_regression_results(context))
        return new_results

    def __run_ppr(self, input_vis: str, ppr: str, telescope: str):
        """
        Execute the recipe defined by PPR.

        Args:
            input_vis : MS name
            ppr : PPR file name
            telescope : string 'alma' or 'vla'
        
        note: this private method is expected be called under "working/"
        """

        # executeppr expects the rawdata in ../rawdata
        os.symlink(input_vis, f'../rawdata/{os.path.basename(input_vis)}')

        # save a copy of PPR in the directory one level above "working/".
        ppr_path = casa_tools.utils.resolve(ppr)
        ppr_local = f'../{os.path.basename(ppr_path)}'
        shutil.copyfile(ppr_path, ppr_local)

        # executeppr expects this environment avariable pointing to "working/".
        os.environ['SCIPIPE_ROOTDIR'] = os.getcwd()

        if telescope is 'alma':
            almappr.executeppr(ppr_local, importonly=False)
        elif telescope is 'vla':
            vlappr.executeppr(ppr_local, importonly=False)
        else:
            LOG.error("Telescope is not 'alma' or 'vla'.  Can't run executeppr.")

    def __run_reducer(self, input_vis: str):
        """
        Execute the recipe by recipereducer.

        Args:
            input_vis : MS name

        note: this private method is expected be called under "working/"
        """
        LOG.warning("Running without Pipeline Processing Request (PPR).  Using recipereducer instead.")
        
        pipeline.recipereducer.reduce(vis=[input_vis], procedure=self.recipe)

    def __reset_logfiles(self, casacalls_logfile=None, casa_logfile=None, prepend=False):
        """Put CASA/Pipeline logfiles into the test working directory."""

        # reset casacalls-*.txt
        if casacalls_logfile is None:
            casacalls_logfile = 'casacalls-{!s}.txt'.format(platform.node().split('.')[0])
        else:
            casacalls_logfile = casacalls_logfile
        _ = logging.get_logger('CASACALLS', stream=None, format='%(message)s', addToCasaLog=False,
                               filename=casacalls_logfile)
        # reset casa-*.log
        if casa_logfile is None:
            now_str = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            casa_logfile = os.path.abspath(f'casa-{now_str}.log')
        else:
            casa_logfile = os.path.abspath(casa_logfile)
        last_casa_logfile = casa_tools.casalog.logfile()
        casa_tools.casalog.setlogfile(casa_logfile)

        # prepend the content of the last CASA logfile in the new logfile.
        if prepend and os.path.exists(last_casa_logfile):
            with open(last_casa_logfile, 'r') as infile:
                with open(casa_logfile, 'a') as outfile:
                    outfile.write(infile.read())

        return casacalls_logfile, casa_logfile, last_casa_logfile


# The methods below are test methods called from pytest.

def test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small__procedure_hifa_calimage__regression():
    """Run ALMA cal+image regression on a small test dataset.

    Recipe name:                procedure_hifa_calimage
    Dataset:                    uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms
    Expected results version:   casa-6.1.1-15-pipeline-2020.1.0.40
    """
    pr = PipelineRegression(recipe='procedure_hifa_calimage.xml',
                            input_dir='pl-unittest',
                            visname='uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms',
                            expectedoutput=('pl-regressiontest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small/' +
                                            'uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.casa-6.1.1-15-pipeline-2020.1.0.40.results.txt'))

    pr.run(ppr='pl-regressiontest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small/PPR.xml')


def test_uid___A002_X85c183_X36f__procedure_hsd_calimage__regression():
    """Run ALMA single-dish cal+image regression on the obseration data of M100.

    Recipe name:                procedure_hsd_calimage
    Dataset:                    uid___A002_X85c183_X36f
    Expected results version:   casa-6.2.0-119-pipeline-2020.2.0.23
    """
    pr = PipelineRegression(recipe='procedure_hsd_calimage.xml',
                            input_dir='pl-regressiontest/uid___A002_X85c183_X36f',
                            visname='uid___A002_X85c183_X36f',
                            expectedoutput=('pl-regressiontest/uid___A002_X85c183_X36f/' +
                                            'uid___A002_X85c183_X36f.casa-6.2.1-2-pipeline-2021.2.0.94-PIPE-1235.results.txt'))

    pr.run()


def test_uid___A002_X85c183_X36f_SPW15_23__PPR__regression():
    """Run ALMA single-dish restoredata regression on the observation data of M100.

    Dataset:                    uid___A002_X85c183_X36f_SPW15_23
    Expected results version:   casa-6.2.0-119-pipeline-2020.2.0.23
    """
    input_dir = 'pl-regressiontest/uid___A002_X85c183_X36f_SPW15_23'
    pr = PipelineRegression(input_dir=input_dir,
                            visname='uid___A002_X85c183_X36f_SPW15_23.ms',
                            expectedoutput=('pl-regressiontest/uid___A002_X85c183_X36f_SPW15_23/' +
                                            'uid___A002_X85c183_X36f_SPW15_23.casa-6.2.1-2-pipeline-2021.2.0.94-PIPE-1235.results.txt'))

    # copy files use restore task into products folder
    input_products = casa_tools.utils.resolve(f'{input_dir}/products')
    shutil.copytree(input_products, 'uid___A002_X85c183_X36f_SPW15_23.ms/products')

    pr.run(ppr='pl-regressiontest/uid___A002_X85c183_X36f_SPW15_23/PPR.xml')


def test_uid___mg2_20170525142607_180419__procedure_hsdn_calimage__regression():
    """Run ALMA single-dish cal+image regression for standard nobeyama recipe.

    Recipe name:                procedure_hsdn_calimage
    Dataset:                    mg2-20170525142607-180419
    Expected results version:   casa-6.2.0-119-pipeline-2020.2.0.23
    """
    pr = PipelineRegression(recipe='procedure_hsdn_calimage.xml',
                            input_dir='pl-regressiontest/mg2-20170525142607-180419',
                            visname='mg2-20170525142607-180419.ms',
                            expectedoutput=('pl-regressiontest/mg2-20170525142607-180419/' +
                                            'mg2-20170525142607-180419.casa-6.2.0-119-pipeline-2021.2.0.23.results.txt'))
    pr.run()


def test_uid___mg2_20170525142607_180419__PPR__regression():
    """Run ALMA single-dish cal+image regression for restore nobeyama recipe.

    Dataset:                    mg2-20170525142607-180419
    Expected results version:   casa-6.2.0-119-pipeline-2020.2.0.23
    """

    input_dir = 'pl-regressiontest/mg2-20170525142607-180419'

    pr = PipelineRegression(input_dir=input_dir,
                            visname='mg2-20170525142607-180419.ms',
                            expectedoutput=(f'{input_dir}/' +
                                            'mg2-20170525142607-180419_PPR.casa-6.2.0-119-pipeline-2021.2.0.23.results.txt'),
                            output_dir='mg2-20170525142607-180419_PPR')

    # copy files use restore task into products folder
    input_products = casa_tools.utils.resolve(f'{input_dir}/products')
    shutil.copytree(input_products, 'mg2-20170525142607-180419_PPR/products')

    pr.run(ppr=f'{input_dir}/PPR.xml')


def test_uid___A002_Xee1eb6_Xc58d_pipeline__procedure_hifa_calsurvey__regression():
    """Run ALMA cal+survey regression on a calibration survey test dataset
 
    Recipe name:                procedure_hifa_calsurvey
    Dataset:                    uid___A002_Xee1eb6_Xc58d_original.ms
    Expected results version:   casa-6.3.0-48-pipeline-2021.3.0.5
    """
    input_directory = 'pl-regressiontest/uid___A002_Xee1eb6_Xc58d_calsurvey/'
    pr = PipelineRegression(recipe='procedure_hifa_calsurvey.xml',
                            input_dir = input_directory,
                            visname='uid___A002_Xee1eb6_Xc58d_original.ms',
                            expectedoutput=(input_directory +
                                           'uid___A002_Xee1eb6_Xc58d.casa-6.3.0-482-pipeline-2021.3.0.5.results.txt'),
                            output_dir='uid___A002_Xee1eb6_Xc58d_calsurvey_output')
 
    pr.run()


def test_13A_537__procedure_hifv__regression():
    """Run VLA calibration regression for standard procedure_hifv.xml recipe.

    Recipe name:                procedure_hifv
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    Expected results version:   casa-6.2.1.7-pipeline-2021.2.0.128
    """

    input_dir = 'pl-regressiontest/13A-537'

    pr = PipelineRegression(recipe='procedure_hifv.xml',
                            input_dir=input_dir,
                            visname='13A-537.sb24066356.eb24324502.56514.05971091435',
                            expectedoutput=(f'{input_dir}/' +
                                            '13A-537.casa-6.2.1.7-pipeline-2021.2.0.128.results.txt'),
                            output_dir='13A_537__procedure_hifv__regression')

    pr.run(telescope='vla', omp_num_threads=1)


def test_13A_537__calibration__PPR__regression():
    """Run VLA calibration regression with a PPR file.

    PPR name:                   PPR_13A-537.xml
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    Expected results version:   casa-6.2.1.7-pipeline-2021.2.0.128
    """

    input_dir = 'pl-regressiontest/13A-537'

    pr = PipelineRegression(input_dir=input_dir,
                            visname='13A-537.sb24066356.eb24324502.56514.05971091435',
                            expectedoutput=(f'{input_dir}/' +
                                            '13A-537.casa-6.2.1.7-pipeline-2021.2.0.128.results.txt'),
                            output_dir='13A_537__calibration__PPR__regression')

    pr.run(ppr=f'{input_dir}/PPR_13A-537.xml', telescope='vla', omp_num_threads=1)


def test_13A_537__restore__PPR__regression():
    """Run VLA calibration restoredata regression with a PPR file

    PPR name:                   PPR_13A-537_restore.xml
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    Expected results version:   casa-6.2.1.7-pipeline-2021.2.0.128
    """
    input_dir = 'pl-regressiontest/13A-537'
    pr = PipelineRegression(input_dir=input_dir,
                            visname='13A-537.sb24066356.eb24324502.56514.05971091435',
                            expectedoutput=(f'{input_dir}/' +
                                            '13A-537.casa-6.2.1.7-pipeline-2021.2.0.128.restore.results.txt'),
                            output_dir='13A_537__restore__PPR__regression')

    # copy files use restore task into products folder
    input_products = casa_tools.utils.resolve(f'{input_dir}/products')
    shutil.copytree(input_products, '13A_537__restore__PPR__regression/products')

    pr.run(ppr=f'{input_dir}/PPR_13A-537_restore.xml', telescope='vla')

