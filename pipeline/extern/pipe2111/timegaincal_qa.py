#!/Applications/CASA.app/Contents/MacOS/python3
# -*- coding: utf-8 -*-

#shebang cluster
#/opt/pipelinedriver/2023AUG/casa/casa-6.5.4-9-pipeline-2023.1.0.124/bin/python3

import os, sys
import argparse
import glob
import time as systime
import numpy as np
import argparse
import pickle
import qa_utils as qau
import ampphase_timegaincal
import TableWrapper

def_input_path = "/Users/haroldfrancke/QAscoresMOUSs"
#def_input_path = "/jaopost_spool/QAscoresMOUSs"
def_output_path = "/Users/haroldfrancke/QAscoresResults_v32"
#def_output_path = "/jaopost_spool/QAscoresResults_v32"

applycalQAversion = '32'

def parse_arguments():
    parser = argparse.ArgumentParser(description='Calculate QA2 scores for ALMA timegaincal stage')
    parser.add_argument('input', help='Directory to get .ms and timegaincal files from',type=str)
    parser.add_argument('-o','--output', metavar="output",help='Directory to store QA2 scores', required=False,
                        default=def_output_path)
    parser.add_argument('-l','--label', metavar="label",help='Label for qa scors script run', required=False,
                        default='')

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

    if not os.path.exists(args.output):
        os.system('mkdir '+args.output)

    if not os.path.exists(args.output+'/'+input_folder_name):
        os.system('mkdir '+args.output+'/'+input_folder_name)
    
    if not os.path.exists(args.output+'/'+input_folder_name+'/databuffer'):
        os.system('mkdir '+args.output+'/'+input_folder_name+'/databuffer')
        
    args.output = args.output+'/'+input_folder_name
    print("Output directory: "+args.output)

    return args

def QAScores2Txt(qascores, output_path, label):
    f = open(output_path+'/timegaincal_qascores_'+label+'.txt', 'w')
    for qascore in qascores:
        f.write(str(repr(qascore))+'\n')
    f.close()
    return

def main():
    #Get command line arguments
    args = parse_arguments()
    input_path = args.input
    output_path = args.output
    label = args.label

    #get list of ms, create relevant lists filtering out non-relevant MSs
    mslist = glob.glob(input_path+'/S*/G*/M*/working/*.ms')
    excludedstr = ['_targets.ms','_target.ms','_line.ms','_cont.ms']
    mslist = [ms for ms in mslist if all([not item in ms for item in excludedstr])]
    justmslist = [ms.split('/')[-1] for ms in mslist]
    maxvaldict = {}
    fullplfolder = mslist[0].replace(justmslist[0], '')
    
    #Get an identifier for the containing folder of the dataset
    if '/' in input_path:
        plfolder = [item for item in input_path.split('/') if not item == ''][-1]
    else:
        plfolder = input_path

    #Create output paths, if they don't exist yet
    if not os.path.exists(output_path):
        os.system('mkdir '+output_path)

    #List of all QAScores obtained
    allqascores = []
    
    #Run timegaincal_qa in each MS
    for idx, ms in enumerate(mslist):
        ms_qascores = ampphase_timegaincal.get_timegaincal_qascores(ms, output_path = output_path, label=label, applycalQAversion = applycalQAversion)
        allqascores.extend(ms_qascores)

    #Put QAscores into text form for diagnostic purposes
    QAScores2Txt(allqascores, output_path, label)
    
    return

if __name__ == '__main__':
    main()

