#!/home/casa/packages/RHEL8/release/current/bin/python3
# -*- coding: utf-8 -*-

# sadly, I can't find a remotely modern version of python on the cluster,
# so I have to use my own.
# #!/usr/bin/env python3


def usage():
    print("\nUsage: calibPipeIF.py [options]")
    print("\nDescription: This script assists in the execution of the interferometric pipeline.")
    print("\nOptions:")
    print("\t--mous=<mous_uid>       MOUS status uid to execute the pipeline.")
    print("\t--flag=<path>           Path to dir with uid*flag*template.txt, uid*ms.wvr*, PPR, flux.csv, antennapos.csv and/or raw asdms to be re-used.")
    print("\t--PPR=<path>            Path to a PPR xml file to re-use (requires --flag). Overrides any PPR found in the --flag directory.")
    print("\t--valid                Use 6.1.0-63 validation as the --flag dir")
    print("\t--config=<path>         Path to TOML config file (personal, lives next to the checkout).")
    print("\t                        Default: $CALIBPIPE_CONFIG, else config.toml next to this checkout.")
    print("\t--env=<name>            Name of the [envs.<name>] table to use from the config file.")
    print("\t                        Default: the config file's default_env.")
    print("\t--subdir=<name>         Extra subdirectory appended to SCIPIPE_ROOTDIR.")
    print("\t--print-env             Resolve config/env, print the resulting environment, and exit.")
    print("\t--recipe=[cal|image|image_selfcal|calimage|calimage_selfcal|calsurvey]")
    print("\t                        image looks for calibrated data in --flag directory")
    print("\t--ebwfile=<file>        file with effective bandwidth information")
    print("\t--ncores=<number>       number of cores")
    print("\t--loglevel=[critical|error|warning|info|debug|todo|trace]  PL log level; default=debug")
    print("\t--pickle                run picklePipeRun")
    print("\t--useresume             usually, there will be two hifa_importdata, 2 contexts.  this makes it use break/resume instead, and there will be 1 context")
    print("\t--legacy                run fixsyscaltimes, fixplanets")
    print("\t--aUdir=<path>          set aU dir to <path>")
    print("\t--usegetalmaflux        use aU.getALMAFluxCsv. if this not set, it will run only as a backup")
    print("\t--noupdate              don't update casa IERS")
    print("\t--verbose               write all subprocess output to the calibPipeIF log file (default: quiet)")
    print("\t--onlysemipass=<EB_uid> process only the specified EBs (comma-delimited 'uid://A002/Xabc/Xdef' list) by running asdmExport (if --flag is not specified) and modifying the ASDM entries in the PPR after pipelineMakeRequest")
    print("\t--semipass=<EB_uid>     also process the specified EBs (comma-delimited 'uid://A002/Xabc/Xdef' list) by running asdmExport (if --flag is not specified) and modifying the ASDM entries in the PPR after pipelineMakeRequest")
    print("\t--staticobscal          use previous flux.csv, antennapos.csv, flagtemplate.txt from [paths].obscaldir")
    print("\t--oldcont               use previous cont.dat from [paths].obscaldir")
    print("\t-h, --help              Show this help.")


# utility functions and class:
import os, fnmatch
from datetime import datetime
from subprocess import Popen, PIPE, STDOUT
import subprocess
import sys
from sys import argv, stdout, exit
from os import system, chdir, getcwd
import os
from subprocess import getoutput
from getopt import getopt, GetoptError
from pprint import pprint
from xml.dom.minidom import parse
from glob import glob
import pdb
from copy import copy
import shutil

import envconfig


def find(pattern, path):
    result = []
    for root, dirs, files in os.walk(path,followlinks=True): # RI links needed for symlinked ASDMs
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                result.append(os.path.join(root, name))
    return result

def finddir(pattern, path):
    result = []
    for root, dirs, files in os.walk(path,followlinks=True): # RI links needed for symlinked ASDMs
        for name in dirs:
            if fnmatch.fnmatch(name, pattern):
                result.append(os.path.join(root, name))
    return result

class log:
    def __init__(self, filename, print_flag = False):
        now = datetime.now().isoformat().replace(":", "-")
        self.filename = filename
        self.print_flag = print_flag
        self.fd = open(filename + "." + now + ".log", "w")

    def log(self, str):
        now = datetime.now().isoformat()
        str = str.split("\n")

        for s in str:
            self.fd.write(now + ": " + s + "\n")
            if self.print_flag:
                print(now + ": " + s)
            self.fd.flush()

    def run(self, command):
        """This procedure runs a command in background and logs the output line by line in real-time
        command: String containing the command to run."""

        self.log("running '"+command+"':\n\n")
        proc = Popen(command, shell=True, bufsize=2, stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        for l in proc.stdout:
            self.log(l) # DARED
        proc.poll()
        retcode=proc.returncode
        proc.terminate()
        #proc.kill()
        return(retcode)


    def runquiet(self, command):

        self.log("running '"+command+"' quietly.")
        retcode=subprocess.call(command, shell=True)
        if retcode>0:
            self.log("nonzero exit code = "+str(retcode))
        return(retcode)

    def close(self):
        self.fd.close()


#=============================================================================
def main():

    # Arguments and options parsing.
    if len(argv) == 1:
        usage()
        exit()
    try:
        opts, args = getopt(argv[1:], "mfhv", ["mous=", "flag=", "PPR=", "valid", "config=", "env=", "help", "recipe=", "pickle", "legacy", "ebwfile=", "ncores=", "loglevel=","aUdir=","useresume","usegetalmaflux","staticobscal","oldcont","noupdate","verbose","semipass=","onlysemipass=","subdir=","print-env"])
    except GetoptError as err:
        print(err)
        usage()
        exit(2)

    # Default variables
    mous_uid = argv[1]
    flag_and_go = False
    flag_and_go_dir = ""
    ppr_override = ""
    hostname = getoutput("hostname").replace("\n", "")
    username = getoutput("whoami").replace("\n", "")
    ncores=8
    loglevel="debug" # PL logging level, default=debug
    recipe="calimage"
    dopickle=False
    useresume=False
    usegetalmaflux=False
    legacy=False
    staticobscal=False # use flux.csv and antennapos.csv from obscaldir
    oldcont=False # use cont.dat from obscaldir
    noupdate=True
    verbose=False # if True, log all subprocess output line-by-line; default is quiet

    config_arg=None
    env_name=None
    subdir=None
    print_env=False
    semipass=""
    onlysemipass=""

    ebwfile="/lustre/naasc/sciops/comm/cbrogan/Pipeline_Imaging_Tests/ebwfile.txt"

    use_validation_start=False # rerun with flux.csv, flagtemplate, from previous validation run.

    # Arguments and options detection.
    for o, a in opts:
        if o in ("--mous="):
            mous_uid = a

        if o in ("--flag"):
            flag_and_go = True
            flag_and_go_dir = a
            if flag_and_go_dir[0] != "/":
                flag_and_go_dir = getcwd() + "/" + flag_and_go_dir
            if flag_and_go_dir[-1] != "/":
                flag_and_go_dir += "/"
            if not os.path.exists(flag_and_go_dir):
                print("Cannot find the --flag directory "+flag_and_go_dir+".  Does it exist?")
                exit(0)

        if o in ("--PPR"):
            ppr_override = a
            if ppr_override[0] != "/":
                ppr_override = getcwd() + "/" + ppr_override
            if not os.path.exists(ppr_override):
                print("Cannot find the --PPR file "+ppr_override+".  Does it exist?")
                exit(0)

        if o in ("--valid"):
            use_validation_start=True

        if o in ("--config="):
            config_arg = a

        if o in ("--env="):
            env_name = a

        if o in ("--subdir="):
            subdir = a

        if o in ("--print-env"):
            print_env = True

        if o in ("--recipe="):
            recipe = a

        if o in ("--ebwfile="):
            ebwfile = a

        if o in ("--semipass="):
            semipass = a

        if o in ("--onlysemipass="):
            onlysemipass = a
            # when this is specified, we tell pipelineMakeRequest not to
            # bother downloading the semipass EBs

        if o in ("--ncores="):
            ncores = int(a)

        if o in ("--loglevel="):
            loglevel = a

        if o in ("--pickle"):
            dopickle=True

        if o in ("--legacy"):
            legacy=True

        if o in ("--useresume"):
            useresume=True

        if o in ("--usegetalmaflux"):
            usegetalmaflux = True

        if o in ("--staticobscal"):
            staticobscal = True

        if o in ("--oldcont"):
            oldcont = True

        if o in ("--noupdate"):
            noupdate=True

        if o in ("--verbose"):
            verbose=True

        if o in ("-h", "--help"):
            usage()
            exit(0)

    # --aUdir= override: recover it from opts explicitly, since the loop
    # above only sets aUdir_override on the specific iteration it's seen.
    aUdir_override = None
    for o, a in opts:
        if o in ("--aUdir="):
            aUdir_override = a

    #-----------------------------------------------------------------------------
    # resolve config / environment (replaces sourcing pipeline_env_*.sh)
    try:
        config_path = envconfig.find_config_path(config_arg)
        config = envconfig.load_config(config_path)
        env_spec = envconfig.resolve_env(config, env_name)
        env = envconfig.build_environment(config, env_spec)
    except envconfig.ConfigError as e:
        print("ERROR: "+str(e))
        exit(1)

    if subdir:
        env["SCIPIPE_ROOTDIR"] = env["SCIPIPE_ROOTDIR"] + "/" + subdir
        os.makedirs(env["SCIPIPE_ROOTDIR"], exist_ok=True)

    os.environ.update(env)

    if print_env:
        for k in sorted(env):
            print(f"{k}={env[k]}")
        exit(0)

    paths = config.get("paths", {})
    aUdir = aUdir_override or paths.get("aUdir", "/home/casa/contrib/AIV/science/analysis_scripts/")
    obscaldir = paths.get("obscaldir", "/lustre/naasc/sciops/comm/rindebet/pipeline/obscal2021")
    validation_dir = paths.get("validation_dir", "/lustre/naasc/projects/pipeline_validation_c8/CASA6.1.63")
    pickle_dir = paths.get("pickle_dir", "/lustre/naasc/sciops/comm/{user}/pipeline/pickles").format(user=os.environ.get("USER", ""))

    if len(semipass) > 0 or len(onlysemipass) > 0:
        # needed for asdmExport/modifyPPR; requires running calibPipeIF.py
        # under a python that has casatools available (e.g. CASA's own),
        # unlike the rest of this script.
        if aUdir not in sys.path:
            sys.path.append(aUdir)
        import analysisUtils as au
        import analyzemscal as amc

    if use_validation_start:
        flag_and_go=False # don't try to do both of these at the same time!

    if recipe=="cal":
        print("Will be doing only calibration")
        procedure_short="hifa_cal"
    elif recipe in ["calimage","calimage_selfcal","calimage_selfcal_nocube"]:
        print("Will be doing calibration and imaging in one PPR")
        procedure_short="hifa_"+recipe
    elif recipe in ["image","image_selfcal","image_selfcal_nocube"]:
        print("Will be doing imaging of previous cal data")
        procedure_short="hifa_"+recipe
    elif recipe=="hsd_calimage":
        procedure_short=recipe
    else:
        procedure_short="hifa_"+recipe

    # pipeversion=getoutput("cd $SCIPIPE_HEURISTICS; svnversion")
    pipeversion='need to implement git command'
    heuristics=os.environ["SCIPIPE_HEURISTICS"].rstrip("/")
    branch=heuristics.split("/")[-1]
    casaroot=os.environ["CASA_ROOT"].rstrip("/")

    # in casa6, --norc will ignore user's config.py but still runs startup.py
    # --norc with --rcdir will ignore config.py in rcdir as well as users'
    # --rcdir=<path> will use startup.py in that dir instead of the users',
    # and config.py unless -norc is set

    #casarun=casaroot+"/bin/casa --nocrashreport --notelemetry --nogui --norc"
    casarun=casaroot+"/bin/casa --nocrashreport --notelemetry --nogui"

    if heuristics.count(casaroot):
        # PL packaged inside of casa:
        casarun=casarun+" --pipeline"
    else:
        # external heuristics
        casarun=casarun+" --agg"

    casarun_serial=copy(casarun)

    if ncores>1:
        casarun=(casaroot+"/bin/mpicasa -n %i "%ncores)+" "+casarun

    print("will use: ",casarun)

    procedure="procedure_"+procedure_short+".xml"


#-----------------------------------------------------------------------------
# find old PPR files
    oldpprfile=""
    if len(ppr_override)>0:
        oldpprfile = ppr_override
        print("Using PPR from --PPR: "+oldpprfile)

    if flag_and_go:
        print("searching wvr offsets in %s..." % (flag_and_go_dir))
        oldwvroffsets = finddir('uid*ms.wvr*', flag_and_go_dir)
        if len(oldwvroffsets)>0:
            print("Found ", oldwvroffsets)
        if len(oldpprfile)==0:
            print("searching flag dir for PPR...")
            oldpprfiles = find('PPR*xml', flag_and_go_dir)
            # start with shortest, in case eg PR_uid___A001_X1465_Xb49_mod.xml
            # lengths=[len(os.path.basename(x)) for x in oldpprfiles]
            # prefer the one from "working" dir, but not from the weblog:
            # inworking=[("working" in x and "html" not in x) for x in oldpprfiles]

            someinworking=False
            for oldpprfile0 in oldpprfiles:
                if "working" in oldpprfile0 and "html" not in oldpprfile0:
                    someinworking=True
            for oldpprfile0 in oldpprfiles:
                if someinworking==False or ("working" in oldpprfile0 and "html" not in oldpprfile0):
                    if len(os.path.basename(oldpprfile0))>len(os.path.basename(oldpprfile)):
                        oldpprfile=oldpprfile0

        if len(oldpprfile)>0:
            print("old PPR file = "+oldpprfile)
            cmd = "grep OUSStatusRef " + oldpprfile
            cmdoutput = getoutput(cmd)
            mous_uid = cmdoutput.split('"')[1]
        else:
            print("INFO: no PPR in flag dir")

        # find mous in path name
        if "MOUS" in flag_and_go_dir:
            mous_uid=flag_and_go_dir.split("MOUS_")[1].split("/")[0]

        if mous_uid[0:3]!="uid":
            print("ERROR: mous_uid [%s] invalid - need to specify with --mous argument or with old PPR"%mous_uid)
            exit(0)

        if len(oldpprfile)>0:
            # CHECK if SAME RECIPE
            cmd = "grep ProcedureTitle " + oldpprfile
            cmdoutput = getoutput(cmd)
            oldprocedure=cmdoutput.split(">")[1].split("<")[0]
            if oldprocedure!=procedure_short:
                print("PPR found in flag directory doesn't have the same recipe as your requested "+procedure_short+" so I'm not using it.  Hope you know what you're doing.")
                oldpprfile=""




    mous_uid=mous_uid.replace('___','://').replace('_','/')
    mous_underscores=mous_uid.replace('://','___').replace('/','_')




#-----------------------------------------------------------------------------
# info
    print("Requested: ")
    print("MOUS "+mous_uid)
    print("PL   "+branch+" version "+pipeversion)
    print("CASA "+casaroot)
    if flag_and_go:
        if len(oldpprfile)>0:
            print("rerunning from "+oldpprfile)
        else:
            print("rerunning with new PPR and "+procedure)
            print("but with files in "+flag_and_go_dir)
    else:
        print("running from scratch")
    if use_validation_start:
        print("running with new PPR but flux.csv and flagtemplate from previous validation run if I can find it")
    if staticobscal:
        print("running with flux.csv, antennapos.csv, flagtemplate.txt if I find it in "+obscaldir)
    if oldcont:
        print("running with cont.dat if I find it in "+obscaldir)

    if flag_and_go:
        # Old asdms?
        oldasdmxmls = find('ASDM.xml', flag_and_go_dir)
        oldasdms=[]
        for oa in oldasdmxmls:
            oldasdms.append("/".join(oa.split("/")[:-1]))
        if len(oldasdms)>0:
            # ASSUME IF IT HAS SOME OLD ASDMS IT HAS THEM ALL
            print("oldasdms=",oldasdms)

        if recipe in ["image","image_selfcal"]:
            oldcalfound=True
            types=['calapply.txt','flagversions.tgz','caltables.tgz','pipeline_manifest.xml','auxproducts.tgz']
            for caltype in types:
                calfiles = find('uid*.'+caltype, flag_and_go_dir)
                if len(calfiles)>0:
                    print("using old cal files of type "+caltype)
                else:
                    oldcalfound=False

    else:
        oldasdms=[]
        oldcalfound=False

    print("")
    print("-------------------------------------")




#-----------------------------------------------------------------------------
# makerequest
    print("-------------------------------------")
    print(" running pipelineMakeRequest ")
    if len(onlysemipass) > 0:
        asdmsArg = "--asdms ["+onlysemipass+"] "
        semipass = onlysemipass
    else:
        asdmsArg = ""
    if procedure.count("hsd")>0:
        cmd = "pipelineMakeRequest " + asdmsArg + mous_uid + " intents_hsd.xml "+procedure
    else:
        cmd = "pipelineMakeRequest " + asdmsArg + mous_uid + " intents_hifa.xml "+procedure
    if len(oldasdms)>0:
        cmd=cmd+" false"
    else:
        cmd=cmd+" true"
    if recipe in ["image","image_selfcal"] and not oldcalfound:
        cmd=cmd+" true" # try to DL cal products
    else:
        cmd=cmd+" false"

    print(cmd)
    cmdoutput = getoutput(cmd)
    print(cmdoutput)
    for i in cmdoutput.split("\n"):
        if "Project root directory is" in i:
            ppmr_rel_dir = i.split()[-1]
            piperootdir=os.environ["SCIPIPE_ROOTDIR"]
            ppmr_dir=piperootdir +"/" + ppmr_rel_dir
        if "missing" in i: # capture archive errors
            if not ("no files missing" in i):
                print("makerequest failed with this line:")
                print(i)
                print(ppmr_dir)
                exit()

#-----------------------------------------------------------------------------
# start logging and store relations between old and new run
    for i in range(5): print;
    print("starting calibPipeIF log")

    # Now I have a directory, I can create the log file
    mylog = log(ppmr_dir + "/calibPipeIF." + ppmr_rel_dir + "." + mous_uid.replace("/", "_").replace(":", "_"), print_flag = True)
    l = mylog.log # l points to method "log"w
    l("  just finished running pipelineMakeRequest with this output (skip to 'AFTER PMR' to see next steps):")
    l(cmdoutput)

    if len(semipass) > 0:
        for semipassEB in semipass.split(','):
            print("Appending semipassEB = ", semipassEB)
            oldasdms.append(semipassEB)
            if not flag_and_go:
                # then they might not exist yet, but check the rawdata directory before getting them
                cmd = "ls -d1 " + ppmr_dir + "/SOUS_uid___*/GOUS_uid___*/MOUS_uid___*/rawdata/"
                dir_rawdata = getoutput(cmd)
                if not os.path.exists(os.path.join(dir_rawdata,semipassEB)):
                    print("Running asdmExport of %s into %s" % (semipassEB,dir_rawdata))
                    au.asdmExport(semipassEB, outpath=dir_rawdata)

    for i in range(5): l("")
    l("== AFTER PMR ====================================================================")
    l("Running the pipeline for MOUS " + mous_uid + " as " + username + "@" + hostname)
    l("Pipeline execution absolute directory is " + ppmr_dir)
    l("Pipeline execution relative directory is " + ppmr_rel_dir)

    l("Recipe = "+procedure_short)
    if len(oldpprfile)>0:
        l("Re-using "+oldpprfile+" from "+flag_and_go_dir)
    if len(oldasdms)>0 and flag_and_go:
        l("Re-using raw ASDMs from "+flag_and_go_dir)

    obsproject_code = ppmr_rel_dir[:14]
    l("Project code is " + obsproject_code)

    yr=obsproject_code.split(".")[0]
    if yr.isdigit():
        if int(yr)<2015 and procedure.count("hsd")<=0:
            if not legacy:
                print(" Switching on legacy fixes for this older data...")
                legacy=True

    l("git information for the requested pipeline:")
    cmd = "pushd $SCIPIPE_HEURISTICS ; git log | head -4 ; popd"
    mylog.run(cmd)



    # put summary information in runsummary.txt
    summarylog = open(ppmr_dir + "/runsummary.txt",'w')
    summarylog.write('uname:\n')
    summarylog.write(getoutput('uname -a')+'\n')
    summarylog.write('---------- free:\n')
    summarylog.write(getoutput('free')+"\n")
    summarylog.write("\n")
    summarylog.write("---------- calibPipeIF arguments:\n")
    summarylog.write(sys.argv[0]+"\n")
    for o, a in opts:
        if len(a)>0:
            summarylog.write("   "+o+"="+a+"\n")
        else:
            summarylog.write("   "+o+" "+a+"\n")
    summarylog.write("\n")
    envvars=['CASA_ROOT','PYTHONPATH','SCIPIPE_HEURISTICS','PATH']
    for envvar in envvars:
        summarylog.write(("$%s = "%envvar)+os.environ.get(envvar,"")+"\n")
    summarylog.write("\n---------- casa run prefix:\n")
    summarylog.write(casarun+"\n")

    summarylog.write("\n---------- PL git last commit info:\n")
    cmd = "pushd $SCIPIPE_HEURISTICS ; git branch; echo '---------'; git log | head -4 ; popd"
    summarylog.write(getoutput(cmd)+"\n")
    summarylog.close()



    for i in range(5):
        l(" ")
    l("============================================================")
    l("pipeline environment:")
    mylog.run("env")
    l("============================================================")

    # update casa
    if not noupdate:
        mylog.run("export TMPDIR=/lustre/naasc/sciops/comm/rindebet/tmp; xvfb-run -d "+casarun_serial+' -c "os.system(\'update-data\');exit"')


    cmd = "ls -d1 " + ppmr_dir + "/SOUS_uid___*/GOUS_uid___*/MOUS_uid___*/working/"
    dir_working = getoutput(cmd)
    if dir_working.count("No such file"):
        # work for calsurvey with only blah/MOUS
        cmd = "ls -d1 " + ppmr_dir + "/MOUS_uid___*/working/"
        dir_working = getoutput(cmd)
    ppmr_fulldir=dir_working.split("working")[0]+"/"

    cmd = "grep ExecBlockId " + ppmr_fulldir + "/working/PPR_uid___*.xml"
    cmdoutput = getoutput(cmd)
    ebs = cmdoutput.replace("<ExecBlockId>", "").replace(" ", "").replace("</ExecBlockId>", "")
    for i in range(5): l("")
    l("The Execution Blocks in this MOUS are:\n" + ebs)

    chdir(ppmr_fulldir+"/rawdata")
    if len(oldasdms)>0 and flag_and_go:
        for oa in oldasdms:
            os.system("ln -s "+oa+" ./")

    if recipe in ["image", "image_selfcal", "image_selfcal_nocube"]:
        l(" ")
        types=['calapply.txt','flagversions.tgz','caltables.tgz','pipeline_manifest.xml','auxproducts.tgz']
        for caltype in types:
            calfiles = find('uid*.'+caltype, flag_and_go_dir)
            if len(calfiles)>0:
                l("using old cal files of type "+caltype)
                for c in calfiles:
                    l("   "+c)
                    os.system("ln -s "+c+" ./")
            else:
                l("ERROR: no old cal files found of type "+caltype)


    chdir(ppmr_fulldir+"/working")

    cmd = "ls -1 ../working/PPR*xml"
    pprfile = getoutput(cmd)
    if len(semipass) > 0:
        nSemiPassEBs = 1+len(semipass.split(','))
        print("Adding %d SemiPass EBs to the PPR" % (nSemiPassEBs))
        amc.modifyPPR(pprfile, asdm=ebs.replace('\n',',')+','+semipass, newpprname=False)

    # Store the RelativePath of this execution in the variable relative_path
    fd = open(pprfile, "r")
    pprXML = parse(fd)
    nodeList = pprXML.getElementsByTagName('RelativePath')
    print(nodeList)
    nodeList = pprXML.getElementsByTagName('RelativePath')
    if len(nodeList)<1:
        print("pprXML = ", pprXML.toxml())
        print(nodeList)
        print("problem with PPR file - can't find RelativePath")
        pdb.set_trace()
        exit()

    s = nodeList[0] # There should be only 1 RelativePath node
    relative_path = s.firstChild.data # read
    fd.close()


#-----------------------------------------------------------------------------
# Copy the flags commands from last pipeline execution to this new one

    if use_validation_start:
        validation_runs=glob(validation_dir+"/"+obsproject_code+"*")
        if len(validation_runs)<1:
            print("can't find corresponding validation run for "+obsproject_code)
            pdb.set_trace()
            exit(0)
        validation_runs.sort()
        validation_workdirs=[]
        for v in validation_runs:
            moredirs=glob(v+"/SOUS*/GOUS*/MOUS*/working")
            for x in moredirs:
                validation_workdirs.append(x)
        if len(validation_workdirs)<1:
            print("can't find working dir in validation run "+str(validation_runs))
        matchdirs=[]
        for i,v in enumerate(validation_workdirs):
            if mous_underscores in v:
                matchdirs.append(v)
        if len(matchdirs)==0:
            print("can't find working dir in validation run "+str(validation_runs))
        elif len(matchdirs)>1:
            print("found multiple matches for --valid7 working dir:")
            for x in matchdirs:
                print(matchdirs)
            return
        else:
            flag_and_go_dir=matchdirs[0]
            flag_and_go=True
        oldpprfile=""


    if flag_and_go:
        if len(oldpprfile)>0:
            if len(ppr_override)>0 and os.path.exists(pprfile):
                l("Deleting pipelineMakeRequest PPR " + pprfile + " because --PPR was specified")
                os.remove(pprfile)

            cmd  = "cp --force " + oldpprfile + " " +ppmr_fulldir+"/working/"
            l("Copying the PPR from last pipeline execution to this new one. " + getoutput(cmd))
            l(cmd)
            pprfile = os.path.join(ppmr_fulldir, "working", os.path.basename(oldpprfile))
            # Replace RelativePath in PPR.xml with new path
            fd = open(pprfile, "r")
            pprXML = parse(fd)
            old_relative_path = pprXML.getElementsByTagName('RelativePath')[0].firstChild.data
            l("Replacing relative path in " + pprfile + ": " + old_relative_path + " to " + "relative_path")
            pprXML.getElementsByTagName('RelativePath')[0].firstChild.replaceWholeText(relative_path)
            fd.close()
            fd = open(pprfile,"w")
            fd.write(pprXML.toxml())
            fd.close()

        # Copy the flags commands from last pipeline execution to this new one
        oldflagfiles = find('uid*flag*template.txt', flag_and_go_dir)
        print("oldflagfiles=",oldflagfiles)
        for oldflagfile in oldflagfiles:
            if not "html" in oldflagfile:
                shutil.copy(oldflagfile,ppmr_fulldir+"/working/")
                l("Copying the flags commands from last pipeline execution "+ oldflagfile+" "+ppmr_fulldir+"/working/")
        oldflagfiles = find('uid*flagtsystemplate.txt', flag_and_go_dir)
        print("oldflagtsysfiles=",oldflagfiles)
        for oldflagfile in oldflagfiles:
            if not "html" in oldflagfile:
                shutil.copy(oldflagfile,ppmr_fulldir+"/working/")
                l("Copying the tsys flags commands from last pipeline execution "+ oldflagfile+" "+ppmr_fulldir+"/working/")
        oldflagfiles = finddir('uid*ms.wvr*', flag_and_go_dir)
        print("old wvr files=", oldflagfiles)
        for oldflagfile in oldflagfiles:
            oldwvrtable = os.path.basename(oldflagfile)
            shutil.copytree(oldflagfile, os.path.join(ppmr_fulldir,"working",oldwvrtable))
            l("Copying the WVR offsets table from the --flag area"+ oldflagfile+" "+ppmr_fulldir+"/working/")


#-----------------------------------------------------------------------------
# run PPR::import (if not imageonly)

    for i in range(5): l(" ");
    l("assembling casa command")

    nweblog=0 # number counting from 0, of the active weblog in the directory
    if recipe not in ["image","image_selfcal"]:

#-----------------------------------------------------------------------------
# create the fixes script

        fixes_script = """
from __future__ import print_function
import glob,sys
print("start of SACM-fixes script")
        """

        fixes_script=fixes_script+"\nif sys.path.count('"+aUdir+"')<=0:\n    sys.path.append('"+aUdir+"')\n"

        fixes_script=fixes_script+"""
import analysisUtils as aU
if(sys.version_info[0]>=3):
    from casarecipes.almahelpers import fixsyscaltimes
else:
    from recipes.almahelpers import fixsyscaltimes

es = aU.stuffForScienceDataReduction()
mslist = glob.glob('uid___A00*_X*_X*.ms')
fd = open("casa_pipescript.py.txt", "w")

x=os.getcwd()
pid=x.split("/")[-5].split(".")[0]
antcorr=True
if pid.isdigit():
    if int(pid)<2015:
        antcorr=False # should also exclude E2E4?
if antcorr:
    print("getting antenna positions using aU from " + aU.__file__)
    es.correctMyAntennaPositions(mslist,lbc=True)
some2555=False
        """

        if "hsd" in recipe:
            fixes_script=fixes_script+"""
es.getJyPerK(mslist)
        """

        if legacy:
            fixes_script=fixes_script+"""
for thisvis in mslist:
    fixedSyscal=False
    print('Running fixsyscaltimes on '+thisvis)
    fixedSyscal=aU.runFixsyscaltimes(vis = thisvis)
    if fixedSyscal:
        fd.write("    fixsyscaltimes(vis = '" + thisvis + "')")
        print("# SACM/JAO - Fixes", file=fd)
    SSOforfix = es.getFieldsForFixPlanets(thisvis)
    if (len(SSOforfix) > 0):
            print('Running fixplanets...')
            for ssofield in SSOforfix:
                    fd.write("    fixplanets(vis = '" + thisvis + "', field = '" + str(ssofield) + "', fixuvw = True)")
                    print("# SACM/JAO - Fixes", file=fd)
                    fixplanets(vis = thisvis, field = str(ssofield), fixuvw = True)
            """


        if usegetalmaflux:
            fixes_script=fixes_script+"""
fd.close()
print('Running aU.getALMAFluxcsv...')
aU.getALMAFluxcsv('flux.csv')"""
        else:
            fixes_script=fixes_script+"""
fd.close()
print('Running aU.getALMAFluxcsv but ONLY AS BACKUP...')
aU.getALMAFluxcsv('flux.csv',outfile='flux.csv.getalmaflux')"""

        fixes_script=fixes_script+"""
print("end of SACM-fixes script")
"""

        fd = open("sacmPL-fixes.casa.py.txt", "w")
        fd.write(fixes_script)
        fd.close()



        #=================================================================
        # assemble a single run command

        # ( still inside "if recipe != image" block)
        if useresume:
            # use break and resume - single context
            cmd = 'xvfb-run -d '+casarun+' -c "eppr.executeppr(\'' + pprfile + '\',breakpoint=\'hifa_flagdata\',bpaction=\'break\', loglevel=\''+loglevel+'\');execfile(\'sacmPL-fixes.casa.py.txt\');'
        else:
            # use second import - two contexts
            cmd = 'xvfb-run -d '+casarun+' -c "eppr.executeppr(\'' + pprfile + '\',importonly=True, loglevel=\''+loglevel+'\');execfile(\'sacmPL-fixes.casa.py.txt\');'
            nweblog=1

        #--------- added by Todd for findcont testing --------------------------------------------------------------------
        # priority is to use antenna.csv from --flag dir if it is found
        found_antennaposcsv_in_flagdir=False
        if flag_and_go:
            oldantennaposcsvs = find('antennapos.csv', flag_and_go_dir)
            if len(oldantennaposcsvs)>0:
                oldantennaposcsv=[x for x in oldantennaposcsvs if "html" not in x][0]
                print("using oldantennaposcsv=",oldantennaposcsv)
                cmd=cmd+"import shutil;shutil.copy(\'"+oldantennaposcsv+"\',\'"+ppmr_fulldir+"/working/antennapos.csv\');"
                found_antennaposcsv_in_flagdir=True

        #-----------------------------------------------------------------------------
        # priority is to use flux.csv from --flag dir over the one in obscaldir
        found_fluxcsv_in_flagdir=False
        found_contdat_in_flagdir=False
        if flag_and_go:
            oldfluxcsvs= find('flux.csv', flag_and_go_dir)
            if len(oldfluxcsvs)>0:
                oldfluxcsv=[x for x in oldfluxcsvs if "html" not in x][0]
                print("using oldfluxcsv=",oldfluxcsv)
                cmd=cmd+"import shutil;shutil.copy(\'"+oldfluxcsv+"\',\'"+ppmr_fulldir+"/working/flux.csv\');"
                found_fluxcsv_in_flagdir=True

            oldcontdats= find('cont.dat', flag_and_go_dir)
            if len(oldcontdats)>0:
                oldcontdat=[x for x in oldcontdats if "html" not in x][0]
                print("using old cont.dat=",oldcontdat)
                cmd=cmd+"import shutil;shutil.copy(\'"+oldcontdat+"\',\'"+ppmr_fulldir+"/working/cont.dat\');"
                found_contdat_in_flagdir=True


        if staticobscal:
            # use old flux.csv, antennapos, and flagtemplates if exist in obscaldir
            oldfluxcsvs2 = find('*'+mous_underscores+'*flux.csv', obscaldir)
            if len(oldfluxcsvs2)>0:
                oldfluxcsv2=oldfluxcsvs2[0]
                if found_fluxcsv_in_flagdir:
                    print("found "+oldfluxcsv2+", but "+oldfluxcsv+" takes precendence, so using the latter")
                else:
                    print("using fluxcsv=",oldfluxcsv2)
                    cmd=cmd+"import shutil;shutil.copy(\'"+oldfluxcsv2+"\',\'"+ppmr_fulldir+"/working/flux.csv\');"
            else:
                print("looked but didn't find MOUS*flux.csv in "+obscaldir)

            # use old antennapos.csv if exists in obscaldir
            oldantpos = find('*'+mous_underscores+'*antennapos.csv', obscaldir)
            if len(oldantpos)>0:
                oldantpos=oldantpos[0]
                if found_antennaposcsv_in_flagdir:
                    print("found "+oldantpos+", but "+oldantennaposcsv+" takes precendence, so using the latter")
                else:
                    print("using antpos=",oldantpos)
                    cmd=cmd+"import shutil;shutil.copy(\'"+oldantpos+"\',\'"+ppmr_fulldir+"/working/antennapos.csv\');"
            else:
                print("looked but didn't find MOUS*antennapos.csv in "+obscaldir)


            oldflagfiles=[]
            for eb in ebs.split("\n"):
                eb_under=eb.replace('://','___').replace('/','_')
                oldflagfiles = oldflagfiles + find(eb_under+'*flag*template.txt', obscaldir)
            print("oldflagfiles=",oldflagfiles)
            for oldflagfile in oldflagfiles:
                if not "html" in oldflagfile:
                    shutil.copy(oldflagfile,ppmr_fulldir+"/working/")
                    l("Copying the flags commands from obscal: "+ oldflagfile+" "+ppmr_fulldir+"/working/")


        if oldcont:
            # use old cont.dat if exists in obscaldir
            oldcontdat2s = find('*'+mous_underscores+'*cont.dat', obscaldir)
            if len(oldcontdat2s)>0:
                oldcontdat2=oldcontdat2s[0]
                if found_contdat_in_flagdir:
                    print("found "+oldcontdat2+", but "+oldcontdat+" takes precendence, so using the latter")
                else:
                    print("using cont.dat=",oldcontdat2)
                    cmd=cmd+"import shutil;shutil.copy(\'"+oldcontdat2+"\',\'"+ppmr_fulldir+"/working/cont.dat\');"
            else:
                print("looked but didn't find MOUS*cont.dat in "+obscaldir)


        print

        #-----------------------------------------------------------------------------
        # add rest of PL

        if useresume:
            cmd = cmd + 'eppr.executeppr(\'' + pprfile + '\',breakpoint=\'hifa_importdata\',bpaction=\'resume\', loglevel=\''+loglevel+'\');exit;"'
        else:
            cmd = cmd + 'eppr.executeppr(\'' + pprfile + '\',importonly=False,loglevel=\''+loglevel+'\');exit;"'


    # ---------------------------------------------------------------------------------
    else:
        # recipe==image or image2:
        cmd='xvfb-run -d '+casarun+' -c "eppr.executeppr(\'' + pprfile + '\', loglevel=\''+loglevel+'\');exit;"'

    # ---------------------------------------------------------------------------------

    # actually run
    if verbose:
        retcode=mylog.run(cmd)
    else:
        retcode=mylog.runquiet(cmd)

    # link to weblog and working
    cmd = "ls -d1 " + ppmr_dir + "/SOUS_uid___*/GOUS_uid___*/MOUS_uid___*/working/pipeline-*/html"
    weblogdir = getoutput(cmd).split("\n")[nweblog]
    xx=weblogdir.split("SOUS")
    mylog.run("pushd "+xx[0]+"; ln -s SOUS"+xx[1]+" weblog; popd")
    mylog.run("pushd "+xx[0]+"; ln -s SOUS"+xx[1]+"/index.html weblog.html; popd")
    cmd = "ls -d1 " + ppmr_dir + "/SOUS_uid___*/GOUS_uid___*/MOUS_uid___*/working"
    workdir = getoutput(cmd).split("\n")[-1]
    xx=weblogdir.split("SOUS")
    xwork=xx[1].split("working")[0]+"working"
    mylog.run("pushd "+xx[0]+"; ln -s SOUS"+xwork+" working; popd")



    #-----------------------------------------------------------------------------
    # finish putting fixes in the right files

    if recipe not in ["image","image_selfcal"]:

        # Procedure to include fixes in casa_pipescript
        cmd = "ls -d1 " + ppmr_dir + "/SOUS_uid___*/GOUS_uid___*/MOUS_uid___*/products/uid___*.casa_pipescript.py"
        cmdoutput = getoutput(cmd)
        if "cannot" in cmdoutput:
            print("can't find casa_pipescript - pipeline failed?")
            exit()
        l("Starting the routine to add fixes to casa_pipescript file " + cmdoutput)

        fd = open(cmdoutput, "r")
        lines = fd.readlines()
        fd.close()

        fd = open("casa_pipescript.py.txt", "r")
        fixeslines = fd.readlines()
        fd.close()

        l("%i Fixes to be applied are: "%len(fixeslines))
        for f in fixeslines:
            l(f)

        newlines = list()
        if len(fixeslines)>0:
            if(sys.version_info[0]>=3):
                newlines.append('from casarecipes.almahelpers import fixsyscaltimes # SACM/JAO - Fixes\n')
            else:
                newlines.append('from recipes.almahelpers import fixsyscaltimes # SACM/JAO - Fixes\n')

        for line in lines:
            newlines.append(line)
            if 'hifa_importdata' in line and len(fixeslines)>0:
                newlines = newlines + fixeslines
                newlines.append("    h_save() # SACM/JAO - Finish weblog after fixes\n")
                newlines.append("    h_init() # SACM/JAO - Restart weblog after fixes\n")
                newlines.append(line)
        fd = open(cmdoutput, "w")
        fd.writelines(newlines)
        fd.close()


        # Procedure to include fixes in casa_piperestorescript
        restore_script = glob(ppmr_dir + "/SOUS_uid___*/GOUS_uid___*/MOUS_uid___*/products/uid___*.casa_piperestorescript.py")[0]
        l("Starting the routine to add fixes to casa_piperestorescript file " + restore_script)

        fd = open(restore_script, "r")
        lines = fd.readlines()
        fd.close()

        fd = open("casa_pipescript.py.txt", "r")
        fixeslines = fd.readlines()
        fd.close()

        newlines = list()
        if len(fixeslines)>0:
            if(sys.version_info[0]>=3):
                newlines.append('from casarecipes.almahelpers import fixsyscaltimes # SACM/JAO - Fixes\n')
            else:
                newlines.append('from recipes.almahelpers import fixsyscaltimes # SACM/JAO - Fixes\n')

        for line in lines:
            if 'hifa_restoredata' in line:
                if len(fixeslines)>0:
                    newlines.append(line.replace("hifa_restoredata", "hifa_importdata").replace("'uid___", "'../rawdata/uid___").replace('vis=[', 'dbservice=False, vis=['))
                    newlines = newlines + fixeslines
                    newlines.append("    h_save() # SACM/JAO - Finish weblog after fixes\n")
                    newlines.append("    h_init() # SACM/JAO - Restart weblog after fixes\n")
            newlines.append(line)
        # Perform the actual modification of casa_piperestorescript
        fd = open(restore_script, "w")
        fd.writelines(newlines)
        fd.close()



    if dopickle:
        mous_uid_underscores=mous_uid.replace('://','___').replace('/','_')
        l("pipeline finished, pickling")
        if ppmr_rel_dir[-1]=="/":
            ppmr_rel_dir=ppmr_rel_dir[0:-1]
        cmd = 'xvfb-run -d '+casarun_serial+' -c "aU.picklePipeRun(\''+ppmr_dir+'\',outfile=\''+pickle_dir.rstrip("/")+'/'+mous_uid_underscores+"_"+ppmr_rel_dir+'.pkl\',debug=True);exit;"'
        l('Starting to run the command "' + cmd + '"')
        retcode=retcode + mylog.runquiet(cmd)


    l("done with fixes")
    if retcode>1:
        l("calibPipeIF.py has finished with an error :(")
    else:
        l("calibPipeIF.py has finished :)")
    mylog.close()
    print("Ran: ")
    print("MOUS "+mous_uid)
    print("PL   "+branch+" version "+pipeversion)
    print("CASA "+casaroot)
    print("output in " + ppmr_dir)


main()
