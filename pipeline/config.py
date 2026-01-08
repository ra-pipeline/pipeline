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
from typing import Any, Optional

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


def casatasks_startup(casa_config: dict[str, Optional[str]], loglevel: Optional[str] = None) -> tuple[str, str]:
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

    # Update casaconfig attributes
    for key, value in config['casaconfig'].items():
        if value is None:
            config['casaconfig'][key] = getattr(casaconfig.config, key, None)
        else:
            setattr(casaconfig.config, key, value)
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
