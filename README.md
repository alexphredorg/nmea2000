# nmea2000

This is a haphazard collection of scripts that I've used to parse and send NMEA2000 data.

What's here:
* lib/nema2000.py: The core library with functions to parse PGNs and send the data to a set of consumers
* lib/network.py: This was for the state server part of the server script.  It's honestly probably junk.
* lib/nmea0183server.py: Also junk
* ParseLog.py: Parses a Raymarine or socketcan log of NMEA2000 data and prints what is in it
* server.py: A server which is meant to log interesting statistics to a file, expose them to the local network, and print them.  Not finished (and likely never will be).
* python-j1939: This is a clone of a library used to help with parsing.  Lots of logging is commented out.  Source: https://github.com/milhead2/python-j1939
* updatepgns.sh: This will download the PGN description file from canboat and modify it to be read by these scripts
* test-input/*: Random logs from my boat
* test-output.txt: The output from running on nmea2000-2.log

Dependencies:
# pip install python-can==3.3.2
# pip install quantities
# cd python-j1939
# python setup.py install
# cd ..