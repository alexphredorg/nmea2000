#!/usr/bin/python
from __future__ import print_function

import can
import struct
import time
import math
import sys

from can.interfaces.interface import *
from can.protocols import j1939

# report depth in meters
# depth: depth in meters, resolution 0.01
def depth(bus, depth):
    depth = int(depth * 100)
    data = bytearray(8)
    # SID(1), depth(4)
    struct.pack_into("@ixxx", data, 1, depth)
    data[0] = 0xff
    print("%02x %02x %02x %02x %02x %02x %02x %02x" %(data[0], data[1], data[2], data[3], data[4], data[5], data[6], data[7]))
    arbitration_id = j1939.ArbitrationID(pgn=128267)
    msg = j1939.PDU(arbitration_id=arbitration_id, data=data)
    bus.send(msg)

# report wind speed and direction
# speed: speed in m/s, resolution 0.01
# angle: angle in degrees
def wind(bus, speed, angle):
    speed = int(speed * 100)
    angle = int(math.radians(angle) * 10000)
    print ("angle is %.2f" % (angle * 0.0001))
    data = bytearray(8)
    # SID(1), speed(2), angle(2), reference(0x40=boat)
    struct.pack_into("@HH", data, 1, speed, angle)
    data[0] = 255
    data[5] = 0xfa
    data[6] = 255
    data[7] = 255
    print("%02x %02x %02x %02x %02x %02x %02x %02x" %(data[0], data[1], data[2], data[3], data[4], data[5], data[6], data[7]))
    arbitration_id = j1939.ArbitrationID(pgn=130306)
    msg = j1939.PDU(arbitration_id=arbitration_id, data=data)
    bus.send(msg)
    
def main():
    bus = j1939.Bus()
    depth(bus, 25)
    for i in range(0,360):
        wind(bus, 7.25, i)
        time.sleep(0.1)
    print("Message sent")
    bus.shutdown() 

if __name__ == "__main__":
    main()
