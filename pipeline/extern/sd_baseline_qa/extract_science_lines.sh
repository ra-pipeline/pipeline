#!/bin/bash

#Save current environment variables
OLDPATH=$PATH
OLDPYTHONPATH=$PYTHONPATH

# ================= CONFIGURATION =================
# Node names to search for in the XML file
NODE_A_NAME="CasaVersion"
NODE_B_NAME="PipelineVersion"

# -------------------------------------------------
# LOOKUP TABLE
# Format: NodeA_Value  NodeB_Value  Release  CASAPATH
# Use spaces or tabs to separate columns.
# -------------------------------------------------
read -r -d '' LOOKUP_TABLE << EOM
6.4.1.12  2022.2.0.64   2022AUG  casa-6.4.1-12-pipeline-2022.2.0.64
6.5.4.9   2023.1.0.124  2023AUG  casa-6.5.4-9-pipeline-2023.1.0.124
6.4.1.12  2022.2.0.64   2023FEB  casa-6.4.1-12-pipeline-2022.2.0.64
6.4.1.12  2022.2.0.68   2023JUN  casa-6.4.1-12-pipeline-2022.2.0.68
6.5.4.9   2023.1.0.124  2024JUN  casa-6.5.4-9-pipeline-2023.1.0.124
6.6.1.17  2024.1.0.8    2024OCT  casa-6.6.1-17-pipeline-2024.1.0.8
6.6.6.17  2025.1.0.35   2025OCT  casa-6.6.6-17-pipeline-2025.1.0.35-py3.10.el8
6.7.3.1   2026.0.0.39   2026OCT  casa-6.7.3-1-py3.12.el8
EOM
# =================================================

# 1. Validate Input Argument
INPUT_DIR="$1"

if [[ -z "$INPUT_DIR" ]]; then
    echo "Error: No directory provided."
    echo "Usage: $0 <directory_path>"
    exit 1
fi

if [[ ! -d "$INPUT_DIR" ]]; then
    echo "Error: Directory '$INPUT_DIR' does not exist."
    exit 1
fi

# 1.5 Search for working folder
workingfolder=`ls -d /work/dev/joshua.hoskins/verification/absolute_off/working`

#1.75 set up parameter for python
# Fixed command line arguments for the program
PROG_ARGS="os=__import__(""'""os""'"");sd_qa_utils=__import__(""'""sd_qa_utils""'"");os.chdir(""'""$workingfolder""'"");sd_qa_utils.read_sci_line_data_from_context();"

# 2. Search for the first XML file in the directory
XML_FILE=`ls -d /work/dev/joshua.hoskins/verification/absolute_off/working/pipeline_aquareport.xml`

if [[ -z "$XML_FILE" ]]; then
    echo "Error: No XML file found in '$INPUT_DIR'."
    exit 1
fi

echo "Found configuration file: $XML_FILE"

# 3. Extract Values (Simple Parsing)
# This looks for <NodeName>Value</NodeName> pattern
val_a=$(grep -o "<$NODE_A_NAME>[^<]*" "$XML_FILE" | cut -d'>' -f2)
val_b=$(grep -o "<$NODE_B_NAME>[^<]*" "$XML_FILE" | cut -d'>' -f2)

if [[ -z "$val_a" || -z "$val_b" ]]; then
    echo "Error: Could not find nodes <$NODE_A_NAME> and <$NODE_B_NAME> in $XML_FILE."
    exit 1
fi

echo "Detected Configuration: $val_a | $val_b"

# 4. Parse Lookup Table and Set Environment
match_found=false

while read -r num1 num2 release casapath; do
    # Skip empty lines
    [[ -z "$num1" ]] && continue
    
    if [[ "$num1" == "$val_a" && "$num2" == "$val_b" ]]; then
        echo "Match found in lookup table."
        
        # Prepend to existing environment variables
        #export PATH="/opt/pipelinedriver/$release/casa/$casapath/bin:/users/hfrancke/bin/sd-applycal-qa"
        #export PYTHONPATH="/opt/pipelinedriver/$release/bin/common_dependencies/lib/python/site-packages/:/opt/pipelinedriver/$release/bin/pipeline_driver_build/lib/python/site-packages/:/users/hfrancke/bin/sd-applycal-qa"
        
        match_found=true
        break
    fi
done <<< "$LOOKUP_TABLE"

if [ "$match_found" = false ]; then
    echo "Error: No matching configuration found in lookup table for values $val_a and $val_b."
    exit 1
fi

echo "PATH:"
echo $PATH
echo "PYTHONPATH:"
echo $PYTHONPATH
echo "--------------------------------"
echo "Launching python3 -c $PROG_ARGS"
echo "--------------------------------"
python3 -c "$PROG_ARGS"
