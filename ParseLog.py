#!/usr/bin/python

# dependencies
# pip install python-can==3.3.2
# pip install quantities
# python python-j1939/setup.py install (from https://github.com/milhead2/python-j1939)

# system modules
import math
import sys
import fileinput
import time
import struct
import json
import threading
import os
from pprint import pprint
import j1939

# local modules
from lib.nmea2000 import Nmea2000Reader, Nmea2000State, NmeaLogger, PgnPrinter

#
# parse NMEA 2000 data and run it through our system
# The data format matches what is written by a Raymarine plotter running Lighthouse II
# Example record:
# Rx 478700 09 f5 03 05 f8 00 00 ff ff ff ff ff
# ignored-- header----- data-------------------
#
def parseLog():
    consumers = [ PgnPrinter() ]
    reader = Nmea2000Reader(consumers)

    for line in fileinput.input():
        line = line.rstrip()
        if not line: continue

        words = line.split()
        if words[0] == "Rx" or words[0] == "Tx":
            # parse Raymarine log
            identifier = int(''.join(words[2:6]), 16)
            data = bytearray.fromhex(''.join(words[6:]))
            arbitration_id = j1939.ArbitrationID()
            arbitration_id.can_id = identifier
        else:
            # candump log
            identifier = int(words[1], 16)
            data = bytearray.fromhex(''.join(words[3:]))

        arbitration_id = j1939.ArbitrationID()
        arbitration_id.can_id = identifier

        #print("%-3i: pgn=%-6i line=%s" % (arbitration_id.source_address, arbitration_id.pgn.value, line))

        reader.HandlePacket(arbitration_id, data)

# parse NMEA 2000 network data from CAN bus
def parseNetwork():
    bus = j1939.Bus()
    consumers = [ PgnPrinter() ]
    reader = Nmea2000Reader(consumers)
    try:
        for msg in bus:
            reader.HandlePacket(msg.arbitration_id, msg.data)
    except KeyboardInterrupt:
        bus.shutdown()

if len(sys.argv) < 2:
    pathname = os.path.dirname(sys.argv[0])        
    fullpath = os.path.abspath(pathname)
    print("starting in %s" % fullpath)
    os.chdir(fullpath)
    parseNetwork()
else:
    print("parselog");
    parseLog()
