################################################################################
#
# Copyright (C) 2016-2022 Advanced Micro Devices, Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
################################################################################
import argparse
import os
import yaml
import sys
import csv
csv.register_dialect('strip', skipinitialspace=True)
sys.path.append(os.path.join(os.path.dirname(sys.path[0]),'..','Tensile'))
from DataType import DataType

def parseArgs():
    argParser = argparse.ArgumentParser()
    
    h = {"inpLibLogic"   : "input logic file", \
         "outDir"        :  "Output logic file directory has performance converted efficiency", \
         "inpCSVForFreq" : "get the sclk from this file",\
         "sclk"          : "SCLK frequency in MHz tuning was done at", \
         "specs"         : ".yaml file containing hardware specifications", \
         "per-cu"        : "If tuning was done per CU", \
         "name"          : "Name substring to filter which files are modified", \
         "mfma"          : "If MFMA instructions were used for tuning", \
         "mi50"          : "For vega20, if tuning was done on mi50"
    }

    argParser.add_argument("inpLibLogic", metavar="input-logic-file", type=str, help=h["inpLibLogic"])
    argParser.add_argument("outDir", metavar="output-dir", type=str, help=h["outDir"])
    argParser.add_argument("--inpCSVForFreq", metavar="input-csv-1",type=str,help=h["inpCSVForFreq"])
    argParser.add_argument("--sclk",type=int,help=h["sclk"])
    argParser.add_argument("specs", metavar="hardware-specs", nargs="?", type=str, default="default_specs.yaml", help=h["specs"])
    argParser.add_argument("-p", "--per-cu", action="store_true", help=h["per-cu"])
    argParser.add_argument("-n", "--name", type=str, help=h["name"])
    argParser.add_argument("-m", "--mfma", action="store_true", help=h["mfma"])
    argParser.add_argument("--mi50", action="store_true", help=h["mi50"])
    return argParser.parse_args()
    
# sclk: MHz
# alu: flops/cycle/CU
def peakGFlops(sclk, alu, numCUs):
    return (sclk / 1000) * alu * numCUs
    
def sameSize(yS, cS):
    return yS[0] == int(cS["SizeI"]) and yS[1] == int(cS["SizeJ"]) and yS[2] == int(cS["SizeK"]) and yS[3] == int(cS["SizeL"]) and yS[4] == int(cS["LDD"]) and yS[5] == int(cS["LDC"]) and yS[6] == int(cS["LDA"]) and yS[7] == int(cS["LDB"])

def getFreq(libLogicData,csvRows):
    freqFound = False
    for gemmDataFromCSV in csvRows:
       if sameSize(libLogicData[0], gemmDataFromCSV):
         freq = int(gemmDataFromCSV["WinnerFreq"])
         freqFound = True
    if freqFound == False:
       print("Error,exiting program..Frequency information not found for size: ", libLogicData[0])
       exit(1)
    return freq 

def main():
    args = parseArgs()
    mfmaKey = "mfma" if args.mfma else "non_mfma"
    
    try:
        os.makedirs(args.outDir)
    except OSError:
        pass

    with open(args.specs) as y:
        specs = yaml.safe_load(y)
    
    if (not args.inpCSVForFreq and not args.sclk) or (args.inpCSVForFreq and args.sclk):
      print("error: {} Specify frequency information either through CSV file (or) through SCLK parameter to calculate efficiency ..")
      exit(1)

    freq = 0
    if args.sclk:
       freq = args.sclk
       print("Frequency based on SCLK parameter",freq)
    else:
      csvRows = []
      print("Frequency information from the CSV file ",args.inpCSVForFreq)
      with open(args.inpCSVForFreq) as f:
        rows = csv.DictReader(f,dialect='strip')
        for r in rows:
            csvRows.append(r)
       
    with open(args.inpLibLogic) as inputLibLogicFile:
        libLogicFileData = yaml.safe_load(inputLibLogicFile)

    sched = libLogicFileData[1]
    type = DataType(libLogicFileData[4]["DataType"]).toChar()
    
    if type in specs[sched][mfmaKey]:
      alu = specs[sched][mfmaKey][type]
    else:
      print("error: {} data type does not exist in the spec file. Modify the spec file.".format(type))
      return
    
    # get CU count
    if args.per_cu:
        numCUs = 1
    elif sched == "vega20":
        gpu = "mi50" if args.mi50 else "mi60"
        numCUs = specs[sched]["numCUs"][gpu]
    else:
        numCUs = specs[sched]["numCUs"]

    if args.sclk:
      peak = peakGFlops(freq, alu, numCUs)
      for entry in libLogicFileData[7]:
        #ConvertEffFromSCLK(peak,libLogicFileData[7])
        eff = entry[1][1] / peak
        entry[1][1] = round (100 * eff, 3)
        print("Size: ", entry[0])
        print("Efficiency: ", entry[1][1])
        print("Frequency: ", freq)
        print()        
    else: # CSV file
       for entry in libLogicFileData[7]:
        freq = getFreq(entry,csvRows)
        peak = peakGFlops(freq, alu, numCUs)
        eff = entry[1][1] / peak
        entry[1][1] = round (100 * eff, 3)
        print("Size: ", entry[0])
        print("Efficiency: ", entry[1][1])
        print("Frequency: ", freq)
        print()

    fName = os.path.basename(args.inpLibLogic)
    outFile = os.path.join(args.outDir, fName)
    
    with open(outFile, "w") as y:
        yaml.safe_dump(libLogicFileData, y, default_flow_style=None)

if __name__ == "__main__":
    main()
