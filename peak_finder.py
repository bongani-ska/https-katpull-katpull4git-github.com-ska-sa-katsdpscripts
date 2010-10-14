#!/usr/bin/python

# The *with* keyword is standard in Python 2.6, but has to be explicitly imported in Python 2.5
from __future__ import with_statement

import optparse
import sys
import uuid
import time
import katuilib
import katpoint
import numpy as np

# Parse command-line options that allow the defaults to be overridden
parser = optparse.OptionParser(usage="%prog [options]",
                               description="Perform mini (Zorro) raster scans across the holography sources \
                                            Some options are **required**.")

# Generic options
parser.add_option('-i', '--ini_file', dest='ini_file', type="string", metavar='INI', help='Telescope configuration ' +
                  'file to use in conf directory (default reuses existing connection, or falls back to cfg-local.ini)')
parser.add_option('-s', '--selected_config', dest='selected_config', type="string", metavar='SELECTED',
                  help='Selected configuration to use (default reuses existing connection, or falls back to local_ff)')
parser.add_option('-u', '--experiment_id', dest='experiment_id', type="string",
                  help='Experiment ID used to link various parts of experiment together (UUID generated by default)')
parser.add_option('-o', '--observer', dest='observer', type="string",
                  help='Name of person doing the observation (**required**)')
parser.add_option('-d', '--description', dest='description', type="string", default="Point source scan",
                  help='Description of observation (default="%default")')
parser.add_option('-a', '--ants', dest='ants', type="string", metavar='ANTS',
                  help="Comma-separated list of antennas to include in scan (e.g. 'ant1,ant2')," +
                       " or 'all' for all antennas (**required** - safety reasons)")
parser.add_option('-w', '--discard_slews', dest='record_slews', action="store_false", default=True,
                  help='Do not record all the time, i.e. pause while antennas are slewing to the next target')
(opts, args) = parser.parse_args()

# Various non-optional options...
if opts.ants is None:
    print 'Please specify the antennas to use via -a option (yes, this is a non-optional option...)'
    sys.exit(1)
if opts.observer is None:
    print 'Please specify the observer name via -o option (yes, this is a non-optional option...)'
    sys.exit(1)
if opts.experiment_id is None:
    # Generate unique string via RFC 4122 version 1
    opts.experiment_id = str(uuid.uuid1())

if tgt is None:
    print "Please assign a tgt variable before calling this script..."
    sys.exit(1)

# Try to build the given KAT configuration (which might be None, in which case try to reuse latest active connection)
# This connects to all the proxies and devices and queries their commands and sensors
try:
    kat = katuilib.tbuild(opts.ini_file, opts.selected_config)
# Fall back to *local* configuration to prevent inadvertent use of the real hardware
except ValueError:
    kat = katuilib.tbuild('cfg-local.ini', 'local_ff')
print "\nUsing KAT connection with configuration: %s\n" % (kat.get_config(),)

if kat.dh.sd is None:
    print "You need a running signal display session before calling this script..."
    sys.exit(1)
# The real experiment: Create a data capturing session with the selected sub-array of antennas
with katuilib.BasicCaptureSession(kat, opts.experiment_id, opts.observer, opts.description,
                                  opts.ants, opts.record_slews) as session:

    kat.dbe.req.k7w_write_hdf5(0)
    kat.dbe.req.capture_stop()
    kat.dbe.req.capture_setup()
    kat.dbe.req.capture_start()
    kat.ant1.req.target(tgt)
    kat.ant1.req.mode("POINT")
    kat.ant1.wait("lock",1,300)
     # wait for lock on boresight target
    start_time = time.time()
    for x in [-0.5,0,0.5]:
        kat.ant1.req.scan_asym(-3,x,3,x,20)
        kat.ant1.wait("lock",1,300)
        kat.ant1.req.mode("SCAN")
        kat.ant1.wait("scan_status","after",300)
    end_time = time.time()
    az = kat.ant1.sensor.pos_actual_scan_azim.get_stored_history(start_time=start_time, end_time=end_time, select=False)
    el = kat.ant1.sensor.pos_actual_scan_azim.get_stored_history(start_time=start_time, end_time=end_time, select=False)
    data = kat.dh.sd.select_data(product=1,start_time=start_time,end_time=end_time,avg_axis=1, start_channel=100, stop_channel=400, include_ts=True)
print "Done...Data available in az,el,data"
