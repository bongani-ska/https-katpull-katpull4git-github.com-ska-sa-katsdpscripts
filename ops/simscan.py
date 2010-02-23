# Small test script to generate some simulated target signal data using the dbe simulator.

from __future__ import with_statement

import katuilib
import uuid

target = 'jastgt,azel,20,40'

with katuilib.tbuild('cfg-local.ini', 'local_ff_2dish') as kat:

    # tell the dbe sim to make a test target at specfied az and el
    kat.dbe.req.dbe_test_target(20,40,100)

    # tell the dbe simulator where the antenna is so that is can generate target flux at the right time
    kat.ant1.sensor.pos_actual_scan_azim.register_listener(kat.dbe.req.dbe_pointing_az, 0.5)
    kat.ant1.sensor.pos_actual_scan_elev.register_listener(kat.dbe.req.dbe_pointing_el, 0.5)

    with katuilib.CaptureSession(kat, str(uuid.uuid1()), 'ffuser', 'Sim target scans example', kat.ants) as session:
        session.raster_scan(target, scan_duration=20.0)
