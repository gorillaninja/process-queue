#!/bin/bash

set -e
#set -x

short=${1-36h}
long=${2-7d}

# Pull all log entries into a single file
find * -name '*.log' -exec sort -u {} + > new.log
mv new.log combined.log

# Remove empty subdir files more than 36h old
find */* -mtime +$short -empty -exec rm {} +

# Remove STDOUT files (HandBrake-specific)
#find */* -name '*.stdout' -mtime +$short -exec rm {} +

# Remove subdir log files more than 36h old
find */* -name '*.log' -mtime +$short -exec rm {} +

# Compress command output more than 36h old
find */* -name '*.stderr' -mtime +$short -exec gzip -9 {} \;
find */* -name '*.stdout' -mtime +$short -exec gzip -9 {} \;

# Delete compressed files more than a week old
find */* -name '*.gz' -mtime +$long -exec rm {} +

