import shutil
from pathlib import Path

import pytest
from pipeline.infrastructure.utils import pclean
from pipeline.infrastructure import casa_tools


# Module-level constant for the test dataset
MS_NAME = casa_tools.utils.resolve(
    'pl-unittest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small_target.ms'
)


@pytest.fixture
def valid_ms():
    """Fixture that provides a valid MeasurementSet path or skips the test."""
    if not Path(MS_NAME).exists():
        pytest.skip(f'Test data not found: {MS_NAME}')
    return MS_NAME


@pytest.fixture
def image_output(tmp_path):
    """Fixture that provides a unique output path and handles cleanup."""
    imagename = tmp_path / 'test_output'
    yield str(imagename)
    # Cleanup: Remove all files/dirs matching the pattern
    for p in tmp_path.glob('test_output*'):
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()


class TestFindExecutable:
    """Tests for the find_executable function."""

    def test_finds_mpirun_in_parent_directory(self, tmp_path):
        """Test finding mpirun in a parent directory's bin folder."""
        # Setup: Create tmp_path/bin/mpirun
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()

        mpirun_path = bin_dir / 'mpirun'
        mpirun_path.touch(mode=0o755)

        # Setup: Create a subdirectory to start searching from
        start_dir = tmp_path / 'subdir'
        start_dir.mkdir()

        # Execute
        exe_dict = pclean.find_executable(start_dir=str(start_dir))

        # Verify
        assert exe_dict['mpirun'] == str(mpirun_path.resolve())
        assert exe_dict['mpicasa'] is None

    def test_returns_none_when_not_found(self, tmp_path):
        """Test that None is returned when no executables are found."""
        exe_dict = pclean.find_executable(start_dir=str(tmp_path))

        assert exe_dict['mpirun'] is None
        assert exe_dict['mpicasa'] is None
        assert exe_dict['casa'] is None


class TestPcleanWithInvalidInput:
    """Tests for pclean error handling with invalid inputs."""

    def test_serial_execution_with_missing_ms(self):
        """Test that serial execution fails gracefully with missing MS."""
        with pytest.raises(Exception) as excinfo:
            pclean.pclean('non_existent.ms', imagename='test_serial', parallel=False)

        # Verify the error is from CASA, not pclean internals
        assert 'pclean' not in str(excinfo.type)

    def test_parallel_execution_with_missing_ms(self):
        """Test that parallel execution propagates errors from subprocess."""
        with pytest.raises(RuntimeError) as excinfo:
            pclean.pclean('non_existent.ms', imagename='test_parallel', parallel=True)

        error_msg = str(excinfo.value)

        # Either subprocess failed to run or error was propagated back
        assert ('tclean subprocess execution failed' in error_msg or ': ' in error_msg)

    def test_parallel_with_nproc_dict(self):
        """Test that parallel execution accepts nproc configuration."""
        with pytest.raises(RuntimeError):
            pclean.pclean('non_existent.ms', imagename='test_dict', parallel={'nproc': 2})


class TestPcleanWithValidDataset:
    """Integration tests using a real MeasurementSet.
    
    Note that the current tests focus on verifying that pclean runs.
    The mpi-cluster setup (<=4 cores/proc) is restricted to stay within the current 
    GitHub Runner limit:
        https://docs.github.com/en/actions/reference/runners/github-hosted-runners
    """

    def test_serial_dirty_image(self, valid_ms, image_output):
        """Test serial tclean execution produces expected output."""
        pclean.pclean(vis=[valid_ms],
                      field='helms30', spw=['0'], antenna=['0,1,2,3,4,5,6,7,8,9,10&'],
                      scan=['10'], intent='OBSERVE_TARGET#ON_SOURCE', datacolumn='data',
                      imagename=image_output,
                      imsize=[90, 90], cell=['0.91arcsec'], phasecenter='ICRS 01:03:01.3200 -000.32.59.640',
                      stokes='I', specmode='cube', nchan=117,
                      start='214.4501854310GHz', width='15.6245970MHz', outframe='LSRK',
                      perchanweightdensity=True, gridder='standard', mosweight=False,
                      usepointing=False, pblimit=0.2, deconvolver='hogbom', restoration=True,
                      restoringbeam='common', pbcor=True, weighting='briggsbwtaper',
                      robust=0.5, npixels=0, niter=0, threshold='0.0mJy', nsigma=0.0,
                      interactive=False, fullsummary=False, usemask='auto-multithresh',
                      sidelobethreshold=1.25, noisethreshold=5.0, lownoisethreshold=2.0,
                      negativethreshold=0.0, minbeamfrac=0.1, growiterations=75,
                      dogrowprune=True, minpercentchange=1.0, fastnoise=False,
                      savemodel='none', parallel=False)

        # Verify output was created
        assert self._image_exists(image_output), 'Output image was not created'

    def test_parallel_dirty_image(self, valid_ms, image_output):
        """Test parallel tclean execution produces expected output."""
        pclean.pclean(vis=[valid_ms],
                      field='helms30', spw=['0'], antenna=['0,1,2,3,4,5,6,7,8,9,10&'],
                      scan=['10'], intent='OBSERVE_TARGET#ON_SOURCE', datacolumn='data',
                      imagename=image_output,
                      imsize=[90, 90], cell=['0.91arcsec'], phasecenter='ICRS 01:03:01.3200 -000.32.59.640',
                      stokes='I', specmode='cube', nchan=117,
                      start='214.4501854310GHz', width='15.6245970MHz', outframe='LSRK',
                      perchanweightdensity=True, gridder='standard', mosweight=False,
                      usepointing=False, pblimit=0.2, deconvolver='hogbom', restoration=True,
                      restoringbeam='common', pbcor=True, weighting='briggsbwtaper',
                      robust=0.5, npixels=0, niter=0, threshold='0.0mJy', nsigma=0.0,
                      interactive=False, fullsummary=False, usemask='auto-multithresh',
                      sidelobethreshold=1.25, noisethreshold=5.0, lownoisethreshold=2.0,
                      negativethreshold=0.0, minbeamfrac=0.1, growiterations=75,
                      dogrowprune=True, minpercentchange=1.0, fastnoise=False,
                      savemodel='none', parallel=True)

        # Verify output was created
        assert self._image_exists(image_output), 'Output image was not created'

    def test_parallel_with_custom_nproc(self, valid_ms, image_output):
        """Test parallel execution with custom number of processes."""
        pclean.pclean(vis=[valid_ms],
                      field='helms30', spw=['0'], antenna=['0,1,2,3,4,5,6,7,8,9,10&'],
                      scan=['10'], intent='OBSERVE_TARGET#ON_SOURCE', datacolumn='data',
                      imagename=image_output,
                      imsize=[90, 90], cell=['0.91arcsec'], phasecenter='ICRS 01:03:01.3200 -000.32.59.640',
                      stokes='I', specmode='cube', nchan=117,
                      start='214.4501854310GHz', width='15.6245970MHz', outframe='LSRK',
                      perchanweightdensity=True, gridder='standard', mosweight=False,
                      usepointing=False, pblimit=0.2, deconvolver='hogbom', restoration=True,
                      restoringbeam='common', pbcor=True, weighting='briggsbwtaper',
                      robust=0.5, npixels=0, niter=0, threshold='0.0mJy', nsigma=0.0,
                      interactive=False, fullsummary=False, usemask='auto-multithresh',
                      sidelobethreshold=1.25, noisethreshold=5.0, lownoisethreshold=2.0,
                      negativethreshold=0.0, minbeamfrac=0.1, growiterations=75,
                      dogrowprune=True, minpercentchange=1.0, fastnoise=False,
                      savemodel='none', parallel={'nproc': 3})

        # Verify output was created
        assert self._image_exists(image_output), 'Output image was not created'

    def test_serial_with_cleaning(self, valid_ms, image_output):
        """Test serial tclean with actual deconvolution iterations."""
        pclean.pclean(vis=[valid_ms],
                      field='helms30', spw=['0'], antenna=['0,1,2,3,4,5,6,7,8,9,10&'],
                      scan=['10'], intent='OBSERVE_TARGET#ON_SOURCE', datacolumn='data',
                      imagename=image_output,
                      imsize=[90, 90], cell=['0.91arcsec'], phasecenter='ICRS 01:03:01.3200 -000.32.59.640',
                      stokes='I', specmode='cube', nchan=117,
                      start='214.4501854310GHz', width='15.6245970MHz', outframe='LSRK',
                      perchanweightdensity=True, gridder='standard', mosweight=False,
                      usepointing=False, pblimit=0.2, deconvolver='hogbom', restoration=True,
                      restoringbeam='common', pbcor=True, weighting='briggsbwtaper',
                      robust=0.5, npixels=0, niter=10, threshold='0.0mJy', nsigma=0.0,
                      interactive=False, fullsummary=False, usemask='auto-multithresh',
                      sidelobethreshold=1.25, noisethreshold=5.0, lownoisethreshold=2.0,
                      negativethreshold=0.0, minbeamfrac=0.1, growiterations=75,
                      dogrowprune=True, minpercentchange=1.0, fastnoise=False,
                      savemodel='none', parallel=False)

        # Verify output and residual images exist
        assert self._image_exists(image_output), 'Output image was not created'
        assert self._residual_exists(image_output), 'Residual image was not created'

    def test_parallel_with_cleaning(self, valid_ms, image_output):
        """Test parallel tclean with actual deconvolution iterations."""
        pclean.pclean(vis=[valid_ms],
                      field='helms30', spw=['0'], antenna=['0,1,2,3,4,5,6,7,8,9,10&'],
                      scan=['10'], intent='OBSERVE_TARGET#ON_SOURCE', datacolumn='data',
                      imagename=image_output,
                      imsize=[90, 90], cell=['0.91arcsec'], phasecenter='ICRS 01:03:01.3200 -000.32.59.640',
                      stokes='I', specmode='cube', nchan=117,
                      start='214.4501854310GHz', width='15.6245970MHz', outframe='LSRK',
                      perchanweightdensity=True, gridder='standard', mosweight=False,
                      usepointing=False, pblimit=0.2, deconvolver='hogbom', restoration=True,
                      restoringbeam='common', pbcor=True, weighting='briggsbwtaper',
                      robust=0.5, npixels=0, niter=10, threshold='0.0mJy', nsigma=0.0,
                      interactive=False, fullsummary=False, usemask='auto-multithresh',
                      sidelobethreshold=1.25, noisethreshold=5.0, lownoisethreshold=2.0,
                      negativethreshold=0.0, minbeamfrac=0.1, growiterations=75,
                      dogrowprune=True, minpercentchange=1.0, fastnoise=False,
                      savemodel='none', parallel=True)

        # Verify output and residual images exist
        assert self._image_exists(image_output), 'Output image was not created'
        assert self._residual_exists(image_output), 'Residual image was not created'

    @staticmethod
    def _image_exists(imagename: str) -> bool:
        """Check if tclean produced an image (handles .image or .image.tt0)."""
        return Path(f'{imagename}.image').exists() or Path(f'{imagename}.image.tt0').exists()

    @staticmethod
    def _residual_exists(imagename: str) -> bool:
        """Check if tclean produced a residual (handles .residual or .residual.tt0)."""
        return (
            Path(f'{imagename}.residual').exists() or Path(f'{imagename}.residual.tt0').exists()
        )