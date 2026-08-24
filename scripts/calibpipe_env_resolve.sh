#!/usr/bin/env bash
#
# Standalone (no Python) resolver for calibPipeIF's CASA + ALMA-pipeline
# environment, read from the personal config.toml next to this script (see
# config.example.toml for the schema; envconfig.py is the Python
# implementation this is a shell port of -- keep the two in sync).
#
# This is the bash-specific worker: it always runs under an explicit `bash`
# interpreter (never `source`d) and prints `export ...` statements on
# stdout. It relies on bash-only syntax (C-style for loops, [[ ]], indexed
# arrays walked by numeric index) that a zsh `source` would parse under
# zsh's own rules and silently miscompute (1-indexed arrays, etc.), so it
# must not be sourced directly -- that's what the small, shell-portable
# `calibpipe_env.sh` dispatcher next to this file is for:
#
#   source calibpipe_env.sh --env=main   # <- what you actually want
#   pipelineMakeRequest ...
#   casa ...
#
# Calling this script directly still works for scripting/inspection:
#
#   eval "$(bash ./calibpipe_env_resolve.sh --env=main)"
#
# Options:
#   --config=<path>   TOML config file. Default: $CALIBPIPE_CONFIG, else
#                      config.toml next to this script.
#   --env=<name>       [envs.<name>] table to use. Default: the config
#                      file's default_env.
#   --subdir=<name>    Extra subdirectory appended to SCIPIPE_ROOTDIR.
#   --print-env        Print plain KEY=value lines (no `export`, no shell
#                       quoting) instead -- for inspection, e.g. diffing
#                       against `calibPipeIF.py --env=<name> --print-env`.
#   -h, --help          Show this help.

set -euo pipefail

err() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: calibpipe_env_resolve.sh [--config=<path>] [--env=<name>] [--subdir=<name>] [--print-env]

Resolves a [envs.<name>] table from a personal config.toml (see
config.example.toml) and prints the resulting CASA/pipeline environment as
`export KEY=value` shell statements. Normally invoked indirectly via
`source calibpipe_env.sh --env=main`; call this directly only for
scripting/inspection:

    eval "$(bash ./calibpipe_env_resolve.sh --env=main)"

Options:
  --config=<path>  TOML config file. Default: $CALIBPIPE_CONFIG, else
                    config.toml next to this script.
  --env=<name>      [envs.<name>] table to use. Default: the config file's
                    default_env.
  --subdir=<name>   Extra subdirectory appended to SCIPIPE_ROOTDIR.
  --print-env       Print plain KEY=value lines instead of `export ...`.
  -h, --help        Show this help.
EOF
}

# ---------------------------------------------------------------------------
# arg parsing

config_arg=""
env_name=""
subdir=""
print_env=0

for arg in "$@"; do
    case "$arg" in
        --config=*) config_arg="${arg#--config=}" ;;
        --env=*) env_name="${arg#--env=}" ;;
        --subdir=*) subdir="${arg#--subdir=}" ;;
        --print-env) print_env=1 ;;
        -h|--help) usage; exit 0 ;;
        *) err "unknown option: $arg (see --help)" ;;
    esac
done

# ---------------------------------------------------------------------------
# locate this script + resolve config path (mirrors envconfig.find_config_path)

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_PATH")" >/dev/null 2>&1 && pwd)"

if [[ -n "$config_arg" ]]; then
    config_path="${config_arg/#\~/$HOME}"
    [[ -e "$config_path" ]] || err "--config file not found: $config_path"
elif [[ -n "${CALIBPIPE_CONFIG:-}" ]]; then
    config_path="${CALIBPIPE_CONFIG/#\~/$HOME}"
    [[ -e "$config_path" ]] || err "\$CALIBPIPE_CONFIG file not found: $config_path"
else
    config_path="$SCRIPT_DIR/config.toml"
    [[ -e "$config_path" ]] || err "No config file found. Pass --config=<path>, set \$CALIBPIPE_CONFIG, or create $config_path (see config.example.toml for the schema)."
fi

# ---------------------------------------------------------------------------
# Minimal TOML-subset parser: top-level "key = value" pairs, and
# [paths]/[site]/[envs.<name>] tables of the same. Values are bare
# true/false or "double-quoted strings"; comments must be on their own
# line. That's the entire subset config.example.toml uses -- this is not a
# general TOML parser.
#
# Parsed into parallel-array (keys[], vals[]) tables rather than
# associative arrays so this runs on bash 3.2 as well as modern bash.

top_keys=(); top_vals=()
paths_keys=(); paths_vals=()
site_keys=(); site_vals=()
env_names_seen=()
env_keys=(); env_vals=()   # env_keys entries are "<envname>::<key>"

_trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

# _lookup <keys-array-name> <vals-array-name> <key>  -- prints the value and
# returns 0 if found, else returns 1. Uses eval-indirection instead of
# namerefs (declare -n is bash 4.3+) to stay bash-3.2-compatible.
_lookup() {
    local keys_name="$1" vals_name="$2" key="$3" i n k
    eval "n=\${#${keys_name}[@]}"
    for ((i = 0; i < n; i++)); do
        eval "k=\${${keys_name}[$i]}"
        if [[ "$k" == "$key" ]]; then
            eval "printf '%s' \"\${${vals_name}[$i]}\""
            return 0
        fi
    done
    return 1
}

section=""
while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    line="$(_trim "$raw_line")"
    [[ -z "$line" || "$line" == \#* ]] && continue

    if [[ "$line" =~ ^\[([A-Za-z0-9_.]+)\]$ ]]; then
        section="${BASH_REMATCH[1]}"
        if [[ "$section" == envs.* ]]; then
            env_names_seen+=("${section#envs.}")
        fi
        continue
    fi

    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
        key="${BASH_REMATCH[1]}"
        val="$(_trim "${BASH_REMATCH[2]}")"
        if [[ "$val" =~ ^\"(.*)\"$ ]]; then
            val="${BASH_REMATCH[1]}"
        fi
        case "$section" in
            "") top_keys+=("$key"); top_vals+=("$val") ;;
            paths) paths_keys+=("$key"); paths_vals+=("$val") ;;
            site) site_keys+=("$key"); site_vals+=("$val") ;;
            envs.*) env_keys+=("${section#envs.}::$key"); env_vals+=("$val") ;;
        esac
    fi
done < "$config_path"

# ---------------------------------------------------------------------------
# resolve env spec (mirrors envconfig.resolve_env)

if [[ ${#env_names_seen[@]} -eq 0 ]]; then
    err "Config file has no [envs.*] tables defined."
fi

if [[ -z "$env_name" ]]; then
    env_name="$(_lookup top_keys top_vals default_env || true)"
    [[ -n "$env_name" ]] || err "No --env given and config file has no default_env set."
fi

found=0
for n in "${env_names_seen[@]}"; do
    if [[ "$n" == "$env_name" ]]; then
        found=1
        break
    fi
done
if [[ "$found" -eq 0 ]]; then
    available="$(printf '%s\n' "${env_names_seen[@]}" | sort -u | paste -sd, - | sed 's/,/, /g')"
    err "No [envs.$env_name] in config file. Available: $available"
fi

branch="$(_lookup env_keys env_vals "$env_name::branch" || true)"
[[ -n "$branch" ]] || branch="$env_name"

casa_root="$(_lookup env_keys env_vals "$env_name::casa_root" || true)"
[[ -n "$casa_root" ]] || err "[envs.$env_name] is missing casa_root"
casa_root="${casa_root%/}"

# ---------------------------------------------------------------------------
# build environment (mirrors envconfig.build_environment)

heuristics_dir_tmpl="$(_lookup env_keys env_vals "$env_name::heuristics_dir" || true)"
if [[ -n "$heuristics_dir_tmpl" ]]; then
    heuristics="${heuristics_dir_tmpl//\{casa_root\}/$casa_root}"
    heuristics="${heuristics//\{branch\}/$branch}"
else
    heuristics_root="$(_lookup paths_keys paths_vals heuristics_root || true)"
    if [[ -n "$heuristics_root" ]]; then
        heuristics="${heuristics_root%/}/$branch"
    else
        # No heuristics_root configured: assume this script is running from
        # inside a pipeline branch checkout's own scripts/ directory, and
        # that checkout itself (one level up) is the heuristics to use.
        heuristics="$(dirname "$SCRIPT_DIR")"
    fi
fi
scipipe_scriptdir="$heuristics/pipeline/recipes"

rootdir_tmpl="$(_lookup paths_keys paths_vals scipipe_rootdir || true)"
[[ -n "$rootdir_tmpl" ]] || err "[paths].scipipe_rootdir is required"
scipipe_rootdir="${rootdir_tmpl//\{user\}/$USER}"
[[ -n "$subdir" ]] && scipipe_rootdir="$scipipe_rootdir/$subdir"

logdir_tmpl="$(_lookup paths_keys paths_vals scipipe_logdir || true)"
[[ -n "$logdir_tmpl" ]] || err "[paths].scipipe_logdir is required"
scipipe_logdir="${logdir_tmpl//\{user\}/$USER}"

mkdir -p "$scipipe_rootdir" "$scipipe_logdir"

java_home="$(_lookup site_keys site_vals java_home || true)"
[[ -n "$java_home" ]] || java_home="/usr/lib/jvm/java-21-openjdk-21.0.6.0.7-1.el8.x86_64"

acsdata="$(_lookup site_keys site_vals acsdata || true)"
[[ -n "$acsdata" ]] || acsdata="/home/pipedrive/acsdata"

pmr_home="$(_lookup site_keys site_vals pmr_home || true)"
[[ -n "$pmr_home" ]] || pmr_home="/home/pipetools/latest/build"

datapacker_home="$(_lookup site_keys site_vals datapacker_home || true)"
[[ -n "$datapacker_home" ]] || datapacker_home="/home/pipedrive/datapacker/current"

flux_url="$(_lookup site_keys site_vals flux_service_url || true)"
[[ -n "$flux_url" ]] || flux_url="https://almascience.org/sc/flux"

flux_url_backup="$(_lookup site_keys site_vals flux_service_url_backup || true)"
[[ -n "$flux_url_backup" ]] || flux_url_backup="https://asa.alma.cl/sc/flux"

telemetry="$(_lookup site_keys site_vals casa_enable_telemetry || true)"
if [[ "$telemetry" == "true" ]]; then casa_telemetry="true"; else casa_telemetry="false"; fi

casa_path="$casa_root/bin"
pmr_bin="$pmr_home/bin"

IFS=':' read -r -a path_parts <<< "${PATH:-}"
new_path_parts=()
for p in "${path_parts[@]}"; do
    [[ "$p" == "$casa_path" || "$p" == "$pmr_bin" ]] && continue
    new_path_parts+=("$p")
done
new_path="$pmr_bin:$casa_path"
for p in "${new_path_parts[@]}"; do
    new_path="$new_path:$p"
done

matplotlibrc="$HOME/.casa/matplotlib"

# ---------------------------------------------------------------------------
# emit

out_keys=(CASA_ROOT CASA_PATH PIPE_BRANCH SCIPIPE_HEURISTICS SCIPIPE_SCRIPTDIR SCIPIPE_ROOTDIR SCIPIPE_LOGDIR JAVA_HOME ACSDATA ACSROOT DATAPACKER_HOME JARSDIR FLUX_SERVICE_URL FLUX_SERVICE_URL_BACKUP CASA_ENABLE_TELEMETRY PATH MATPLOTLIBRC)
out_vals=("$casa_root" "$casa_path" "$branch" "$heuristics" "$scipipe_scriptdir" "$scipipe_rootdir" "$scipipe_logdir" "$java_home" "$acsdata" "$pmr_home" "$datapacker_home" "$datapacker_home/lib" "$flux_url" "$flux_url_backup" "$casa_telemetry" "$new_path" "$matplotlibrc")

for i in "${!out_keys[@]}"; do
    k="${out_keys[$i]}"
    v="${out_vals[$i]}"
    if [[ "$print_env" -eq 1 ]]; then
        printf '%s=%s\n' "$k" "$v"
    else
        printf 'export %s=%q\n' "$k" "$v"
    fi
done

printf 'calibpipe env: env=%s branch=%s casa_root=%s heuristics=%s config=%s\n' \
    "$env_name" "$branch" "$casa_root" "$heuristics" "$config_path" >&2
