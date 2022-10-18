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
from lib.RepeatTimer import RepeatTimer
from lib.nmea2000 import Nmea2000Reader, Nmea2000State, NmeaLogger, PgnPrinter
from lib.nmea0183server import Nmea0183Server
from lib.network import BroadcastServer

# 
# Output JSON that is compatible with canboat's analyzer.  This is sent over
# port 10111
#
# This is buffered and sent every half second
#
class JsonServer(object):
    #
    # Initialize the server
    #
    def __init__(self, port=10111, interval=0.5):
        self.__server = BroadcastServer(port, interval, self.__Transmit, self.__Connect)
        self.__lock = threading.Lock()
        self.__sendBuffer = []
        self.__clientCount = 0

    #
    # transmit the contents of the send buffer to all clients
    #
    def __Transmit(self):
        with self.__lock:
            output = '\n'.join(self.__sendBuffer) + '\n'
            self.__sendBuffer = []

        return output

    # 
    # __Connect is called by BroadcastServer whenever the number of connected
    # clients has changed
    #
    def __Connect(self, clientCount):
        with self.__lock:
            self.__clientCount = clientCount

    # 
    # ConsumePgn is called as incoming NMEA 2000 PGNs come in.  It reformats
    # the record as JSON and appends it to the send buffer
    #
    # pgn - the PGN related to this record
    # dataRecord - The data that is being shown in the record
    # pgnRecord - the record from pgnTable with the meta-information 
    #   about this PGN
    #
    def ConsumePgn(self, pgn, dataRecord, pgnRecord):
        # don't do anything if there aren't any clients
        #if self.__clientCount == 0:
        #    return None

        outObject = {}
        # 2015-04-02-18:23:39.000
        # TODO -- output milliseconds
        outObject["timestamp"] = time.strftime("%Y-%m-%d-%H:%M:%S.000")
        outObject["prio"] = dataRecord["nmea2000:priority"]
        outObject["src"] = dataRecord["nmea2000:source_address"]
        outObject["dst"] = dataRecord["nmea2000:destination_address"]
        outObject["pgn"] = dataRecord["nmea2000:pgn"]
        outObject["description"] = pgnRecord["Description"]
        fieldsObject = {}

        for name in dataRecord.keys():
            if (name.find(':') != -1):
                continue

            value = dataRecord[name]
            units = dataRecord[name + ':Units']

            # I can't think in radians, convert those to degrees
            # convert radians to degrees
            if units == 'rad':
                value = ("%.2f" % math.degrees(value))

            if units == 'rad/s':
                value = ("%.2f" % math.degrees(value))

            if value == None:
                value = "Unknown"

            # append output 
            fieldsObject[dataRecord[name + ":LongName"]] = value

        outObject["Fields"] = fieldsObject

        # save output
        with self.__lock:
            self.__sendBuffer.append(json.dumps(outObject))
        #print(json.dumps(outObject))


#
# Dump current state (from Nmea2000State) to stdout once per second.  
# This is a useful debug class to see how state is changing.
#
class PrintState(object):
    def __init__(self, state):
        self.__state = state
        self.__timer = RepeatTimer(1, self.worker)

    def worker(self):
        print("state dump")
        unixTime = (self.__state['Time'] + (self.__state['Date'] * 86400)) - 0
        print("Time: %s" % (time.ctime(int(unixTime))))
        for v in self.__state.keys():
            print("%s: %s %s" % (v, self.__state[v], self.__state.GetUnits(v)))

#
# parse NMEA 2000 data and run it through our system
# The data format matches what is written by a Raymarine plotter running Lighthouse II
# Example record:
# Rx 478700 09 f5 03 05 f8 00 00 ff ff ff ff ff
# ignored-- header----- data-------------------
#
def parseLog():
    nmea2000state = Nmea2000State()
    #nmea0183 = Nmea0183Server(nmea2000state)
    nmealogger = NmeaLogger(nmea2000state)
    json = JsonServer()
    consumers = [ nmea2000state, json, PgnPrinter() ]
    reader = Nmea2000Reader(consumers)
    printState = PrintState(nmea2000state)

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

        print("%-3i: pgn=%-6i line=%s" % (arbitration_id.source_address, arbitration_id.pgn.value, line))

        reader.HandlePacket(arbitration_id, data)
        #time.sleep(0.01)

# parse NMEA 2000 network data from CAN bus
def parseNetwork():
    #json = JsonServer()
    bus = j1939.Bus()
    nmea2000state = Nmea2000State()
    #nmea0183 = Nmea0183Server(nmea2000state)
    nmealogger = NmeaLogger(nmea2000state)
    consumers = [ nmea2000state, PgnPrinter() ]
    reader = Nmea2000Reader(consumers)
    printState = PrintState(nmea2000state)
    try:
        #t = stopwatch.Timer()
        for msg in bus:
            #t.stop()
            #ms = int(t.elapsed * 10000)
            #sys.stdout.write(str(ms) + ' ')
            #sys.stdout.flush()
            #t = stopwatch.Timer()
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
