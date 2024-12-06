######################### timegaincalQA #########################
Prototype timegaincal QA scores for ALMA Interferometric Pipeline
#################################################################
## H. Francke, J. Hibbard 2024

#### Usage: ####
To run timegaincal_qa.py:

`python3 /path_to_applycalQA/timegaincal_qa.py input_path -o output_path -l label`

If the shebang (first line path reference to environment) inside timegaincal_qa.py gets edited to point to the
python3 installation to be used, the file timegaincal_qa.py is included in the PATH and is executable, then
the command line can be simplified to:

`timegaincal_qa.py input_path -o output_path -l label`

Where: 

- *input_path*: path to folder where .ms files are stored.
- *output_path*: path to folder where results will go. 
- *label*: substring to include in the output files and folders created, for identification purposes

#### Script Output ####

The standard output of the script has the following set of files, written in a subfolder
created on "output_path" folder named after the input_path:

1) A subfolder named "databuffer", which has a file with the following name convention:
   - uid___A002_XNNN_XNNN.ms_spwsetup.v32.pkl
   which contains a python pickle file with a dictionary inside, which contains information
   obtained from each dataset. This is searched for and if found, read by the script in future executions of
   the script to speed up the execution of the script. Relevant mostly for debugging reasons.

2) Subfolder named "timeqaplots_<PLfolder><uid___A002_XNNN_XNNN.ms>_<label>" containing diagnostic files:
   - <uid___A002_XNNN_XNNN.ms>_outliers_<label>.txt : which contains a plain text dump of all outliers found for this EB (mimicking pipeline's "PIPE356_outliers.txt" in applycal stage)
   - <uid___A002_XNNN_XNNN.ms>.delta_amp_vs_antid.spw##.png Plots showing the amplitude metric v/s antenna ID for this EB.
   - <uid___A002_XNNN_XNNN.ms>.delta_amp_vs_time.spw##.png Plots showing the amplitude metric v/s time for this EB.
   - <uid___A002_XNNN_XNNN.ms>.delta_phase_vs_Proj_distance.spw##.png Plots showing the phase metric v/s distance to reference antenna for this EB.

3) A text file named "timegaincal_reportline_<label>.csv", containing a CSV text file with the list of outliers and the value of the maximum outlier for amplitude and phase, in the format used for compiling the validation table.

4) A text file named "timegincal_qascores_<label>.txt", which is a text dump of the list of output QAscores generated using the pipeline's object destined to QA message passing.

##### Description of files in this package #####

Readme.txt:                This file
TableWrapper.py:           Class used to handle amplitude and phase solution gaincal tables from the hifa_timegaincal stage.
ampphase_timegaincal.py:   Main QA scores algorithm, containing the metric calculation and outlier detection.
                           It also contains some function used for summary and reporting, which are meant for debugging and
                           algorithm validation.
pipelineqa.py:             Module used by the pipeline to contain the objects used for QA score message passing.
qa_utils.py:               Module used for miscellaneous utilities having some general statistic calculation routines,
                           MS metadata reading and other geometric projection algorithms.
timegaincal_qa.py:         Script used to test and showcase the main algorithm.
