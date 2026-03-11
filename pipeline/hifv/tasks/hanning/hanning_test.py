# Do not evaluate type annotations at definition time.
from __future__ import annotations

from unittest.mock import MagicMock, patch

from .hanning import Hanning, HanningInputs, HanningResults


class TestHanningInputs:
    """Unit tests for HanningInputs class.

    Note: Direct instantiation tests are skipped due to context validation.
    Context must be a launcher.Context instance, tested indirectly through
    integration tests.
    """

    def test_inputs_placeholder(self) -> None:
        """Placeholder for HanningInputs integration testing."""
        pass


class TestHanningResults:
    """Unit tests for HanningResults class."""

    def test_init_with_defaults(self) -> None:
        """Test HanningResults initialization with default values."""
        results = HanningResults(task_successful=True, qa_message='Success')

        assert results.task_successful is True
        assert results.qa_message == 'Success'
        assert results.final == []
        assert results.pool == []
        assert results.preceding == []
        assert results.smoothed_spws == {}
        assert results.error == set()

    def test_init_with_values(self) -> None:
        """Test HanningResults initialization with explicit values."""
        smoothed_spws = {0: (True, 'continuum'), 1: (False, 'spectral line')}
        results = HanningResults(
            task_successful=True,
            qa_message='Success',
            final=['file1.ms'],
            pool=['file2.ms'],
            preceding=['file3.ms'],
            smoothed_spws=smoothed_spws,
        )

        assert results.task_successful is True
        assert results.qa_message == 'Success'
        assert results.final == ['file1.ms']
        assert results.pool == ['file2.ms']
        assert results.preceding == ['file3.ms']
        assert results.smoothed_spws == smoothed_spws

    def test_results_lists_copied(self) -> None:
        """Test that input lists are copied, not referenced."""
        final_list = ['file1.ms']
        results = HanningResults(task_successful=True, qa_message='Success', final=final_list)

        final_list.append('file2.ms')
        assert results.final == ['file1.ms']

    def test_merge_with_context(self) -> None:
        """Test merge_with_context method."""
        context = MagicMock()
        context.observing_run.measurement_sets = [MagicMock()]
        results = HanningResults(task_successful=True, qa_message='Success')

        # Should not raise an error
        results.merge_with_context(context)


class TestHanningPrepare:
    """Unit tests for Hanning.prepare() method."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.context = MagicMock()
        self.inputs = MagicMock(spec=HanningInputs)
        self.inputs.context = self.context
        self.inputs.vis = 'test.ms'
        self.inputs.spws_to_smooth = None
        self.inputs.maser_detection = True

    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.TableReader')
    def test_already_smoothed_ms(self, mock_table_reader: MagicMock) -> None:
        """Test that already smoothed MS is skipped."""
        mock_table = MagicMock()
        mock_table.colnames.return_value = ['OFFLINE_HANNING_SMOOTH']
        mock_table_reader.return_value.__enter__.return_value = mock_table

        hanning_task = Hanning(inputs=self.inputs)
        results = hanning_task.prepare()

        assert results.task_successful is True
        assert 'already had offline hanning smoothing applied' in results.qa_message

    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.TableReader')
    def test_no_spws_to_smooth(self, mock_table_reader: MagicMock) -> None:
        """Test early return when no SPWs need smoothing."""
        mock_table = MagicMock()
        mock_table.colnames.return_value = []
        mock_table_reader.return_value.__enter__.return_value = mock_table

        # Setup MS and spectral windows - spectral line without maser
        ms = MagicMock()
        spw = MagicMock()
        spw.id = 0
        spw.sdm_num_bin = 0
        spw.specline_window = True  # This is a spectral line
        ms.get_spectral_windows.return_value = [spw]
        self.context.observing_run.get_ms.return_value = ms

        hanning_task = Hanning(inputs=self.inputs)
        hanning_task._executor = MagicMock()

        # Mock maser detection to return False
        with patch.object(hanning_task, '_checkmaserline', return_value=False):
            with patch.object(hanning_task, '_track_hsmooth'):
                results = hanning_task.prepare()

        assert results.task_successful is True
        assert 'None of the science spectral windows were selected' in results.qa_message

    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.TableReader')
    def test_online_smoothing_prevents_offline_smoothing(
        self,
        mock_table_reader: MagicMock,
    ) -> None:
        """Test that online smoothing (sdm_num_bin > 1) prevents offline smoothing."""
        mock_table = MagicMock()
        mock_table.colnames.return_value = []
        mock_table_reader.return_value.__enter__.return_value = mock_table

        ms = MagicMock()
        spw = MagicMock()
        spw.id = 0
        spw.sdm_num_bin = 2  # Online smoothing applied
        spw.specline_window = False
        ms.get_spectral_windows.return_value = [spw]
        self.context.observing_run.get_ms.return_value = ms

        hanning_task = Hanning(inputs=self.inputs)
        hanning_task._executor = MagicMock()

        with patch.object(hanning_task, '_track_hsmooth'):
            results = hanning_task.prepare()

        assert results.task_successful is True
        assert 'None of the science spectral windows were selected' in results.qa_message

    @patch('pipeline.hifv.tasks.hanning.hanning.shutil.rmtree')
    @patch('pipeline.hifv.tasks.hanning.hanning.os.path.exists')
    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.TableReader')
    def test_temp_ms_not_created_error(
        self,
        mock_table_reader: MagicMock,
        mock_exists: MagicMock,
        mock_rmtree: MagicMock,
    ) -> None:
        """Test error handling when temp MS is not created."""
        mock_table = MagicMock()
        mock_table.colnames.return_value = []
        mock_table_reader.return_value.__enter__.return_value = mock_table

        ms = MagicMock()
        spw = MagicMock()
        spw.id = 0
        spw.sdm_num_bin = 0
        spw.specline_window = False
        ms.get_spectral_windows.return_value = [spw]
        self.context.observing_run.get_ms.return_value = ms

        hanning_task = Hanning(inputs=self.inputs)
        hanning_task._executor = MagicMock()

        # Temp MS doesn't exist after hanningsmooth (check for temphanning.ms fails)
        mock_exists.return_value = False

        with patch.object(hanning_task, '_do_hanningsmooth'):
            with patch.object(hanning_task, '_track_hsmooth'):
                results = hanning_task.prepare()

        assert results.task_successful is False
        assert 'Problem encountered' in results.qa_message

    @patch('pipeline.hifv.tasks.hanning.hanning.os.rename')
    @patch('pipeline.hifv.tasks.hanning.hanning.shutil.rmtree')
    @patch('pipeline.hifv.tasks.hanning.hanning.os.path.exists')
    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.TableReader')
    def test_file_operation_failure_cleanup(
        self,
        mock_table_reader: MagicMock,
        mock_exists: MagicMock,
        mock_rmtree: MagicMock,
        mock_rename: MagicMock,
    ) -> None:
        """Test cleanup logic when file operations fail."""
        mock_table = MagicMock()
        mock_table.colnames.return_value = []
        mock_table_reader.return_value.__enter__.return_value = mock_table

        ms = MagicMock()
        spw = MagicMock()
        spw.id = 0
        spw.sdm_num_bin = 0
        spw.specline_window = False
        ms.get_spectral_windows.return_value = [spw]
        self.context.observing_run.get_ms.return_value = ms

        # Simulate temp MS exists initially but removal fails
        mock_exists.side_effect = [True, False, True, False]  # temp exists, then doesn't
        mock_rmtree.side_effect = OSError('Permission denied')

        hanning_task = Hanning(inputs=self.inputs)

        with patch.object(hanning_task, '_do_hanningsmooth'):
            with patch.object(hanning_task, '_track_hsmooth'):
                results = hanning_task.prepare()

        assert results.task_successful is False

    @patch('pipeline.hifv.tasks.hanning.hanning.os.path.exists')
    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.TableReader')
    def test_recovery_when_original_ms_removed(
        self,
        mock_table_reader: MagicMock,
        mock_exists: MagicMock,
    ) -> None:
        """Test recovery attempt when original MS is removed but temp exists."""
        mock_table = MagicMock()
        mock_table.colnames.return_value = []
        mock_table_reader.return_value.__enter__.return_value = mock_table

        ms = MagicMock()
        spw = MagicMock()
        spw.id = 0
        spw.sdm_num_bin = 0
        spw.specline_window = False
        ms.get_spectral_windows.return_value = [spw]
        self.context.observing_run.get_ms.return_value = ms

        hanning_task = Hanning(inputs=self.inputs)

        with patch.object(hanning_task, '_do_hanningsmooth'):
            with patch.object(hanning_task, '_track_hsmooth'):
                with patch('pipeline.hifv.tasks.hanning.hanning.shutil.rmtree') as mock_rmtree:
                    with patch('pipeline.hifv.tasks.hanning.hanning.os.rename') as mock_rename:
                        # First check: temp exists, second check: original missing, third/fourth: recovery scenario
                        mock_exists.side_effect = [True, False, True, False]
                        mock_rmtree.side_effect = OSError('Removal failed')

                        results = hanning_task.prepare()

        assert results.task_successful is False

    @patch('pipeline.hifv.tasks.hanning.hanning.os.rename')
    @patch('pipeline.hifv.tasks.hanning.hanning.shutil.rmtree')
    @patch('pipeline.hifv.tasks.hanning.hanning.os.path.exists')
    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.TableReader')
    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tasks.hanningsmooth')
    def test_manual_spws_to_smooth_passed_to_casa_task(
        self,
        mock_hanningsmooth: MagicMock,
        mock_table_reader: MagicMock,
        mock_exists: MagicMock,
        mock_rmtree: MagicMock,
        mock_rename: MagicMock,
    ) -> None:
        """Test that manually set spws_to_smooth are passed to CASA task."""
        mock_table = MagicMock()
        mock_table.colnames.return_value = []
        mock_table_reader.return_value.__enter__.return_value = mock_table

        # Setup MS with multiple spectral windows
        ms = MagicMock()
        spw0 = MagicMock()
        spw0.id = 0
        spw0.sdm_num_bin = 0
        spw0.specline_window = False
        spw1 = MagicMock()
        spw1.id = 1
        spw1.sdm_num_bin = 0
        spw1.specline_window = False
        spw2 = MagicMock()
        spw2.id = 2
        spw2.sdm_num_bin = 0
        spw2.specline_window = False
        ms.get_spectral_windows.return_value = [spw0, spw1, spw2]
        self.context.observing_run.get_ms.return_value = ms

        # Manually set spws_to_smooth (user-provided)
        self.inputs.spws_to_smooth = [0, 2]

        # Mock file operations
        mock_exists.return_value = True
        mock_hanningsmooth.return_value = MagicMock()

        hanning_task = Hanning(inputs=self.inputs)
        hanning_task._executor = MagicMock()
        hanning_task._executor.execute.return_value = MagicMock()

        with patch.object(hanning_task, '_track_hsmooth'):
            results = hanning_task.prepare()

        # Verify hanningsmooth was called with manually set spws
        mock_hanningsmooth.assert_called_once()
        call_kwargs = mock_hanningsmooth.call_args[1]
        assert call_kwargs['smooth_spw'] == [0, 2]
        assert results.task_successful is True

    @patch('pipeline.hifv.tasks.hanning.hanning.os.rename')
    @patch('pipeline.hifv.tasks.hanning.hanning.shutil.rmtree')
    @patch('pipeline.hifv.tasks.hanning.hanning.os.path.exists')
    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.TableReader')
    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tasks.hanningsmooth')
    def test_automatic_spws_to_smooth_passed_to_casa_task(
        self,
        mock_hanningsmooth: MagicMock,
        mock_table_reader: MagicMock,
        mock_exists: MagicMock,
        mock_rmtree: MagicMock,
        mock_rename: MagicMock,
    ) -> None:
        """Test that automatically calculated spws_to_smooth are passed to CASA task."""
        mock_table = MagicMock()
        mock_table.colnames.return_value = []
        mock_table_reader.return_value.__enter__.return_value = mock_table

        # Setup MS with mixed spectral windows
        ms = MagicMock()
        spw0 = MagicMock()
        spw0.id = 0
        spw0.sdm_num_bin = 0
        spw0.specline_window = False  # continuum -> should smooth
        spw1 = MagicMock()
        spw1.id = 1
        spw1.sdm_num_bin = 0
        spw1.specline_window = True  # spectral line, no maser -> should not smooth
        spw2 = MagicMock()
        spw2.id = 2
        spw2.sdm_num_bin = 0
        spw2.specline_window = False  # continuum -> should smooth
        ms.get_spectral_windows.return_value = [spw0, spw1, spw2]
        self.context.observing_run.get_ms.return_value = ms

        # spws_to_smooth is None (automatic detection)
        self.inputs.spws_to_smooth = None

        # Mock file operations
        mock_exists.return_value = True
        mock_hanningsmooth.return_value = MagicMock()

        hanning_task = Hanning(inputs=self.inputs)
        hanning_task._executor = MagicMock()
        hanning_task._executor.execute.return_value = MagicMock()

        # Mock maser detection to return False for spw 1
        with patch.object(hanning_task, '_checkmaserline', return_value=False):
            with patch.object(hanning_task, '_track_hsmooth'):
                results = hanning_task.prepare()

        # Verify hanningsmooth was called with automatically calculated spws (0 and 2, not 1)
        mock_hanningsmooth.assert_called_once()
        call_kwargs = mock_hanningsmooth.call_args[1]
        assert call_kwargs['smooth_spw'] == [0, 2]
        assert results.task_successful is True


class TestHanningAnalyse:
    """Unit tests for Hanning.analyse() method."""

    def test_analyse_returns_results(self) -> None:
        """Test that analyse method returns results unchanged."""
        inputs = MagicMock(spec=HanningInputs)
        hanning_task = Hanning(inputs=inputs)

        results = HanningResults(task_successful=True, qa_message='Test')
        returned = hanning_task.analyse(results)

        assert returned is results


class TestHanningCheckmaserline:
    """Unit tests for Hanning._checkmaserline() method."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.context = MagicMock()
        self.inputs = MagicMock(spec=HanningInputs)
        self.inputs.context = self.context
        self.inputs.vis = 'test.ms'

    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.synthesisutils')
    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.quanta')
    def test_non_topo_frame_skips_detection(
        self,
        mock_quanta: MagicMock,
        mock_sutools: MagicMock,
    ) -> None:
        """Test that non-TOPO reference frame skips maser detection."""
        ms = MagicMock()
        spw = MagicMock()
        spw._ref_frequency_frame = 'LSRK'
        spw._min_frequency.convert_to.return_value.value = 1e9
        spw._max_frequency.convert_to.return_value.value = 2e9
        ms.get_spectral_window.return_value = spw
        self.context.observing_run.measurement_sets = [ms]
        self.context.observing_run.get_ms.return_value = ms

        hanning_task = Hanning(inputs=self.inputs)
        result = hanning_task._checkmaserline('0')

        assert result is False

    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.synthesisutils')
    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.quanta')
    def test_maser_line_detection(
        self,
        mock_quanta: MagicMock,
        mock_sutools: MagicMock,
    ) -> None:
        """Test detection of maser line within frequency range."""
        ms = MagicMock()
        ms.name = 'test.ms'
        spw = MagicMock()
        spw._ref_frequency_frame = 'TOPO'
        spw._min_frequency.convert_to.return_value.value = 1.6e9
        spw._max_frequency.convert_to.return_value.value = 1.7e9
        ms.get_spectral_window.return_value = spw

        self.context.observing_run.measurement_sets = [ms]
        self.context.observing_run.get_ms.return_value = ms

        # Mock casa tools with OH (1) maser line frequency (1612231000 Hz)
        mock_quanta.getvalue.side_effect = [[1.612231e9], [1.612231e9]]
        mock_sutools.advisechansel.return_value = {
            'freqstart': '1.6GHz',
            'freqend': '1.7GHz',
        }

        hanning_task = Hanning(inputs=self.inputs)
        result = hanning_task._checkmaserline('0')

        assert result is True

    def test_checkmaserline_no_maser_line(self) -> None:
        """Test that frequencies outside maser range return False."""
        ms = MagicMock()
        ms.name = 'test.ms'
        spw = MagicMock()
        spw._ref_frequency_frame = 'TOPO'
        spw._min_frequency.convert_to.return_value.value = 10e9
        spw._max_frequency.convert_to.return_value.value = 11e9
        ms.get_spectral_window.return_value = spw

        self.context.observing_run.measurement_sets = [ms]

        with patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.synthesisutils'):
            with patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.quanta') as mock_quanta:
                mock_quanta.getvalue.return_value = [10e9]

                hanning_task = Hanning(inputs=self.inputs)
                result = hanning_task._checkmaserline('0')

        assert result is False


class TestHanningTrackhsmooth:
    """Unit tests for Hanning._track_hsmooth() method."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.inputs = MagicMock(spec=HanningInputs)
        self.inputs.vis = 'test.ms'

    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.TableReader')
    def test_track_hsmooth_creates_column(self, mock_table_reader: MagicMock) -> None:
        """Test that _track_hsmooth creates OFFLINE_HANNING_SMOOTH column."""
        mock_table = MagicMock()
        mock_table_reader.return_value.__enter__.return_value = mock_table

        hanning_task = Hanning(inputs=self.inputs)
        hs_dict = {0: True, 1: False, 2: True}

        hanning_task._track_hsmooth(hs_dict)

        # Verify addcols was called
        mock_table.addcols.assert_called_once()
        call_args = mock_table.addcols.call_args[0][0]
        assert 'OFFLINE_HANNING_SMOOTH' in call_args

    @patch('pipeline.hifv.tasks.hanning.hanning.casa_tools.TableReader')
    def test_track_hsmooth_writes_values(self, mock_table_reader: MagicMock) -> None:
        """Test that _track_hsmooth writes smoothing flags to table."""
        mock_table = MagicMock()
        mock_table_reader.return_value.__enter__.return_value = mock_table

        hanning_task = Hanning(inputs=self.inputs)
        hs_dict = {0: True, 1: False}

        hanning_task._track_hsmooth(hs_dict)

        # Verify putcell was called for each SPW
        assert mock_table.putcell.call_count == 2
