#!/Applications/CASA.app/Contents/MacOS/python3
# -*- coding: utf-8 -*-

import os, sys
import glob
import numpy as np

def_input_path = "/Users/haroldfrancke/QAscoresResults_PLBM"
def_output_path = "/Users/haroldfrancke/QAscoresResults_PLBM"
label = 'v58'

#plfolderfile = open(def_input_path+'/JAO_MOUS_list.txt', 'r')
#plfolders = [line.replace('\n','') for line in plfolderfile]
plfolders = glob.glob(def_output_path+'/????.?.?????.?_????_??_??T??_??_??.???')
plfolders = sorted(plfolders)

outputreport = open(def_output_path + '/timegaincal_report_'+label+'.csv', 'w')

for plfolder in plfolders:
    #get list of ms for this PL folder
    #mslist = glob.glob(def_input_path+'/'+plfolder+'/S*/G*/M*/working/*.ms')
    #excludedstr = ['_targets.ms','_target.ms','_line.ms','_cont.ms']
    #mslist = [ms for ms in mslist if all([not item in ms for item in excludedstr])]
    mslist = glob.glob(plfolder+'/databuffer/*.ms_spwsetup*')
    mslist = [ms.split('_spwsetup')[0] for ms in mslist]
    justplfolder = plfolder.split('/')[-1]
    justmslist = [ms.split('/')[-1] for ms in mslist]

    #Open report files
    rep4ms = {}
    repfile = def_output_path+'/' + justplfolder + '/timegaincal_reportline_'+label+'.csv'
    if os.path.exists(repfile):
        repfd = open(repfile, 'r')
        for line in repfd:
            thisms = line.split(',')[1]
            rep4ms[thisms] = line
        repfd.close()
    
    for ms in justmslist:
        if ms in rep4ms.keys():
            outputreport.write(rep4ms[ms])
        else:
            outputreport.write(justplfolder+','+ms+',Failure!,,,,,,,\n')

outputreport.close()

