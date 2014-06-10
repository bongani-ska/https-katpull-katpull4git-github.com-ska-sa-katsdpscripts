#!/usr/bin/python
# Script that will search through a .h5 file for noise diode firings and
# calculate change in mean counts in the data due to each noise diode firing.
# Output is written to a file which lists the target that is being observed during
# the noise diode firing and the timestamp of the scan and the noise diode
# jump in counts in the HH and VV polarisations.
#
# This is intended to be used for survivability and strong source tests
# changes in the mean value of noise diode jumps can indicate that the data
# is saturated.
#
# TM: 27/11/2013


import optparse

from matplotlib.backends.backend_pdf import PdfPages
import pylab as plt

import numpy as np
import scipy.interpolate as interpolate
import scipy.signal as signal
import math
import os

import scape
from scape.stats import robust_mu_sigma

from katsdpscripts.RTS import qt_2_8_strong_sources

def parse_arguments():
    parser = optparse.OptionParser(usage="%prog [opts] <file>")
    parser.add_option("-a", "--antenna", type="string", default='sd', help="Antenna to load, default is first single-dish baseline in file.")
    parser.add_option("-f", "--freq-chans", help="Range of frequency channels to keep (zero-based, specified as 'start,end', default is 50% of the bandpass.")
    parser.add_option("-t", "--targets", default='all', help="List of targets to select (default is all)")
    parser.add_option("-o", "--output_dir", default='.', help="Output directory. Default is cwd")
    (opts, args) = parser.parse_args()

    return opts, args

# Print out the 'on' and 'off' values of noise diode firings from an on->off transition to a text file.
opts, args = parse_arguments()

qt_2_8_strong_sources.analyse_noise_diode(args[0],output_dir=opts.output_dir,antenna=opts.antenna,targets=opts.targets,freq_chans=opts.freq_chans)

