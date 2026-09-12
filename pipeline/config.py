"""Pipeline configuration management and CASA task initialization.

This module handles the loading of pipeline configuration and the early initialization
of CASA tasks. It is imported at the start of a pipeline process to ensure that
`casaconfig` parameters are customized before `casatasks` is imported and its
configuration is frozen.

The module aggregates configuration from multiple sources, including built-in defaults,
user-specific cache files, and local configuration files. It also manages the setup
of CASA logging and environment settings based on the loaded configuration.
"""
import atexit
import copy
import getpass
import os
import pathlib
import pprint
import shutil
import sys
from typing import Any

import casaconfig.config
import yaml

__builtin_config__ = os.path.realpath(os.path.join(__file__, '../config.yaml'))
__configs__ = [__builtin_config__, os.path.join(casaconfig.config.cachedir, 'config.yaml'), 'config.yaml']


def get_config(conf_files, conf_user=None, env=True, verbose=False):
    """Loads configuration from YAML files.

    Args:
        cfg_name (list): List of YAML or .cfg file paths to load
        env (bool): Whether to override with environment variables
        verbose (bool): print out extra debug messages
    """
    if isinstance(conf_files, str):
        file_list = [conf_files]
    else:
        file_list = conf_files

    conf = {}

    for filename in file_list:
        conf_filename = os.path.abspath(os.path.expanduser(os.path.expandvars(filename)))
        if conf_filename and os.path.exists(conf_filename):
            file_ext = pathlib.Path(conf_filename).suffix
            if file_ext in ('.yaml', 'yml'):
                with open(conf_filename, 'r', encoding='utf-8') as file:
                    conf_per_file = yaml.safe_load(file)
                if verbose:
                    pprint.pprint(conf_filename)
                    pprint.pprint(conf_per_file)
                if conf_per_file:
                    conf = nested_update(conf, conf_per_file)
    if env:
        # not working yet
        for k, v in conf.items():
            if k in os.environ:
                conf[k] = os.environ[k]
    if conf_user:
        conf = nested_update(conf, conf_user)

    return conf


def _get_flat_keys_and_values(d: Any, parent_key: str = '') -> list[tuple[str, Any]]:
    """Recursively flattens a nested dictionary into a list of key-value pairs.

    Each key in the output represents the full path to the value in the
    original nested structure, with path components joined by dots.

    Args:
        d: The dictionary or value to flatten.
        parent_key: The base key to prepend to the keys found in `d`.
                    Used for recursive calls to build the full path.

    Returns:
        A list of (key, value) tuples representing the flattened structure.
    """
    ret = []  # Initialize the list to store flattened key-value pairs

    # Check if the current item is a dictionary
    if isinstance(d, dict):
        # Iterate through key-value pairs if it's a dictionary
        for k, v in d.items():
            # Construct the full key path, adding a dot separator if not the top level
            full_key = f'{parent_key}.{k}' if parent_key else k
            # Recursively call the function for the value and extend the results
            ret.extend(_get_flat_keys_and_values(v, full_key))
    else:
        # If the item is not a dictionary, it's a value to append
        ret.append((parent_key, d))

    # Return the accumulated list of flattened key-value pairs
    return ret


def show_config(verbose: bool = True) -> list:
    """Shows or returns the current configuration.

    Retrieves the flattened key-value pairs of the global configuration
    object. If verbose mode is enabled, it also pretty-prints the
    configuration details to standard output.

    Args:
        verbose: If True, pretty-prints the configuration details.

    Returns:
        A list containing the flattened key-value pairs of the configuration.
    """
    config_list = _get_flat_keys_and_values(config)

    if verbose:
        pprint.pprint(config_list)

    return config_list


def nested_update(d: dict[str, Any], u: dict[str, Any]) -> dict[str, Any]:
    """Recursively update a nested dictionary `d` with the key-value pairs from another dictionary `u`.

    Args:
        d: The target nested dictionary to be updated.
        u: The dictionary containing key-value pairs to update `d`.

    Returns:
        The updated nested dictionary `d` after recursively merging with `u`.
        Note that the update is performed in-place on `d`.

    Examples:
        >>> d = {'a': 1, 'b': {'c': 2}}
        >>> u = {'b': {'d': 3}, 'e': 4}
        >>> nested_update(d, u)
        {'a': 1, 'b': {'c': 2, 'd': 3}, 'e': 4}
        >>> d  # d is updated in-place
        {'a': 1, 'b': {'c': 2, 'd': 3}, 'e': 4}
        >>> d2 = {'a': 1, 'b': 5}  # Example where d[k] is not a dict
        >>> u2 = {'b': {'d': 3}, 'e': 4}
        >>> nested_update(d2, u2)
        {'a': 1, 'b': {'d': 3}, 'e': 4}
        >>> d2
        {'a': 1, 'b': {'d': 3}, 'e': 4}
    """
    for k, v in u.items():
        if isinstance(v, dict):
            d[k] = nested_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def stage_local_measures(source_path: str | None = None,
                         base_dir: str | None = None,
                         cleanup: bool | None = None) -> str | None:
    """Stage dynamic measures tables (geodetic) and link static rundata to node-local scratch storage.

    This protects pipeline runs from mid-execution corruption caused by in-place
    updates (e.g. daily cron rsync/git pull) on shared network mounts. Only geodetic/
    (~9.5 MB) is actively modified by daily measures updates, so it is physically copied,
    while static ephemerides/ (~415 MB) and other static rundata directories (alma, catalogs,
    nrao, etc.) are symlinked (falling back to copy if symlink fails), yielding a minimal
    ~9.5 MB footprint, near-instant staging (< 0.05s), and satisfying casaconfig validation.

    Args:
        source_path: Source directory containing measures data (with geodetic/ subfolder).
                     Defaults to pipeconfig.local_measures_source, $PIPELINE_LOCAL_MEASURES_SOURCE,
                     $CASADATA, or casaconfig.config.measurespath / datapath.
        base_dir: Scratch directory to hold the staged folder.
                  Defaults to pipeconfig.local_measures_base, $PIPELINE_LOCAL_MEASURES_BASE,
                  $SLURM_TMPDIR, $_CONDOR_SCRATCH_DIR, $TMPDIR, or /tmp.
        cleanup: Whether to register an atexit handler to delete the staged folder upon exit.
                 Defaults to $PIPELINE_CLEANUP_LOCAL_MEASURES or True.

    Returns:
        Absolute path to the staged measures directory, or None if staging fails.
    """
    if cleanup is None:
        env_cleanup = os.environ.get('PIPELINE_CLEANUP_LOCAL_MEASURES')
        cleanup = env_cleanup.lower() in ('true', '1', 'yes') if env_cleanup is not None else True
    candidates = []
    if source_path:
        candidates.append(source_path)
    if os.environ.get('PIPELINE_LOCAL_MEASURES_SOURCE'):
        candidates.append(os.environ['PIPELINE_LOCAL_MEASURES_SOURCE'])
    if os.environ.get('CASADATA'):
        candidates.append(os.environ['CASADATA'])
    if hasattr(casaconfig.config, 'measurespath') and casaconfig.config.measurespath:
        candidates.append(casaconfig.config.measurespath)
    if 'casatools' in sys.modules:
        try:
            import casatools
            if hasattr(casatools.ctsys, 'measurespath'):
                mpath = casatools.ctsys.measurespath()
                if mpath:
                    candidates.append(mpath)
            if hasattr(casatools.ctsys, 'rundata'):
                rpath = casatools.ctsys.rundata()
                if rpath:
                    candidates.append(rpath)
        except Exception:
            pass
    if hasattr(casaconfig.config, 'datapath') and isinstance(casaconfig.config.datapath, list):
        candidates.extend(casaconfig.config.datapath)
    if 'casatools' in sys.modules:
        try:
            import casatools
            if hasattr(casatools.ctsys, 'getpath'):
                gpath = casatools.ctsys.getpath()
                if isinstance(gpath, list):
                    candidates.extend(gpath)
        except Exception:
            pass

    resolved_source = None
    for cand in candidates:
        if cand and isinstance(cand, str):
            expanded = os.path.abspath(os.path.expanduser(os.path.expandvars(cand)))
            if os.path.isdir(os.path.join(expanded, 'geodetic')):
                resolved_source = expanded
                break

    if not resolved_source:
        sys.stderr.write("WARNING [pipeline]: Unable to locate valid source measures directory to stage locally.\n")
        return None

    if not base_dir:
        base_dir = (
            os.environ.get('PIPELINE_LOCAL_MEASURES_BASE')
            or os.environ.get('SLURM_TMPDIR')
            or os.environ.get('_CONDOR_SCRATCH_DIR')
            or os.environ.get('CONDOR_SCRATCH_DIR')
            or os.environ.get('TMPDIR')
            or '/tmp'
        )
    base_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(base_dir)))

    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get('USER') or os.environ.get('LOGNAME') or 'casa'
    job_id = (
        os.environ.get('SLURM_JOB_ID')
        or os.environ.get('CONDOR_JOB_ID')
        or (f"{os.environ['ClusterId']}.{os.environ.get('ProcId', '0')}" if 'ClusterId' in os.environ else None)
        or os.environ.get('JOB_ID')
    )
    pid = os.getpid()
    folder_name = f"casarundata_{user}_{job_id}_{pid}" if job_id else f"casarundata_{user}_{pid}"
    target_dir = os.path.join(base_dir, folder_name)

    try:
        os.makedirs(target_dir, exist_ok=True)
        # 1. Copy dynamic geodetic tables (~9.5 MB) to protect against in-place cron updates
        src_geo = os.path.join(resolved_source, 'geodetic')
        dst_geo = os.path.join(target_dir, 'geodetic')
        if os.path.isdir(src_geo) and not os.path.exists(dst_geo):
            shutil.copytree(src_geo, dst_geo, dirs_exist_ok=True)

        # 2. Link static runtime data: ephemerides (~415 MB), catalogs, alma, nrao, etc.
        # These are static runtime tables untouched by the daily measures cron. Symlinking them
        # satisfies casacore C++ path resolution and casaconfig directory structure validation
        # (avoiding 'casarundata is invalid' warnings) with zero copy overhead, keeping the
        # process disk footprint at ~9.5 MB.
        try:
            entries = os.listdir(resolved_source)
        except Exception:
            entries = ['ephemerides']

        for item in entries:
            if item == 'geodetic' or item.startswith('.'):
                continue
            src_item = os.path.join(resolved_source, item)
            dst_item = os.path.join(target_dir, item)
            if not os.path.exists(dst_item):
                try:
                    os.symlink(src_item, dst_item)
                except OSError:
                    # Fallback for ephemerides if symlinks are not permitted on the filesystem
                    if item == 'ephemerides' and os.path.isdir(src_item):
                        shutil.copytree(src_item, dst_item, dirs_exist_ok=True)

        if cleanup:
            def _cleanup_dir():
                try:
                    if os.path.exists(target_dir):
                        shutil.rmtree(target_dir, ignore_errors=True)
                except Exception:
                    pass
            atexit.register(_cleanup_dir)

        return target_dir
    except Exception as exc:
        sys.stderr.write(f"WARNING [pipeline]: Failed to stage measures locally to {target_dir}: {exc}. Falling back to {resolved_source}.\n")
        return None


def casatasks_startup(casa_config: dict[str, str | None], loglevel: str | None = None) -> tuple[str, str]:
    """Initializes a CASA session with custom configurations and log settings.

    This function updates the casaconfig attributes, sets the CASA log file, and adjusts
    the log filtering level for casalogsink.

    Args:
        casa_config: A dictionary containing CASA configuration attributes. Keys are
                     attribute names (e.g., 'logfile', 'nworkers'), and values are the
                     desired settings. Values can be None, in which case the attribute
                     is not modified.
        loglevel: Optional pipeline log level string:
            critical, error, warning, attention, info, debug, todo, trace.
            If provided, the CASA log filter level is adjusted accordingly. If None,
            casa loglevel defaults to 'INFO1'.

    Returns:
        A tuple containing:
            - The path to the CASA log file (str).
            - The CASA log filter level (str).
    """
    # load the session configuration fom the built-in default and user config files
    _session_config = get_config(__configs__)
    config = copy.deepcopy(_session_config)

    # load any configuration inheriated from the dask client
    try:
        import dask
        config['casaconfig'].update(dask.config.config.get('casaconfig', {}))
    except ImportError:
        pass

    # Check if local measures staging is requested
    env_stage = os.environ.get('PIPELINE_STAGE_LOCAL_MEASURES')
    if env_stage is not None:
        stage_measures = env_stage.lower() in ('true', '1', 'yes')
    else:
        stage_measures = config.get('pipeconfig', {}).get('stage_local_measures', False)

    if stage_measures:
        local_source = config.get('pipeconfig', {}).get('local_measures_source')
        local_base = config.get('pipeconfig', {}).get('local_measures_base')
        env_cleanup = os.environ.get('PIPELINE_CLEANUP_LOCAL_MEASURES')
        if env_cleanup is not None:
            cleanup = env_cleanup.lower() in ('true', '1', 'yes')
        else:
            cleanup = config.get('pipeconfig', {}).get('cleanup_local_measures', True)
        staged_path = stage_local_measures(source_path=local_source, base_dir=local_base, cleanup=cleanup)
        if staged_path:
            config['casaconfig']['measurespath'] = staged_path
            config['casaconfig']['measures_auto_update'] = False
            config['casaconfig']['data_auto_update'] = False
            curr_datapath = config['casaconfig'].get('datapath')
            if curr_datapath and isinstance(curr_datapath, list):
                config['casaconfig']['datapath'] = [staged_path] + [p for p in curr_datapath if p != staged_path]
            elif hasattr(casaconfig.config, 'datapath') and isinstance(casaconfig.config.datapath, list):
                config['casaconfig']['datapath'] = [staged_path] + [p for p in casaconfig.config.datapath if p != staged_path]
            else:
                config['casaconfig']['datapath'] = [staged_path]

    # Update casaconfig attributes
    for key, value in config['casaconfig'].items():
        if value is None:
            config['casaconfig'][key] = getattr(casaconfig.config, key, None)
        else:
            setattr(casaconfig.config, key, value)

    # In case casatools has already been initialized (e.g. monolithic CASA session)
    if 'casatools' in sys.modules:
        try:
            import casatools
            if config['casaconfig'].get('measurespath'):
                mpath = config['casaconfig']['measurespath']
                casatools.ctsys.setmeasurespath(mpath)
                curr_path = casatools.ctsys.getpath()
                if isinstance(curr_path, list):
                    casatools.ctsys.setpath([mpath] + [p for p in curr_path if p != mpath])
        except Exception:
            pass

    # Initial import of casatasks with modified casaconfig setup
    import casatasks

    # Get the current casalogfile
    casalogfile = casatasks.casalog.logfile()

    # adjust the log filtering level for casalogsink
    # by default, modify filter to get INFO1 message which the pipeline
    # treats as ATTENTION level.

    # Adjust log filtering level
    casaloglevel = 'INFO1'
    casatasks.casalog.filter(casaloglevel)

    # Log measures configuration and verification
    try:
        import casatools
        mpath = casatools.ctsys.measurespath() if hasattr(casatools.ctsys, 'measurespath') else 'unknown'
        res_geo = casatools.ctsys.resolve('geodetic') if hasattr(casatools.ctsys, 'resolve') else 'unknown'
        res_eph = casatools.ctsys.resolve('ephemerides') if hasattr(casatools.ctsys, 'resolve') else 'unknown'
        if stage_measures and staged_path:
            casatasks.casalog.post(
                f"Local measures staging active: {staged_path} (geodetic: {res_geo})",
                priority='INFO', origin='pipeline.config'
            )
        casatasks.casalog.post(
            f"CASA runtime measures: ctsys.measurespath={mpath}, geodetic={res_geo}, ephemerides={res_eph}",
            priority='DEBUG', origin='pipeline.config'
        )
    except Exception:
        pass
    # print('current:', casalogfile, casaloglevel)
    # Another approach is using environment variable / Workplugin for initialization
    # But they will likely arrive after the import
    # Here, we get configuration directl during Piipeline importing process.

    # need the latest/actual casalogfile path to forward to worker
    config['casaconfig']['logfile'] = casalogfile

    if config['casaconfig'].get('log2term', False):
        # only nesscary for plain Python session as a casashell session
        # would use the casaconfig/log2term do it for you in monolithic CASA6.
        casatasks.casalog.showconsole(onconsole=True)

    return config


config = casatasks_startup({})
