#!/usr/bin/env python
import sys
import os
import optparse

usage = """
Generate sbatch files for running an mRNA-seq pipeline.
Usage:

generate_sbatch.py <directory of FASTQ files> <Bowtie index for reference genome> <gene/transcript annotation GTF file> 

The three first options are mandatory. There are further flags you can use:

-o, --old: Run old TopHat (1.0.14) instead - mainly to reproduce old runs
-t, --projtag: Provide a project tag that will be shown in the queuing system to distinguish from other TopHat runs
-p, --phred33: Use phred33 / Sanger quality scale, e g for MiSeq or CASAVA 1.8 and above
-f, --fai: Generate UCSC Genome Browser compatible BigWig tracks, using the specified FASTA index (fai) file

"""

if len(sys.argv) < 4:
    print usage
    sys.exit(0)

parser = optparse.OptionParser()
parser.add_option('-o', '--old', action="store_true", dest="old", default="False", help="Run old TopHat (1.0.14) instead - mainly to reproduce old runs")
parser.add_option('-t', '--projtag', action="store", dest="projtag", default="", help="Provide a project tag that will be shown in the queuing system to distinguish from other TopHat runs")
parser.add_option('-p', '--phred33', action="store_true", dest="phred33", default="False", help="Use phred33 / Sanger quality scale, e g for MiSeq or CASAVA1.8 and above")
parser.add_option('-f', '--fai', action="store", dest="fai", default="", help="Provide FASTA index file for generating UCSC bigwig tracks")

(opts, args) = parser.parse_args()

old = opts.old
phred33 = opts.phred33
fai = opts.fai
projtag = opts.projtag

qscale = '--solexa1.3-quals'
if phred33 == True: qscale = ''

fpath = sys.argv[1]
refpath = sys.argv[2]
annopath = sys.argv[3]

flist = os.listdir(fpath)

sample_names = []
read1forsample = {}
read2forsample = {}

for fname in flist:
    if 'fastq' not in fname: continue 
    read = fname.split("_")[-1]
    tag = "_".join(fname.split("_")[3:-2])
    print fname.split("_")
    # 2_date_fcid_sample_1.fastq
    if not tag in sample_names: sample_names.append(tag)
    if read == "1.fastq": read1forsample[tag]=fname
    if read == "2.fastq": read2forsample[tag]=fname

print "Best guess for sample names: "
for n in sorted(sample_names):
    print n

r = raw_input("Press n to exit")
if r.upper() == "N": sys.exit(0)

#sFile = open("sample_names.txt", "w")
#for n in sorted(sample_names): 
#    sFile.write(n + "\n")

for n in sorted(sample_names):
    print "Generating sbatch files for sample ", n
    oF = open("map_tophat_" + n + ".sh", "w")
    oF.write("#! /bin/bash -l\n")
    oF.write("#SBATCH -A a2010002\n")                   
    oF.write("#SBATCH -p node\n")
    oF.write("#SBATCH -t 35:00:00\n")
    oF.write("#SBATCH -J tophat_" + n + projtag + "\n")
    oF.write("#SBATCH -e tophat_" + n + projtag + ".err\n")
    oF.write("#SBATCH -o tophat_" + n + projtag + ".out\n")
    oF.write("#SBATCH --mail-user=mikael.huss@scilifelab.se\n")
    oF.write("#SBATCH --mail-type=ALL\n")

    oF.write("module unload bioinfo-tools\n")
    oF.write("module unload samtools\n")
    oF.write("module unload tophat\n")
    oF.write("module unload cufflinks\n")
    oF.write("module unload htseq\n")

    oF.write("module load bioinfo-tools\n")
    oF.write("module load samtools/0.1.9\n")
    
    if old == True: oF.write("module load tophat/1.0.14\n")
    else: oF.write("module load tophat/1.3.3\n")
    oF.write("module load cufflinks/1.3.0\n")
    oF.write("module load htseq/0.5.1\n")

    # TopHat

    size = raw_input("Fragment size including adapters for sample" + n + "? ")
    innerdist = int(size) - 101 - 101 - 121
    if not size.isdigit(): sys.exit(0)

    oF.write("tophat -o tophat_out_" + n + " " + qscale + " -p 8 -r " + str(innerdist) + " " + refpath + " " + fpath + "/" + read1forsample[n] + " " + fpath + "/" + read2forsample[n] + "\n")
    # Samtools -> Picard

    oF.write("cd tophat_out_" + n + "\n")
    if old == True: oF.write("samtools view -bT concat.fa.fa -o accepted_hits_" + n + ".bam " + "accepted_hits.sam\n")
    else: oF.write("mv accepted_hits.bam accepted_hits_" + n + ".bam\n")
    oF.write("java -Xmx2g -jar /home/lilia/glob/src/picard-tools-1.29/SortSam.jar INPUT=accepted_hits_" + n + ".bam OUTPUT=accepted_hits_sorted_" + n + ".bam SORT\
_ORDER=coordinate VALIDATION_STRINGENCY=LENIENT\n")
    oF.write("java -Xmx2g -jar /home/lilia/glob/src/picard-tools-1.29/MarkDuplicates.jar INPUT=accepted_hits_sorted_" + n + ".bam OUTPUT=accepted_hits_sorted_dup\
Removed_" + n + ".bam ASSUME_SORTED=true REMOVE_DUPLICATES=true METRICS_FILE=" + n + "_picardDup_metrics VALIDATION_STRINGENCY=LENIENT\n")

    # HTSeq
    oF.write("samtools view accepted_hits_sorted_dupRemoved_" + n + ".bam |sort > accepted_hits_sorted_dupRemoved_prehtseq_" + n + ".sam\n")
    oF.write("python -m HTSeq.scripts.count -s no -q accepted_hits_sorted_dupRemoved_prehtseq_" + n + ".sam " + annopath + " > " + n + ".counts\n")

    # Cufflinks

    # To use indexed BAM file in Cufflinks

    oF.write("samtools index accepted_hits_sorted_dupRemoved_" + n + ".bam\n")
    oF.write("cufflinks -p 8 -G " + annopath + " -o cufflinks_out_" + n + " accepted_hits_sorted_dupRemoved_" + n + ".bam\n")
    
    # To use col 3-4 sorted SAM file in Cufflinks

    #oF.write("samtools view accepted_hits_sorted_dupRemoved_" + n + ".bam |sort -k 3,3 -k 4,4n > accepted_hits_sorted_dupRemoved_col34Sorted_" + n + ".sam\n")
    #oF.write("cufflinks -p 8 -G " + annopath + " -o cufflinks_out_" + n + " accepted_hits_sorted_dupRemoved_col34Sorted_" + n + ".sam\n")

    # Make custom tracks
    if fai != '':
        oF.write("/bubo/home/h9/mikaelh/software/BEDTools-Version-2.10.1/bin/genomeCoverageBed -bga -split -ibam accepted_hits_sorted_dupRemoved_" + n + ".bam -g " + fai + " > sample_" + n + ".bga \n")
        oF.write("/bubo/home/h9/mikaelh/bin/bedGraphToBigWig sample_" + n + ".bga " + fai + " sample_" + n + ".bw\n")

    # Clean up
    oF.write("rm accepted_hits_sorted_" + n + ".bam\n")
    oF.write("rm accepted_hits_sorted_dupRemoved_prehtseq_" + n + ".sam\n")
    # oF.write("rm accepted_hits_sorted_dupRemoved_col34Sorted_" + n + ".sam\n")

    oF.close()







