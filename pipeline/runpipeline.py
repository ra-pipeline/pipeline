"""ALMA Pipeline Runner.

This script serves as an entry point for the VLA pipeline processing.
It parses command line arguments and executes the pipeline processing request (PPR).

Usage:
    casa --nogui --nologger -c runpipeline.py <pipeline_processing_request>

Note:
    The argument index calculation accounts for CASA's parameter handling,
    where the script name follows the '-c' flag.
"""
# Import casashell to access command line arguments passed to CASA
import casashell

# Import the module responsible for executing the pipeline processing request
import pipeline.infrastructure.executeppr as eppr

# Only execute the PPR when the script is run directly (not when imported as a module)
if __name__ == '__main__':
    ppr_file = casashell.argv[casashell.argv.index('-c') + 2]

    # Execute the pipeline processing request
    eppr.executeppr(ppr_file, importonly=False)
