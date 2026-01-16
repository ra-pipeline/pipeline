"""
The launcher module contains classes to initialize the pipeline, potentially
from a saved context state.
"""
import contextvars
import datetime
import os
import pickle
import pprint
from typing import Any

from pipeline import domain, environment

from . import callibrary, casa_tools, eventbus, imagelibrary, logging, project, utils
from .eventbus import ContextCreatedEvent, ContextResumedEvent

LOG = logging.get_logger(__name__)

# minimum allowed CASA revision. Set to 0 or None to disable
MIN_CASA_REVISION = [6, 6, 6, 16]
# maximum allowed CASA revision. Set to 0 or None to disable
MAX_CASA_REVISION = None

# Define the thread-safe context variable here for the current task executaton state
current_task_name = contextvars.ContextVar('current_task_name', default=None)


class Context:
    """
    Context holds all pipeline state, consisting of metadata describing the
    data set, objects describing the pipeline calibration state, the tree of
    Results objects summarising the results of each pipeline task, and a
    small number of internal pipeline variables and objects.

    The aim of the Context class is to provide one central object to which all
    pipeline state is attached. Keeping all state in one object makes it easy
    to persist this one object, and thus all state, to disk as a Python pickle,
    allowing pipeline sessions to be interrupted and resumed.

    Attributes:
        name: Name of the context; also forms the root of the filename used for
            the pickled state.

        output_dir: The working directory where pipeline output data should be saved.
        products_dir: The directory where pipeline products should be exported to.
        report_dir: The directory where pipeline HTML reports should be saved.

        logs: Dictionary containing the filenames to use for standard output
            files (CASA commands log, AQUA report, pipeline script, restore script).

        results: The list of task result (proxy) objects containing summaries
            of each executed task in the pipeline run.
        task_counter: Index of the last task to complete.
        subtask_counter: Index of the last subtask to complete.

        observing_run: The top-level ObservingRun object through which all other
            pipeline.domain objects can be accessed.

        project_performance_parameters: ALMA OUS project performance information.
        project_structure: ALMA project structure information.
        project_summary: Project summary information.

        calimlist: The ImageLibrary object holding final images of calibrators.
        callibrary: The CalLibrary object holding the calibration state for
            registered measurement sets.
        clean_list_info: Dictionary to store information about the target image
            to-be-cleaned list; typically populated by hif_makeimlist.
        clean_list_pending: List of hif.tasks.makeimlist.cleantarget.CleanTarget
            objects representing what target images are to be cleaned; typically
            populated by hif_makeimlist, or edited by hif_editimlist.
        clean_masks: Dictionary to store the names of clean masks to be re-used
            for TARGET IQUV imaging.
        clean_thresholds: Dictionary to store thresholds to be re-used for
            TARGET IQUV imaging.
        contfile: Name of file with frequency ranges to use for continuum
            images; typically populated by hif_makeimlist.
        imaging_mode: Imaging mode string; may be used to switch between imaging
            parameter heuristics; currently only used for deciding what products
            to export.
        imaging_parameters: Dictionary containing computed values to use for
            certain parameters during imaging; typically populated by
            hifa_imageprecheck.
        linesfile: Name of file with line frequency ranges to exclude for
            continuum images; typically populated by hif_makeimlist.
        per_spw_cont_sensitivities_all_chan: Dictionary containing some imaging
            parameters as well as sensitivity information; typically populated
            by hifa_imageprecheck, and potentially updated by hif_makeimages or
            hif_tclean.
        processing_intents: Dictionary of processing intents for the current
            pipeline run. Currently, the following options are known:
            - {'INTERFEROMETRY_STANDARD_OBSERVING_MODE': 'Undefined'}
            - {'VLA_INTERFEROMETRY_STANDARD_OBSERVING_MODE': 'Undefined'}
            - {'INTERFEROMETRY_FULL_POL_CUBE_IMAGING': True}
            - {'INTERFEROMETRY_HETEROGENEOUS_IMAGING': True}
            - {'SINGLEDISH_STANDARD_OBSERVING_MODE': 'Undefined'}
        rmsimlist: The ImageLibrary object holding RMS uncertainty images of the
            science targets.
        sciimlist: The ImageLibrary object holding final images of science targets.
        selfcal_resources: List of files/tables required for the
            self-calibration restoration.
        selfcal_targets: List of targets for which self-calibration is performed.
        size_mitigation_parameters: Dictionary containing imaging product size
            mitigation parameters; typically populated by hif_checkproductsize,
            and used by hif_makeimlist.
        subimlist: The ImageLibrary object holding cut-out images of the science
            targets.
        synthesized_beams: Dictionary containing some imaging parameters as well
            computed synthesized beam information; typically populated/updated
            by hifa_imageprecheck, hif_checkproductsize, hif_makeimlist,
            hif_makeimages, and hif_tclean.
    """
    def __init__(self, name: str | None = None) -> None:
        """
        Initialize a Context object.

        Args:
            name: Name of the context.
        """
        if name is None:
            # initialise the context name with something reasonable: a current
            # timestamp
            now = datetime.datetime.utcnow()
            name = now.strftime('pipeline-%Y%m%dT%H%M%S')
        self.name = name

        # Define default file paths for working output, weblog, export products.
        self.output_dir = ''
        self.products_dir = None
        LOG.trace('Setting products directory: %s', self.products_dir)
        self.report_dir = os.path.join(self.output_dir, self.name, 'html')
        LOG.trace('Creating report directory: %s', self.report_dir)
        utils.mkdir_p(self.report_dir)

        # Define default filenames for output logs, scripts, AQUA report.
        self.logs: dict[str, str | list] = dict(
            casa_commands='casa_commands.log',
            pipeline_script='casa_pipescript.py',
            pipeline_restore_script='casa_piperestorescript.py',
            aqua_report='pipeline_aquareport.xml'
        )

        # Define list of task results and task counters.
        self.results = []
        self.task_counter = 0
        self.subtask_counter = 0
        LOG.trace('Pipeline stage counter set to {0}'.format(self.stage))

        # Define list of processing intents.
        self.processing_intents = dict()

        # Define observing run.
        self.observing_run = domain.ObservingRun()

        # Define project information.
        self.project_performance_parameters = project.PerformanceParameters()
        self.project_structure = project.ProjectStructure()
        self.project_summary = project.ProjectSummary()

        # Initialize task inputs that are populated after init / importdata.
        self.calimlist = imagelibrary.ImageLibrary()
        self.callibrary = callibrary.CalLibrary(self)
        self.clean_list_info = {}  # CAS-9456
        self.clean_list_pending = []  # CAS-10146
        self.clean_masks = {} # PIPE-2464
        self.clean_thresholds = {} # PIPE-2464
        self.contfile: str | None = None
        self.imaging_mode: str | None = None  # PIPE-592
        self.imaging_parameters = {}  # CAS-10146
        self.linesfile: str | None = None
        self.per_spw_cont_sensitivities_all_chan = {'robust': None, 'uvtaper': None}  # CAS-11211
        self.rmsimlist = imagelibrary.ImageLibrary()  # CAS-9632
        self.sciimlist = imagelibrary.ImageLibrary()
        self.selfcal_resources: list[str] = []  # PIPE-1802
        self.selfcal_targets = []  # PIPE-1802
        self.size_mitigation_parameters = {}  # CAS-9255
        self.subimlist = imagelibrary.ImageLibrary()  # CAS-10345
        self.synthesized_beams = {'robust': None, 'uvtaper': None}

        # Log context creation event.
        event = ContextCreatedEvent(context_name=self.name, output_dir=self.output_dir)
        eventbus.send_message(event)

    @property
    def stage(self) -> str:
        """Return task and sub-task stage number."""
        return f'{self.task_counter}_{self.subtask_counter}'

    @property
    def products_dir(self) -> str:
        """Return path to the products directory."""
        return self._products_dir

    @products_dir.setter
    def products_dir(self, value: str | None) -> None:
        """
        Set path to the products directory.

        Args:
            value: path to use for products directory; if None, it will default
                to using the path ../products, relative to the output_dir (aka
                working directory).
        """
        if value is None:
            value = os.path.join('../', 'products')

        value = os.path.relpath(value, self.output_dir)
        LOG.trace('Setting products_dir: %s', value)
        self._products_dir = value

    def save(self, filename: str | None = None) -> None:
        """
        Save a pickle of the Context to a file with given filename.

        Args:
            filename: Name of the context file. If None, this will be set to
                <context name>.context.
        """
        if filename in ('', None):
            filename = f'{self.name}.context'

        with open(filename, 'wb') as context_file:
            LOG.info('Saving context: %s', filename)
            pickle.dump(self, context_file, protocol=-1)

    def __str__(self) -> str:
        ms_names = [ms.name
                    for ms in self.observing_run.measurement_sets]
        return ('Context(name=\'{0}\', output_dir=\'{1}\')\n'
                'Registered measurement sets:\n{2}'
                ''.format(self.name, self.output_dir,
                          pprint.pformat(ms_names)))

    def __repr__(self) -> str:
        return f"<Context(name='{self.name}')>"

    def set_state(self, cls: str, name: str, value: Any) -> None:
        """
        Set a context property using the class name, property name and property
        value.

        The class name should be one of:

         1. 'ProjectSummary'
         2. 'ProjectStructure'
         3. 'PerformanceParameters'

        Background: see CAS-9497 - add infrastructure to translate values from
        intent.xml to setter functions in casa_pipescript.

        Args:
            cls: Class identifier.
            name: Property to set.
            value: Value to set.
        """
        m = {
            'ProjectSummary': self.project_summary,
            'ProjectStructure': self.project_structure,
            'PerformanceParameters': self.project_performance_parameters
        }
        instance = m[cls]
        setattr(instance, name, value)

    def get_oussid(self) -> str:
        """
        Get the parent OUS 'ousstatus' name. This is the sanitized OUS
        status UID.
        """
        ps = self.project_structure
        if ps is None or ps.ousstatus_entity_id == 'unknown':
            return 'unknown'
        else:
            return ps.ousstatus_entity_id.translate(str.maketrans(':/', '__'))

    def get_recipe_name(self) -> str:
        """Get the recipe name from project structure."""
        ps = self.project_structure
        if ps is None or ps.recipe_name == 'Undefined':
            return ''
        else:
            return ps.recipe_name


class Pipeline:
    """
    Pipeline is the entry point for initialising the pipeline. It is
    responsible for the creation of new Context objects and for loading
    saved Contexts from disk.

    Attributes:
        context: Context object containing the Pipeline state information.
    """
    def __init__(self, context: str | None = None, loglevel: str = 'info', casa_version_check: bool = True,
                 name: str | None = None, plotlevel: str = 'default', path_overrides: dict | None = None,
                 processing_intents: dict = None):
        """
        Initialise the pipeline, creating a new Context or loading a saved
        Context from disk.

        Args:
            context: Filename of the pickled Context to load from disk.
                Specifying 'last' loads the last-saved Context, while passing
                None creates a new Context.
            loglevel: Pipeline log level.
            casa_version_check: enable (True) or bypass (False) the CASA version
                check. Default is True.
            name: If not "None", this overrides the name of the Pipeline Context
                if a new context needs to be created.
            plotlevel: Pipeline plots level.
            path_overrides: Optional dictionary containing context properties to
                be redefined when loading existing context (e.g. "name").
            processing_intents: Dictionary of processing intents for the current
                pipeline run.
        """
        # configure logging with the preferred log level
        logging.set_logging_level(level=loglevel)

        # Prevent users from running the pipeline on old or incompatible
        # versions of CASA by comparing the CASA subversion revision against
        # our expected minimum and maximum
        if casa_version_check is True:
            if MIN_CASA_REVISION and environment.compare_casa_version('<', MIN_CASA_REVISION):
                msg = ('Minimum CASA revision for the pipeline is %s, '
                       'got CASA %s.' % (MIN_CASA_REVISION, environment.casa_version))
                LOG.critical(msg)
            if MAX_CASA_REVISION and environment.compare_casa_version('>', MAX_CASA_REVISION):
                msg = ('Maximum CASA revision for the pipeline is %s, '
                       'got CASA %s.' % (MAX_CASA_REVISION, environment.casa_version))
                LOG.critical(msg)

        # if no previous context was specified, create a new context for the
        # given measurement set
        if context is None:
            self.context = Context(name=name)

        # otherwise load the context from disk..
        else:
            # .. by finding either last session, or..
            if context == 'last':
                context = self._find_most_recent_session()

            # .. the user-specified file
            with open(context, 'rb') as context_file:
                LOG.info('Reading context: %s', context)
                last_context = utils.pickle_load(context_file)
                self.context = last_context

                event = ContextResumedEvent(context_name=last_context.name, output_dir=last_context.output_dir)
                eventbus.send_message(event)

            # If requested, redefine context properties with given overrides.
            if path_overrides is not None:
                for k, v in path_overrides.items():
                    setattr(self.context, k, v)

        if processing_intents is not None:
            self.context.processing_intents = processing_intents

        self._link_casa_log(self.context)

        # define the plot level as a global setting rather than on the
        # context, as we want it to be a session-wide setting and adjustable
        # mid-session for interactive use.
        import pipeline.infrastructure as infrastructure
        infrastructure.set_plot_level(plotlevel)

    def _link_casa_log(self, context: Context) -> None:
        """
        Create a hard-link to the current CASA log in the report directory,
        and add path to current CASA log to given Context.

        Args:
            context: Pipeline Context to update with path to current CASA log.
        """
        report_dir = context.report_dir

        # create a hard-link to the current CASA log in the report directory
        src = casa_tools.log.logfile()
        dst = os.path.join(report_dir, os.path.basename(src))
        if not os.path.exists(dst):
            try:
                os.link(src, dst)
            except OSError:
                LOG.error('Error creating hard link to CASA log')
                LOG.warning('Reverting to symbolic link to CASA log. This is unsupported!')
                try:
                    os.symlink(src, dst)
                except OSError:
                    LOG.error('Well, no CASA log for you')

        # the web log creates links to each casa log. The name of each CASA
        # log is appended to the context.
        if 'casalogs' not in context.logs:
            # list as one casa log will be created per CASA session
            context.logs['casalogs'] = []
        if src not in context.logs['casalogs']:
            context.logs['casalogs'].append(os.path.basename(dst))

    @staticmethod
    def _find_most_recent_session(directory: str = './') -> str:
        """
        Return filename for the most recently saved Pipeline Context in given directory.

        Args:
            directory: Path where to search for context files.

        Returns:
            Filename of most recently saved Pipeline Context file.

        Raises:
            FileNotFoundError if no Pipeline context files are found in given directory.
        """
        # list all the files in the directory..
        files = [f for f in os.listdir(directory) if f.endswith('.context')]

        if len(files) == 0:
            raise FileNotFoundError(f'No pipeline context exists in {os.path.abspath(directory)}')

        # .. and from these matches, create a dict mapping files to their
        # modification timestamps, ..
        name_n_timestamp = dict([(f, os.stat(directory+f).st_mtime)
                                 for f in files])

        # .. then return the file with the most recent timestamp
        return max(name_n_timestamp, key=name_n_timestamp.get)

    def __repr__(self) -> str:
        ms_names = [ms.name
                    for ms in self.context.observing_run.measurement_sets]
        return 'Pipeline({0})'.format(ms_names)

    def close(self) -> None:
        """Save a pickle of the Pipeline Context to a file."""
        self.context.save()
