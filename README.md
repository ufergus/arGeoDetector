# arGeoDetector
Amateur Radio utility for converting GPS coordinates to grid square and county or independent city in realtime.
- See about_arGeoDetector.pdf for quick presentation and screenshots.

# Objective
The objective of arGeoDetector is to provide real time location telemetry to the operator during mobile contesting operations.  Never again get confused by unmarked county or city lines.  arGeoDetector is completely standalone and is not dependent on an internet connection.  The only hardware requirement is an NMEA compatible GPS dongle that presents itself as a serial port.  I have only been able to test with a few pieces of hardware, so if yours isn't working, please let me know.

# Maidenhead Grid Square
arGeoDetector currently provides a 6 character grid square.

# County or Independent City
arGeoDetector is able to parse country/city boundary files from NO5W availble [here](http://no5w.com/CQxCountyOverlays-DL.php)

# Installation

## Windows
64-bit Windows 10 binaries provided in the release section

## Linux
No prepared packages currently available for linux, please install the prerequisite packages using your default package manager, clone the repository and execute arGeoDetector.py

### Prerequisites
- Python3
- PySerial
- wxPython
- AppDirs
- simpleaudio

# Testing
NMEA routes can be generated from nmeagen.org for testing purposes.  Save the output and pass it to arGeoDetector with the Tool->Replay option.

# Logging
arGeoDetector will log your session and produce two log files.  One with text output from the application and one with GPS NMEA data captured from the GPS receiver. Location of log files is shown in the About dialog. 

# Examples
```
python arGeoDetector.py
```

