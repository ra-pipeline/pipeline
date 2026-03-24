#!/opt/pipelinedriver/2025DEC/casa/casa-6.6.6-18-pipeline-2025.1.0.36-py3.10.el8/bin/python3
# -*- coding: utf-8 -*-

import os, sys
import argparse
import glob
import time as systime
import datetime
import numpy as np
import pickle
import sd_qa_utils
import sd_baseline_qa
import sd_qa_reports
from casatools import version_string as cversion
from pipeline.h.cli import h_resume
from pipeline.infrastructure import version as plversion

#def_input_path = "/jaopost_spool/sd-qascores/PIPEREQ-305"
def_input_path = "/mnt/jaosco/data/hfrancke/QAscores/PIPEREQ-305"
def_output_path = ""

def parse_arguments():
    parser = argparse.ArgumentParser(description='Calculate QA scores for ALMA SD PL baseline stage (Pipeline version)')
    parser.add_argument('input', help='Directory to get .ms files from',type=str)
    parser.add_argument('-o','--output', metavar="output",help='Directory to store copy of QA2 score results',
                        required=False, default=def_output_path)
    parser.add_argument('-b','--bufferdata', help='Buffer read MS data T/F', required=False, action='store_true')

    args = parser.parse_args()

    input_folder_name=args.input

    if os.path.exists(args.input):
        print("Input directory: "+args.input)
        input_folder_name=args.input.split("/")[-1]
    elif os.path.exists(def_input_path+"/"+args.input):
        args.input = def_input_path+"/"+args.input
        print("Input directory: "+args.input)
    else:
        print('Could not find input folder '+def_input_path+"/"+args.input+". See -h for help")
        sys.exit()

    if len(args.output) > 0:
        if not os.path.exists(args.output):
            os.system('mkdir '+args.output)

        if not os.path.exists(args.output+'/'+input_folder_name):
            os.system('mkdir '+args.output+'/'+input_folder_name)
                
        args.output = args.output+'/'+input_folder_name
        print("Output copy directory: "+args.output)
    else:
        args.output = ""
        print("No Output copy directory, leaving output in the same input directory...")

    return args

def main():

    #Start time
    tstart = systime.time()
    #Get this CASA+PL versions
    casaversion = cversion().replace('-', '.')
    PLversion = plversion.get_version()

    #Get command line arguments
    args = parse_arguments()
    input_path = args.input
    output_path = args.output

    #Buffer MS data read to disk?
    buffer_data = args.bufferdata

    #Get CASA and PL version used for the input data
    (folder_casaversion, folder_PLversion) = sd_qa_utils.get_versions_from_aquareport(input_path)

    #Change to working folder of pipeline
    init_cwd = os.getcwd()
    plworking_folder = glob.glob(input_path+'/S*/G*/M*/working')
    if len(plworking_folder) == 1:
        plworking_folder = plworking_folder[0]
    else:
        print('Could not find pipeline working folder inside '+input_path+'! Exiting...')
        sys.exit('Could not find pipeline working folder.')
    print('Changing current working folder to: '+plworking_folder)
    os.chdir(plworking_folder)

    #Get science line data detections, if available
    sci_line_data = sd_qa_utils.read_sci_line_data_from_buffer()
    if sci_line_data is None:
        try:
            print('Could not find science line detection in a sci_line_data.pkl buffer file, attempting read from the pipeline context.')
            if (not folder_casaversion == casaversion) or (not folder_PLversion == PLversion):
                print(f'Dataset {input_path} produced using CASA {folder_casaversion}, Pipeline {folder_PLversion},')
                print(f'while current CASA is {casaversion} and Pipeline {PLversion}.')
                print('Run extract_science_lines.sh to buffer context information into sci_line_data.pkl.')
                print('Exiting...')
                sys.exit('Wrong pipeline version for context reading')
            sci_line_data = sd_qa_utils.read_sci_line_data_from_context()
        except ValueError as e:
            print(f"Could not read pipeline context to obtain science line detections. Check pipeline version. Error: {e}")
            print("Exiting...")
            sys.exit("Pipeline context reading error")

    #get list of ms, create relevant lists filtering out non-relevant MSs
    mslist = glob.glob('uid*.ms.atmcor.atmtype?_bl')
    justmslist = [ms.split('/')[-1] for ms in mslist]
    working_folder = mslist[0].replace(justmslist[0], '')

    #Get an identifier for the containing folder of the dataset
    if '/' in input_path:
        plfolder = [item for item in input_path.split('/') if not item == ''][-1]
    else:
        plfolder = input_path

    #Set output path
    if output_path == '':
        output_path = working_folder
    else:
        output_path = plfolder

    plot_output_path = os.path.join(output_path, 'sd_baseline_output')
        
    #Create output paths, if they don't exist yet
    if (not os.path.exists(plot_output_path)):
        os.system('mkdir '+plot_output_path)

    print('Working PL folder:'+working_folder)
    print('Requesting plot output to be in '+plot_output_path)
    #Run sd_applycal main method to get QA scores
    qascore_list = []
    plots_fnames = []
    antnames_for = {}
    for ms in mslist:
        msonly = ms.split('/')[-1]
        (this_qascore_list, this_antnames_for, this_plots_fnames) = \
            sd_baseline_qa.get_ms_baseline_qascores([ms], sci_line_data = sci_line_data,
                                                    plot_output_path = plot_output_path,
                                                    weblog_output_path = plot_output_path,
                                                    buffer_data = True,
                                                    buffer_fname = msonly+'.mswCollection.bl.buffer.pkl')
        qascore_list.extend(this_qascore_list)
        plots_fnames.extend(this_plots_fnames)
        antnames_for.update(this_antnames_for)

    #End time
    tend = systime.time()
    dtime_min = (tend-tstart)/60.0

    #Write reports used for testing
    sd_qa_reports.addFLSLentry_bl(qascore_list, output_file = output_path+'prototype_qa_score.csv', dtime_min = dtime_min)
    sd_qa_reports.makeSummaryTable_bl(qascore_list, antnames_for, plots_fnames, plfolder, working_folder = working_folder, output_file = plot_output_path + '/qascore_summary.csv', writemode = 'w', weblog_adress = 'http://jaopost-web.sco.alma.cl/dataproc/hfrancke/hfranckebase/QAscores/PIPEREQ-305/'+plworking_folder)

    os.chdir(init_cwd)
 
    return

if __name__ == '__main__':
    main()

