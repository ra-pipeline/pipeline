"""Config loading and CASA/pipeline environment construction for calibPipeIF.py
and runbatch.py.

Replaces the old pattern of per-person `pipeline_env_<name>.sh` files that
each just picked a CASA_ROOT/PIPE_BRANCH and re-sourced a shared
`env_core2.sh`. That shell script turned out to be pure path/string logic
(plus a couple of `mkdir -p` calls) once its interactive-prompt block is
dropped, so it's ported here directly instead of being shelled out to.

Personal/site data lives in a TOML file that is NOT part of this repo -- see
config.example.toml for the schema and find_config_path() for how a file is
located.
"""

import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # needed on Python < 3.11 (e.g. CASA's bundled python)


# Site-wide defaults, the same for everyone at NAASC. Only set the optional
# [site] table in a personal config.toml to override any of these.
SITE_DEFAULTS = {
    "java_home": "/usr/lib/jvm/java-21-openjdk-21.0.6.0.7-1.el8.x86_64",
    "pmr_home": "/home/pipetools/latest/build",
    "acsdata": "/home/pipedrive/acsdata",
    "datapacker_home": "/home/pipedrive/datapacker/current",
    "flux_service_url": "https://almascience.org/sc/flux",
    "flux_service_url_backup": "https://asa.alma.cl/sc/flux",
    "casa_enable_telemetry": False,
    "submit_host": None,  # runbatch.py host guard; None = no check
}


class ConfigError(Exception):
    pass


def find_config_path(cli_arg=None):
    """Resolve which TOML config file to use.

    Order: --config=<path> > $CALIBPIPE_CONFIG > config.toml in the same
    directory as this file (i.e. wherever calibPipeIF.py itself is checked
    out or copied to -- typically a pipeline checkout's scripts/ dir).
    """
    if cli_arg:
        path = Path(cli_arg).expanduser()
        if not path.exists():
            raise ConfigError(f"--config file not found: {path}")
        return path

    env_path = os.environ.get("CALIBPIPE_CONFIG")
    if env_path:
        path = Path(env_path).expanduser()
        if not path.exists():
            raise ConfigError(f"$CALIBPIPE_CONFIG file not found: {path}")
        return path

    local_default = Path(__file__).resolve().parent / "config.toml"
    if local_default.exists():
        return local_default

    raise ConfigError(
        "No config file found. Pass --config=<path>, set $CALIBPIPE_CONFIG, "
        f"or create {local_default} (see config.example.toml for the schema)."
    )


def load_config(path):
    with open(path, "rb") as fd:
        return tomllib.load(fd)


def resolve_env(config, env_name=None):
    """Look up an [envs.<name>] table, defaulting to the config's default_env."""
    envs = config.get("envs", {})
    if not envs:
        raise ConfigError("Config file has no [envs.*] tables defined.")

    name = env_name or config.get("default_env")
    if not name:
        raise ConfigError(
            "No --env given and config file has no default_env set."
        )
    if name not in envs:
        available = ", ".join(sorted(envs))
        raise ConfigError(f"No [envs.{name}] in config file. Available: {available}")

    env_spec = dict(envs[name])
    env_spec.setdefault("name", name)
    env_spec.setdefault("branch", name)
    if "casa_root" not in env_spec:
        raise ConfigError(f"[envs.{name}] is missing casa_root")
    return env_spec


def build_environment(config, env_spec):
    """Port of env_core2.sh: given a resolved env_spec, return the full
    environment dict a CASA/pipeline subprocess should run with.
    """
    paths = config.get("paths", {})
    site = {**SITE_DEFAULTS, **config.get("site", {})}
    user = os.environ.get("USER", "")

    casa_root = env_spec["casa_root"].rstrip("/")
    branch = env_spec["branch"]
    casa_path = f"{casa_root}/bin"

    env = os.environ.copy()
    env["CASA_ROOT"] = casa_root
    env["CASA_PATH"] = casa_path
    env["PIPE_BRANCH"] = branch

    if "heuristics_dir" in env_spec:
        heuristics = env_spec["heuristics_dir"].format(casa_root=casa_root, branch=branch)
    else:
        heuristics_root = paths.get("heuristics_root")
        if heuristics_root:
            heuristics = f"{heuristics_root.rstrip('/')}/{branch}"
        else:
            # No heuristics_root configured: assume calibPipeIF.py is being
            # run from inside a pipeline branch checkout's own scripts/
            # directory, and that checkout itself (one level up) is the
            # heuristics to use.
            heuristics = str(Path(__file__).resolve().parent.parent)
    env["SCIPIPE_HEURISTICS"] = heuristics
    env["SCIPIPE_SCRIPTDIR"] = f"{heuristics}/pipeline/recipes"

    for var, key, required in (
        ("SCIPIPE_ROOTDIR", "scipipe_rootdir", True),
        ("SCIPIPE_LOGDIR", "scipipe_logdir", True),
    ):
        template = paths.get(key)
        if not template:
            if required:
                raise ConfigError(f"[paths].{key} is required")
            continue
        resolved = template.format(user=user)
        os.makedirs(resolved, exist_ok=True)
        env[var] = resolved

    env["JAVA_HOME"] = site["java_home"]
    env["ACSDATA"] = site["acsdata"]
    env["ACSROOT"] = site["pmr_home"]
    env["DATAPACKER_HOME"] = site["datapacker_home"]
    env["JARSDIR"] = f"{site['datapacker_home']}/lib"
    env["FLUX_SERVICE_URL"] = site["flux_service_url"]
    env["FLUX_SERVICE_URL_BACKUP"] = site["flux_service_url_backup"]
    env["CASA_ENABLE_TELEMETRY"] = "true" if site["casa_enable_telemetry"] else "false"

    pmr_bin = f"{site['pmr_home']}/bin"
    path_parts = env.get("PATH", "").split(":")
    for prepend in (casa_path, pmr_bin):
        if prepend in path_parts:
            path_parts.remove(prepend)
        path_parts.insert(0, prepend)
    env["PATH"] = ":".join(path_parts)

    env["MATPLOTLIBRC"] = str(Path.home() / ".casa" / "matplotlib")

    return env
