#!/usr/bin/python

# system modules
import math
import struct
import json
import sys
import fileinput
import abc
import time
import threading
import csv
from abc import ABCMeta
from io import StringIO
from pprint import pprint
# pip install quantities
import quantities

# local modules
from lib.RepeatTimer import RepeatTimer

#
# abstract class for a NMEA 2000 data consumer
#
class PgnConsumer(object):
    __metaclass__ = abc.ABCMeta

    #
    # pgn - the PGN related to this record
    # dataRecord - The data that is being shown in the record
    # pgnRecord - the record from pgnTable with the meta-information about this PGN
    #
    @abc.abstractmethod
    def ConsumePgn(self, pgn, dataRecord, pgnRecord):
        return

#
# Parse NMEA 2000 packets and call a handler will a full packet is received and 
# decoded
#
# This current handles standard J1939 (8 byte) and NMEA 2000 fast packets
#
class Nmea2000Reader:
    #
    # pgnTable -- the definition of the pgns from type PgnTable
    # consumers -- A list of consumers (inherited from PgnConsumer) that 
    #   consumes processed data from the bus
    #
    def __init__(self, consumers):
        self.__pgnTable = PgnTable()
        self.__packetStateTable = {}
        self.__consumers = consumers

    #
    # HandlePacket is called whenever a new data packet is found on the bus
    #
    def HandlePacket(self, arbitration_id, data):
        if arbitration_id.source_address not in self.__packetStateTable:
            self.__packetStateTable[arbitration_id.source_address] = PacketState(self.__pgnTable, arbitration_id.source_address, self.__consumers)

        self.__packetStateTable[arbitration_id.source_address].ProcessPacket(arbitration_id, data)
        
#
# PgnTable is a class that represents all of the PGNs and has data to parse them
# from a NMEA 2000 network. 
#
# The table is loaded from pgns.json and more or less matches it's format
#
class PgnTable:
    # initialize the PGN table by loading the JSON structure from disk
    def __init__(self, jsonFile='./pgns.json'):
        with open(jsonFile, 'r') as json_data:
            self.__pgnTable = json.load(json_data)
            self.__pgnTable = self.__pgnTable['PGNs']
        self.fixupPgnTable()
        #self.applyCorrections()

    # Get a single value from the table
    def __getitem__(self, key):
        return self.__pgnTable[key]

    # Does the PGN table contain the key?
    def __contains__(self, key):
        return key in self.__pgnTable

    @property
    def Nmea0183Table(self):
        return self.__nmea0183map

    # Fix the enums used for lookup tables inside the PGN Table:
    # * Change them to proper dictionaries (for some reason they are loaded from JSON as arrays of dictionaries)
    # * Compute the maximum bits used and remember that for use by decode.  Saved as EnumMask
    # * remove spaces from names
    def fixupPgnTable(self):
        # convert from list to dict
        pgnDict = {}
        for pgnRecord in self.__pgnTable:
            pgnId = pgnRecord["PGN"]
            print(pgnId)
            pgnDict[pgnId] = pgnRecord
        self.__pgnTable = pgnDict

        for pgn in self.__pgnTable:
            pgnRecord = self.__pgnTable[pgn]
            if 'Fields' in pgnRecord:
                for field in pgnRecord['Fields']:
                    if 'Name' in field and field['Name'] != None:
                        # remove spaces from field names
                        field['LongName'] = field['Name']
                        field['Name'] = field['Name'].replace(' ', '')
                    if 'EnumValues' in field:
                        newTable = {}
                        oldTable = field['EnumValues']
                        maxKey = 0
                        for row in oldTable:
                            key = row["value"]
                            v = row["name"]
                            newTable[key] = v
                            if int(key) > maxKey:
                                maxKey = int(key)
                        field[u'EnumValues'] = newTable
                        field[u'EnumMask'] = (2**(maxKey).bit_length()) - 1

    # this repairs known bugs in pgns.json
    def applyCorrections(self):
        # fix Reference in WindData.Reference to point to the right 3 bits
        self.applyCorrection(130306, 'Reference', 'BitOffset', 45)

    def applyCorrection(self, pgn, fieldName, fieldParam, newValue):
        pgnRecord = self.__pgnTable[pgn]
        for f in pgnRecord['Fields']:
            if f['Name'] == fieldName:
                f[fieldParam] = newValue

# 
# PacketState keeps track of the parsing state for multi-packet fields 
# (NMEA 2000 Fast Packet) for data coming from a given source address.
#
# When a packet is completely received it is send to decode() for processing
#
class PacketState:
    def __init__(self, pgnTable, source_address, consumers):
        self.__packetsLeft = 0
        self.__fastPacketSequence = 0
        self.__pgnTable = pgnTable
        self.__source_address = source_address
        self.__currentPgn = 0
        self.__consumers = consumers

    def int_to_bytes(self, val, num_bytes):
        num_bytes -= 1
        return [(val & (0xff << (num_bytes-pos)*8)) >> (num_bytes-pos)*8 for pos in range(num_bytes + 1)]

    # arbitration_id: CAN arbitration_id (header)
    # data: CAN data (8 bytes)
    def ProcessPacket(self, arbitration_id, data):
        # break out the fast packet support fields
        fastPacket = struct.unpack("<H", data[0:2])[0]
        sequenceCounter = (fastPacket & 0xe000) >> 13
        frameCounter = (fastPacket & 0x1f00) >> 8
        length = (fastPacket & 0xff)
        pgn = arbitration_id.pgn.value
        prio = arbitration_id.priority
        source_address = arbitration_id.source_address

        if (self.__packetsLeft > 0) and ((self.__fastPacketSequence != sequenceCounter) or (self.__currentPgn != pgn)):
            # somehow we lost a sequence, reset our internal state
            #print("PacketState-%i: lost sequence, expectedpgn = %i, nowpgn = %i fastPacketSequence = %i, sequenceCounter = %i" % (self.__source_address, self.__currentPgn, pgn, self.__fastPacketSequence, sequenceCounter))
            self.__packetsLeft = 0
            self.__currentPgn = 0
            return 0

        if (self.__packetsLeft > 0) and (self.__fastPacketSequence == sequenceCounter) and (self.__currentPgn == pgn):
            # we end up here if we are in the middle of processing a fast packet sequence
            self.__b.extend(data[1:])
            self.__packetsLeft -= 1

            # we're at the end of the packet sequence
            if (self.__packetsLeft == 0):
                self.decode(pgn, arbitration_id, self.__b)
        elif (pgn in self.__pgnTable) and (self.__pgnTable[pgn]['Length'] > 8) and length > 6:
            # new fast-packet pgn
            extraLength = max(length - 6, 0)
            self.__packetsLeft = int(math.ceil(extraLength / 7.0))
            self.__fastPacketSequence = sequenceCounter
            self.__currentPgn = pgn
            self.__b = data[2:]
        else:
            # short pgn
            self.decode(pgn, arbitration_id, data)

    #
    # parse invidual bits from a NMEA data field
    # also does endian-fixup.  There is probably a cleaner
    # way to do this
    # b -- byte array with the data
    # bitOffset -- the offset of the data to read
    # bitLength -- the number of bits to read
    # type -- The type to decode (pulled from PgnTable)
    # returns: the value
    #
    def parseOut(self, b, bitOffset, bitLength, dataType, signed):
        # variable length
        if bitLength == -1:
            startingByte = int(bitOffset / 8)
            if startingByte < len(b):
                print(dataType)
                print("variable length -- not working yet")
                print("bitOffset = %i" % bitOffset)
                data = b[startingByte:]
                pprint(data)
                print(len(b))
                print(startingByte)
                exit()

        # check for out of bounds
        if (bitOffset + bitLength > len(b) * 8):
            return 0

        #print("data[%d] = %s" % (len(b), ' '.join('%02x' % x for x in b)))

        startingByte = int(bitOffset / 8)
        numBytes = int(bitLength / 8)
        if (bitLength % 8 > 0): 
            numBytes += 1

        #print("bitOffset = %d %s" % (bitOffset, str(type(bitOffset))))
        #print("bitLength = %d %s" % (bitLength, str(type(bitLength))))
        #print("startingByte = %d %s" % (startingByte, str(type(startingByte))))
        #print("dataType = %s" % dataType)
        #print("numBytes = %d %s" % (numBytes, str(type(numBytes))))

        data = b[startingByte:startingByte + numBytes]

        #print("data[%d] = %s" % (len(data), ' '.join('%02x' % x for x in data)))

        # unpack depending on the type of length
        if (dataType == 'ASCII text'):
            # data is just the ASCII text.  Ignore translation errors
            v = data.decode('ascii', 'ignore')
        elif (dataType == 'ASCII string starting with length byte'):
            # untested! This might work?
            #length = data[0]
            #v = ''.join(map(chr, data[1:length]))
            raise NotImplementedError
        elif (numBytes == 1) and signed:
            # single byte signed int
            v = struct.unpack('<b', data)[0]
        elif (numBytes == 1) and not signed:
            # single byte signed int
            v = struct.unpack('<B', data)[0]
        elif (numBytes == 2) and signed:
            # two byte signed int
            v = struct.unpack('<h', data)[0]
        elif (numBytes == 2) and not signed:
            # two byte signed int
            v = struct.unpack('<H', data)[0]
        elif (numBytes == 3):
            # three byte signed int
            # pad with leading 0 for 3 byte numbers
            data = data + bytearray(1)
            if signed:
                v = struct.unpack('<l', data)[0]
            else:
                v = struct.unpack('<L', data)[0]
        elif (numBytes == 4) and signed:
            # four byte signed int
            v = struct.unpack('<l', data)[0]
        elif (numBytes == 4) and not signed:
            # four byte signed int
            v = struct.unpack('<L', data)[0]
        elif (numBytes == 8) and signed:
            # eight byte signed int
            v = struct.unpack('<q', data)[0]
        elif (numBytes == 8) and not signed:
            # eight byte signed int
            v = struct.unpack('<Q', data)[0]
        else:
            # something else that we haven't encountered
            raise RuntimeError('Unexpected number of bytes %d and dataType %s ' % (numBytes, dataType))

        # numbers may be contained in less than a byte, this shifts and 
        # masks as appropriate
        if isinstance(v, (int)):
            bitOffsetInByte = bitOffset % 8
            v = v >> bitOffsetInByte
            if (bitLength % 8 != 0):
                v = v & ((1 << bitLength) - 1)

        return v

    #
    # Use pgnTable (loaded from JSON "pgns.json") to decode a NMEA 2000 record
    #
    # pgn -- the pgn of the record
    # b -- byte array with the data
    # returns: human readable string of the record
    #
    def decode(self, pgn, arbitration_id, b):
        if pgn not in self.__pgnTable:
            #print("decode failed: pgn=%i" % pgn)
            return 0
        pgnRecord = self.__pgnTable[pgn]

        dataRecord = {}

        dataRecord["nmea2000:pgn"] = arbitration_id.pgn.value
        dataRecord["nmea2000:priority"] = arbitration_id.priority
        dataRecord["nmea2000:source_address"] = arbitration_id.source_address
        dataRecord["nmea2000:destination_address"] = arbitration_id.destination_address

        bitOffset = 0
        bitLength = 0

        for f in pgnRecord['Fields']:
            name = f['Name']
            if 'BitOffset' in f and 'BitLength' in f:
                bitOffset = f['BitOffset']
                bitLength = f['BitLength']
            elif 'BitLengthVariable' in f and f['BitLengthVariable']:
                bitOffset += bitLength
                bitLength = -1
            signed = f.get('Signed', False)

            # skip reserved blocks
            if name == None or name == 'Reserved' or name == 'SID':
                continue

            value = self.parseOut(b, bitOffset, bitLength, f.get('Type'), signed)

            if bitLength == -1:
                bitLength = 0
            unknownValue = (1 << (bitLength)) - 1
            if f.get('Signed') == True:
                unknownValue = unknownValue >> 1

            #print("field = %s" % name)
            #print("bitOffset = %d" % bitOffset)
            #print("bitLength = %d" % bitLength)
            #print("unknownValue = %d" % unknownValue)
            #print("value = %d" % value)

            if value == unknownValue:
                dataRecord[name + ':RawValue'] = value
                value = None
                units = None
            else:
                # resolution modifier
                if 'Resolution' in f and f['Resolution'] != 1:
                    resolution = float(f['Resolution'])
                    value = value * resolution

                # type modifier, we use it to find lookup tables
                if 'Type' in f:
                    type = f['Type']
                else:
                    type = 'scalar'

                dataRecord[name + ':RawValue'] = value

                # units modifier, used to decorate output
                if 'Units' in f and f['Units'] != None:
                    units = f['Units']
                else:
                    units = ''

                # expand lookup table
                if (type == 'Lookup table') and ('EnumValues' in f):
                    v = value & f['EnumMask']
                    value = '"%d"' % v
                    enumValues = f['EnumValues']
                    if (str(v) in enumValues):
                        value = enumValues[str(v)]

            dataRecord[name] = value
            dataRecord[name + ':Units'] = units
            dataRecord[name + ':LongName'] = f['LongName']

        for consumer in self.__consumers:
            consumer.ConsumePgn(pgn, dataRecord, pgnRecord)

# 
# This is a simple NMEA 2000 data consumer that prints all input
# records to stdout
#
class PgnPrinter(PgnConsumer):
    # 
    # print a NMEA2000 record
    #
    # pgn - the PGN related to this record
    # dataRecord - The data that is being shown in the record
    # pgnRecord - the record from pgnTable with the meta-information about this PGN
    #
    def ConsumePgn(self, pgn, dataRecord, pgnRecord):
        outFields = []
        description = pgnRecord['Description']
        for name in dataRecord.keys():
            if (name.find(':') != -1):
                continue
            value = dataRecord[name]
            units = dataRecord[name + ':Units']

            # I can't think in radians, convert those to degrees
            # convert radians to degrees
            if units == 'rad':
                value = ("%.2f" % math.degrees(value))
                units = 'deg'

            if units == 'rad/s':
                value = ("%.2f" % math.degrees(value))
                units = 'deg/s'

            if units == None:
                units = ''

            if units != '':
                units = ' ' + units

            # append output 
            outFields.append("%s=(%s%s)" % (name, value, units))

        # print output
        print("source=%s: pgn=%s(%i): values=%s\n" % (str(dataRecord["nmea2000:source_address"]), description, pgn, ' '.join(outFields[0:])))

#
# This class keeps track of all boat state coming in via NMEA 2000. 
# At it's core is a list of PGNs to consume and what variables to
# consume from them.  The most recent version of each is kept in a
# local cache that can then be consumed by other classes (such as the
# NMEA 0183 output or the data logger).
#
class Nmea2000State(PgnConsumer):
    # Initialize the class
    def __init__(self):
        # TODO -- single instance this between here and Nmea2000Reader
        self.__pgnTable = PgnTable()

        #
        # This is a map of PGNs to data that should be kept from them.
        # The key in the map is the PGN to notice
        # The data in the map is the list of data values to store.  
        # The value is XXX,YYY, where XXX is the name of the variable
        # in the PGN data, and YYY is the name of the variable in the
        # state map.  If ,YYY is missing then the same name is used in
        # both
        #
        self.__map = {
            127250: [ 'Heading' ],
            128259: [ 'SpeedWaterReferenced,SpeedThroughWater' ],
            128267: [ 'Depth', 'Offset,DepthOffset' ],
            129025: [ 'Longitude', 'Latitude' ],
            129026: [ 'SOG', 'COG' ],
            130306: [ 'WindSpeed', 'WindAngle', 'Reference,WindReference' ],
            129033: [ 'Date', 'Time' ],
        }

        # 
        # __state is what keeps track of our variables
        #
        # There is one entry per variable stored that contains both
        # the value.  There is a paired variable in __units that
        # contains the units for that variable.  The units don't
        # change over the lifetime of this object.
        #
        # If the value is not known then the map will contain the
        # entry None.
        #
        self.__state = {} 
        self.__units = {}

        self.__lock = threading.Lock()

        for pgn in self.__map.keys():
            for v in self.__map[pgn]:
                i = v.find(',')
                if (i == -1):
                    pgnName = v
                    stateName = v
                else:
                    pgnName = v[0:i]
                    stateName = v[i+1:]
                i += 1
                self.__state[stateName] = None
                self.__units[stateName] = self.FindUnitsForField(pgn, pgnName)

    # 
    # Find the units for a given field in a pgn
    #
    def FindUnitsForField(self, pgn, field):
        fields = self.__pgnTable[pgn]
        for f in fields['Fields']:
            if (f['Name'] == field and 'Units' in f):
                return f['Units']
            elif (f['Name'] == field):
                return ''
        return ''

    #
    # Update __state with data from this PGN
    # 
    # pgn - the PGN related to this record
    # dataRecord - The data that is being shown in the record
    # pgnRecord - the record from pgnTable with the meta-information about this PGN (ignored)
    #
    def ConsumePgn(self, pgn, dataRecord, pgnRecord):
        if pgn not in self.__map:
            return None

        for v in self.__map[pgn]:
            i = v.find(',')
            if i == -1:
                pgnName = v
                fieldName = v
            else:
                pgnName = v[0:i]
                fieldName = v[i+1:]

            with self.__lock:
                self.__state[fieldName] = dataRecord[pgnName]

    # 
    # Return the value of a state item
    #
    def __getitem__(self, k):
        with self.__lock:
            return self.__state[k]

    # 
    # Get the units for a state item
    #
    def GetUnits(self, k):
        return self.__units[k]

    #
    # Return the list of known keys
    #
    def keys(self):
        return self.__state.keys()

#
# Log data from the Nmea2000State object to a log file
#
class NmeaLogger(object):
    #
    # state -- a Nmea2000State object that is collecting state from the bus
    #
    def __init__(self, state):
        self.__state = state
        self.__timer = RepeatTimer(1, self.worker)
        self.__filename = "%s.csv" % time.strftime('saildata/saildata-%Y-%m-%d-%H-%M')
        self.__file = open(self.__filename, 'wb')
        self.__csv = csv.writer(self.__file) #, dialect='excel2')
        self.__writeheader = True
        self.__keys = [ 
            'Heading', 
            'SpeedThroughWater', 
            'SOG', 
            'COG',
            'WindSpeed', 
            'WindAngle', 
            'WindReference',
            'Depth', 
            'DepthOffset',
            'Longitude', 
            'Latitude', ]

    #
    # This worker method is called once per second to log the state data
    #
    def worker(self):
        # write the header if there isn't already one
        # we do this on the first write instead of during __init__ to pick
        # up the units
        if self.__writeheader:
            self.__writeheader = False;
            header = []
            for k in self.__keys:
                header.append("%s (%s)" % (k, self.__state.GetUnits(k)))
            # write out the header
            self.__csv.writerow(header.encode("utf-8"))

        values = []
        for k in self.__keys:
            values.append(self.__state[k])
        self.__csv.writerow(values.encode("utf-8"))
