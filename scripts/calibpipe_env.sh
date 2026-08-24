# calibpipe_env.sh -- source this to set the CASA + ALMA-pipeline
# environment (from your personal config.toml) directly in your *current*
# shell, so subsequent pipelineMakeRequest/casa calls pick up the right
# build and branch:
#
#   source calibpipe_env.sh --env=main
#   pipelineMakeRequest ...
#   casa ...
#
# Works from bash or zsh. Must be sourced (`source ...` / `. ...`), not
# executed -- run directly it can't modify your shell's environment and
# will just print a reminder.
#
# All options are forwarded to calibpipe_env_resolve.sh next to this file
# (see its --help): --config=<path>, --env=<name>, --subdir=<name>.
#
# This file is intentionally shell-portable POSIX (no arrays indexed by
# number, no [[ ]], no bash-only builtins): it's parsed directly by
# whichever shell you source it from, so it just locates
# calibpipe_env_resolve.sh and always hands the real TOML-parsing/
# environment-building work to that script via an explicit `bash`
# subprocess -- regardless of what shell you're sourcing from -- then
# `eval`s its `export ...` output into your shell. See
# calibpipe_env_resolve.sh's own header for why that split exists.

__calibpipe_sourced=0
if [ -n "${BASH_SOURCE:-}" ]; then
    __calibpipe_self="${BASH_SOURCE}"
    # bash leaves $0 as the invoking shell/script when sourced, and sets it
    # to this file's own path when executed directly -- the standard bash
    # sourced-vs-executed check.
    [ "${BASH_SOURCE}" != "${0}" ] && __calibpipe_sourced=1
elif [ -n "${ZSH_VERSION:-}" ]; then
    # zsh, unlike bash, rewrites $0 to the sourced file's path while it
    # runs -- so $0 can't distinguish sourced from executed here. Use
    # ZSH_EVAL_CONTEXT instead, which ends in ":file" only while a `source`d
    # file is executing.
    __calibpipe_self="$(eval 'print -r -- ${(%):-%x}')"
    case "${ZSH_EVAL_CONTEXT:-}" in
        *:file) __calibpipe_sourced=1 ;;
    esac
else
    __calibpipe_self=""
fi

if [ -z "$__calibpipe_self" ]; then
    echo "calibpipe_env.sh: source this from bash or zsh (e.g. 'source calibpipe_env.sh --env=main')" >&2
    unset __calibpipe_self __calibpipe_sourced
    return 1 2>/dev/null || exit 1
fi

if [ "$__calibpipe_sourced" -eq 0 ]; then
    echo "calibpipe_env.sh: this must be sourced, not executed -- run:" >&2
    echo "    source $__calibpipe_self $*" >&2
    unset __calibpipe_self __calibpipe_sourced
    exit 1
fi

__calibpipe_dir=$(cd "$(dirname "$__calibpipe_self")" >/dev/null 2>&1 && pwd)
__calibpipe_resolver="$__calibpipe_dir/calibpipe_env_resolve.sh"

if [ ! -f "$__calibpipe_resolver" ]; then
    echo "calibpipe_env.sh: can't find calibpipe_env_resolve.sh next to this script in $__calibpipe_dir" >&2
    unset __calibpipe_self __calibpipe_sourced __calibpipe_dir __calibpipe_resolver
    return 1 2>/dev/null || exit 1
fi

for __calibpipe_arg in "$@"; do
    case "$__calibpipe_arg" in
        -h|--help)
            bash "$__calibpipe_resolver" --help
            unset __calibpipe_self __calibpipe_sourced __calibpipe_dir __calibpipe_resolver __calibpipe_arg
            return 0 2>/dev/null || exit 0
            ;;
    esac
done

__calibpipe_out=$(bash "$__calibpipe_resolver" "$@")
__calibpipe_status=$?
if [ "$__calibpipe_status" -ne 0 ]; then
    unset __calibpipe_self __calibpipe_sourced __calibpipe_dir __calibpipe_resolver __calibpipe_arg __calibpipe_out __calibpipe_status
    return 1 2>/dev/null || exit 1
fi

eval "$__calibpipe_out"
unset __calibpipe_self __calibpipe_sourced __calibpipe_dir __calibpipe_resolver __calibpipe_arg __calibpipe_out __calibpipe_status
