'''
Prototype script for SD hsd_baseline QA score (PIPEREQ-305)
-----------------------------------------------------------

run_sd_baseline_qa.py: Main script used to test main QA score algorithm in sd_baseline_qa.py.
                       Reads in a pipeline execution folder, searches for all calibrated MSs,
                       runs the heuristics and produces reports used for heuristic testing.
sd_baseline_qa.py:     Main module containing the hsd_baseline QA heuristics.
sd_qa_reports.py:      Auxiliary module containing the reporting and plotting routines used.
sd_qa_utils.py:        Auxiliary module containing general utilities used to access data and
                       perform some general statistical calculations.
mswrapper_sd.py:       Module containing the MSWrapperSD class, a data container for accessing
		       the necessary ON-source data and CalAtmosphere tables.

extract_science_lines.sh: Bash script used to extract the science line information in the case
                          of a pipeline folder and context created with an older version of the
			  pipeline.

Usage:

run_sd_baseline_qa.py [-o /output_path] [-b True/False] 2021.1.00490.S_2024_04_03T17_03_51.553

If the optional output path is not given, the output is put into the working folder of the pipeline
execution. in this case, e.g.

2021.1.00490.S_2024_04_03T17_03_51.553/SOUS_uid___A001_X1590_X222a/GOUS_uid___A001_X1590_X222b/MOUS_uid___A001_X1590_X222e/working/sd_baseline_output

where the main reports and plots will be saved. Additionally, a very short output will be put in the
base of the working folder for testing and QA0++ uses.
(2021.1.00490.S_2024_04_03T17_03_51.553/SOUS_uid___A001_X1590_X222a/GOUS_uid___A001_X1590_X222b/MOUS_uid___A001_X1590_X222e/working/prototype_qa_score.csv)
'''
from . import mswrapper_sd, sd_baseline_qa, sd_qa_utils, sd_qa_reports
