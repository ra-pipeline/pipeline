"""Pipeline configuration management and CASA task initialization.

This module handles the loading of pipeline configuration and the early initialization
of CASA tasks. It is imported at the start of a pipeline process to ensure that
`casaconfig` parameters are customized before `casatasks` is imported and its
configuration is frozen.

The module aggregates configuration from multiple sources, including built-in defaults,
user-specific cache files, and local configuration files. It also manages the setup
of CASA logging and environment settings based on the loaded configuration.
"""
import copy
import os
import pathlib
import pprint
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


def casaconfig_startup(casa_config: dict[str, str | None] | None = None) -> dict:
    """Load the merged session configuration and apply ``casaconfig`` attributes.

    This is intentionally lightweight: it does **not** import :mod:`casatasks`
    and therefore does not trigger CASA C++ startup (log file creation, etc.).
    It runs at module import time so that downstream modules that read
    :data:`pipeline.config.config` see a fully-populated dict, while keeping
    ``import pipeline`` cheap.

    Args:
        casa_config: Reserved for future use; currently unused (kept for
            backwards-compatible signature with the legacy
            ``casatasks_startup`` entry point).

    Returns:
        The merged config dict (built-in defaults → user cache → ``./config.yaml``).
    """
    del casa_config  # currently unused; reserved for future per-call overrides

    # Suppress CASA log file creation during plain import (e.g. ``pipeline --help``).
    # Importing ``casatasks`` (which happens indirectly when the CLI loads task modules)
    # triggers ``casatools`` C++ startup and would create a ``casa-*.log`` in the CWD.
    # Redirecting to ``/dev/null`` before that happens keeps the working directory clean.
    # ``casatasks_startup()``, called explicitly from ``pipeline.initialize()``, will
    # redirect to a real timestamped log file.
    casaconfig.config.logfile = os.devnull

    # load the session configuration from the built-in default and user config files
    _session_config = get_config(__configs__)
    cfg = copy.deepcopy(_session_config)

    # load any configuration inherited from the dask client.
    # Only merge if dask is already loaded — importing dask here at startup
    # costs ~90ms even when no dask cluster is needed.
    import sys
    if 'dask' in sys.modules:
        import dask
        cfg['casaconfig'].update(dask.config.config.get('casaconfig', {}))

    # Update casaconfig attributes
    for key, value in cfg['casaconfig'].items():
        if value is None:
            cfg['casaconfig'][key] = getattr(casaconfig.config, key, None)
        else:
            setattr(casaconfig.config, key, value)

    return cfg


_CASATASKS_STARTED = False


def casatasks_startup(loglevel: str | None = None) -> None:
    """Import :mod:`casatasks` and configure the CASA log session.

    Splits the casatasks-dependent half of the legacy startup out of import
    time so that it can be invoked **explicitly** by pipeline entry points
    (CLI ``run``, :func:`pipeline.recipereducer.reduce`,
    :func:`pipeline.infrastructure.executeppr.executeppr`).  This avoids the
    CASA C++ initialization cost for callers that only need ``import pipeline``
    (``pipeline --help``, ``pipeline submit``, tooling, tests that don't run
    a pipeline).

    Idempotent: subsequent calls only re-apply the ``casalog`` filter / logfile
    bookkeeping, which is cheap.

    Args:
        loglevel: Optional pipeline log level string (currently informational;
            the CASA filter is fixed at ``INFO1`` so the pipeline can map
            ``INFO1`` → ATTENTION).
    """
    global _CASATASKS_STARTED
    del loglevel  # signature compatibility; not currently used here

    # casatasks import triggers CASA C++ session creation (logfile, etc.) on
    # first call.  Subsequent calls are no-ops at the import level.
    import casatasks

    # If the logfile was suppressed to /dev/null (the default set by casaconfig_startup
    # to keep plain ``import pipeline`` clean), create a real timestamped log now that
    # initialize() has been called.
    if casatasks.casalog.logfile() == os.devnull:
        import datetime
        _ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        _real_logfile = os.path.join(os.getcwd(), f'casa-{_ts}.log')
        casatasks.casalog.setlogfile(_real_logfile)

    casalogfile = casatasks.casalog.logfile()

    # adjust the log filtering level for casalogsink: by default, INFO1 lets
    # the pipeline surface ATTENTION-level messages.
    casatasks.casalog.filter('INFO1')

    # record the actual logfile path so it can be forwarded to dask workers
    config['casaconfig']['logfile'] = casalogfile

    if not _CASATASKS_STARTED and config['casaconfig'].get('log2term', False):
        # only necessary for a plain Python session; a casashell session
        # already wires log2term via casaconfig in monolithic CASA6.
        casatasks.casalog.showconsole(onconsole=True)

    _CASATASKS_STARTED = True


def get_pipeline_config(key: str, default: Any = None, *, env_var: str | None = None, as_type: type | None = None) -> Any:
    """Resolve a pipeline config value with env-var override.

    Traverses ``config['pipeconfig']`` using a dot-separated *key* path
    (e.g. ``'heuristics.pipe356_qa_mode'``).  If the key is missing or
    ``config`` has not been loaded yet, *default* is returned.

    When *env_var* is given and the corresponding environment variable is
    set, that value takes precedence over the config file.  For boolean
    settings, the strings ``'true'``, ``'1'``, and ``'yes'`` (case-insensitive)
    are treated as ``True``; everything else as ``False``.

    Args:
        key: Dot-separated path under ``pipeconfig``, e.g. ``'services.antpos_url'``.
        default: Fallback value when the key is absent.
        env_var: Optional environment variable name that overrides the config.
        as_type: Optional type coercion (currently only ``bool`` triggers
                 special string parsing for environment variable values).

    Returns:
        The resolved configuration value.
    """
    # Walk nested dicts
    try:
        value = config.get('pipeconfig', {})
        for part in key.split('.'):
            value = value[part]
    except (KeyError, TypeError, AttributeError):
        value = default

    # Env-var override
    if env_var is not None:
        env_value = os.getenv(env_var)
        if env_value is not None:
            if as_type is bool:
                value = env_value.lower() in ('true', '1', 'yes')
            else:
                value = env_value

    return value


config = casaconfig_startup()
