#!/usr/bin/env python3
"""Submit a batch of calibPipeIF.py runs to slurm, one per line of a pipefile.

Each non-comment line of the pipefile is "<mous_uid> [recipe]" (recipe
defaults to calimage). Replaces runbatch.sh: no more hardcoded path to
calibPipeIF.py, and --env is a required (or config-default) argument
instead of three dead stacked shell-variable assignments.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import envconfig

CALIBPIPEIF = Path(__file__).resolve().parent / "calibPipeIF.py"


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pipefile", help="file with one '<mous_uid> [recipe]' per line")
    p.add_argument("--config", help="path to TOML config (see calibPipeIF.py --help)")
    p.add_argument("--env", help="[envs.<name>] to use; default: config's default_env")
    p.add_argument("-c", "--cores", type=int, default=8, dest="cores", help="cores per job (default: 8)")
    p.add_argument("-m", "--mem", type=int, default=248, dest="mem", help="GB per job (default: 248)")
    p.add_argument("-M", "--mail-type", default="ALL", dest="mail_type", help="slurm --mail-type (default: ALL)")
    p.add_argument("-n", "--node", default="1", dest="node", help="slurm -N (default: 1)")
    p.add_argument("-o", "--outfile", dest="outfile", help="slurm stdout file (default: batch.<job>.out)")
    p.add_argument("-e", "--errfile", dest="errfile", help="slurm stderr file (default: batch.<job>.err)")
    queue = p.add_mutually_exclusive_group()
    queue.add_argument("-p", dest="queue", action="store_const", const="plwg", default="plwg",
                        help="submit to the plwg queue (default)")
    queue.add_argument("-b", dest="queue", action="store_const", const="batch2",
                        help="submit to the batch2 queue")
    p.add_argument("--extra-arg", action="append", default=[], dest="extra_args",
                    help="extra flag passed through to calibPipeIF.py, repeatable")
    return p


def parse_args():
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    return parser.parse_args()


def check_submit_host(config):
    submit_host = config.get("site", {}).get("submit_host")
    if not submit_host:
        return
    hostname = subprocess.getoutput("hostname")
    if hostname != submit_host:
        print(f"Jobs must be submitted from {submit_host}, exiting.")
        sys.exit(1)


def build_sbatch_script(pipejob):
    return f"""#!/bin/sh
ulimit -Sn 8192
umask 002
{pipejob}
"""


def job_name(pipejob):
    mous = ""
    for tok in pipejob.split():
        if "mous" in tok:
            mous = tok.split("=", 1)[-1]
            mous = mous.replace("uid___A00", "").strip("/").replace("/", "_")
            break
    date = time.strftime("%Y-%m-%d")
    return f"{mous}_{date}"


def main():
    args = parse_args()

    try:
        config_path = envconfig.find_config_path(args.config)
        config = envconfig.load_config(config_path)
    except envconfig.ConfigError as e:
        print("ERROR: " + str(e))
        sys.exit(1)

    check_submit_host(config)

    pipefile = Path(args.pipefile)
    if not pipefile.is_file():
        print(f"{pipefile} does not exist, exiting")
        sys.exit(1)

    mem = f"{args.mem}G"

    with open(pipefile) as fd:
        lines = fd.readlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        mousname = parts[0]
        recipe = parts[1] if len(parts) > 1 else "calimage"

        pipejob_parts = [
            str(CALIBPIPEIF),
            "--staticobscal",
            f"--mous={mousname}",
            f"--recipe={recipe}",
        ]
        if args.config:
            pipejob_parts.append(f"--config={args.config}")
        if args.env:
            pipejob_parts.append(f"--env={args.env}")
        pipejob_parts.extend(args.extra_args)
        pipejob = " ".join(pipejob_parts)

        name = job_name(pipejob)
        print(f"job name = {name}")
        outfile = args.outfile or f"batch.{name}.out"
        errfile = args.errfile or f"batch.{name}.err"

        with tempfile.NamedTemporaryFile(
            mode="w", prefix=f"{os.environ.get('USER','')}_sbatch.", delete=False
        ) as sbatch_fd:
            sbatch_fd.write(build_sbatch_script(pipejob))
            sbatch_path = sbatch_fd.name

        try:
            cmd = [
                "sbatch",
                "-p", args.queue,
                "-N", args.node,
                "-n", str(args.cores),
                "--export=ALL",
                f"--job-name={name}",
                f"--mail-user={os.environ.get('USER','')}",
                f"--mail-type={args.mail_type}",
                f"--mem={mem}",
                "-o", outfile,
                "-e", errfile,
                sbatch_path,
            ]
            print("    " + " ".join(cmd))
            subprocess.run(cmd, check=True)
        finally:
            os.unlink(sbatch_path)

        print("Waiting 5 seconds to minimize directory naming collision risk")
        time.sleep(5)


if __name__ == "__main__":
    main()
