# arGeoDetector
Amateur Radio utility for converting GPS coordinates to grid square and county or independent city in realtime.

# Objective
The objective of arGeoDetector is to provide real time location telemetry to the operator during mobile contesting operations.  Never again get confused by unmarked county or city lines.  arGeoDetector is completely standalone and is not dependent on an internet connection.  The only hardware requirement is an NMEA compatible GPS dongle that presents itself as a serial port.  I have only been able to test with a few pieces of hardware, so if yours isn't working, please let me know.

# Maidenhead Grid Square
arGeoDetector currently provides a 6 character grid square.

# County or Independent City
arGeoDetector is able to parse country/city boundary files from NO5W availble here http://no5w.com/CQxCountyOverlays-DL.php

# Usage
Usage: arGeoDetector.py [options]

Options:
  -h, --help            show this help message and exit
  -p PORT, --port=PORT  GPS serial port
  -r RATE, --rate=RATE  GPS serial rate
  -f NMEAFILE, --file=NMEAFILE
                        NMEA data file
  -b BNDFILE, --boundary=BNDFILE
                        Geographic boundary kml data file
  -l LOGFILE, --log=LOGFILE
                        Log filename root, creates filename.log and
                        filename.nmea
  -v, --verbose         Verbose output data

# Testing
NMEA routes can be generated from nmeagen.org for testing purposes.  Save the output and pass it to arGeoDetector with the -f option.

# Logging
arGeoDetector will log your session and produce two log files.  One with text output from the application and one with GPS NMEA data captured from the GPS receiver.  

# Examples

./arGeoDetector.py -b OverlayVirginiaRev4.kml -p COM1 -l mylog
./arGeoDetector.py -b OverlayVirginiaRev4.kml -f mylog.nmea

