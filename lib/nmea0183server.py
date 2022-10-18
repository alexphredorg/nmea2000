#!/usr/bin/python

import time
import quantities
from lib.network import BroadcastServer

#
# Dump current state as NMEA 0183 output once per second
#
class Nmea0183Server(object):
    def __init__(self, state, port=10110, interval=1):
        # This list is what defines the output.  Substitution from 
        # Nmea2000State is done with the following parser:
        # {format,variable,units}
        # * variable is the variable name in Nmea2000State
        # * format is a python format string
        # * units is output units to use, this is translated from the
        #   units used in the state map
        # The leading $ and checksum is added to the output
        self.__output = [
                'SDDPT,{%.1f,Depth,m},{%.1f,DepthOffset,m}',
                'VWVHW,,,,,{%0.1f,SpeedThroughWater,knots},N,{%0.1f,SpeedThroughWater,km/h},K',
                'IIMWV,{%.1f,WindAngle,deg},R,{%.1f,WindSpeed,knots},N,A',
            ]

        self.__server = BroadcastServer(port, interval, self.__Transmit, self.__Connect)

        self.__state = state
        self.__clientCount = 0

    # 
    # __Connect is called by BroadcastServer whenever the number of connected
    # clients has changed
    #
    def __Connect(self, clientCount):
        self.__clientCount = clientCount

    #
    # This is the periodic timer function which dumps all state through
    # the NMEA 0183 list defined above
    #
    def __Transmit(self):
        output = ""

        # don't do anything if there is no one to talk to
        if self.__clientCount == 0:
            return output

        for nmeastr in self.__output:
            # do variable substitution on the nmea0183 string
            startSub = nmeastr.find("{")
            while (startSub != -1):
                # locate and parse the substitution
                endSub = nmeastr.find("}", startSub + 1)
                lookup = nmeastr[startSub + 1:endSub]
                parts = lookup.split(",")
                format = parts[0]
                variable = parts[1]
                outputUnits = None
                if len(parts) > 2:
                    outputUnits = parts[2]
                value = self.__state[variable]

                # do unit conversion if necessary
                if (outputUnits != None):
                    inputUnits = self.__state.GetUnits(variable)
                    v = quantities.Quantity(value, inputUnits)
                    value = v.rescale(outputUnits)

                # build the resulting output using our value and format
                sub = format % value

                # do the substitution
                nmeastr = nmeastr[0:startSub] + sub + nmeastr[endSub + 1:]

                # locate the next substitution
                startSub = nmeastr.find("{")

            # compute the checksum
            checksum = 0
            for c in str(nmeastr):
                checksum ^= ord(c)

            # compose the final string
            nmeastr = "$%s*%02x\r\n" % (nmeastr, checksum)
            output += nmeastr;

        return output

