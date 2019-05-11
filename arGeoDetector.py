#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created on Wed Mar 20 19:43:40 2019

@author: Richard Ferguson K3FRG
         k3frg@arrl.net
"""

import os
import sys
import math
import re
import time
import datetime
from threading import Thread
#import io
from optparse import OptionParser
import logging
import logging.handlers
import serial
import xml.etree.ElementTree
import wx
import wx.html
import webbrowser
from enum import Enum

from appdirs import AppDirs 
import configparser

# Courtesy of Chris Liechti <cliechti@gmx.net> (C) 2001-2015 
from wxSerialConfigDialog import SerialConfigDialog

class geoMsg(Enum):
    GRID = 1
    CNTY = 2
    STAT = 3
    TIME = 4
    GPS  = 5
    NOTIF= 6

class geoBoundary():
    def __init__(self, name, abbr):
        self.name = name
        self.abbr = abbr
        self.coords = []
        
    def addCoord(self, xy):
        # xy is a (x,y) tuple
        self.coords.append(xy)
    
    def wrapCoord(self):
        self.coords.append(self.coords[0])
    
    def coords2mxb(self, c1,c2):
        # solve for line equation
        (c1x,c1y) = c1
        (c2x,c2y) = c2
    
        m = (c2y-c1y) / (c2x-c1x)
        b = c1y - m*c1x
        #print "m>%f b>%f" % (m, b)
        return (m,b)
      
    def contains(self, xy):
        (x,y) = xy

        test_cnt = 0
        coord_cnt = 0

        for i in range(len(self.coords)-1):
            # Test against sequential coordinates
            (cx1,cy1) = self.coords[i]
            (cx2,cy2) = self.coords[i+1]
            # the NMEA X coordinate must fall between the two test coords
            if x == cx1:
                if cy1 < y:
                    test_cnt -= 1
                else:
                    test_cnt += 1
                coord_cnt +=1
            
            elif x == cx2:
                if cy2 < y:
                    test_cnt -= 1
                else:
                    test_cnt += 1
                coord_cnt +=1
                
            elif x >= cx1 and x <= cx2 or x >= cx2 and x <= cx1:
                # Solve for line equation y=mx+b
                (m,b) = self.coords2mxb(self.coords[i],self.coords[i+1])
                # Calculate Y coordinate from equation
                ycalc = m*x+b
                
                # Compare calculated Y vs NMEA Y
                if ycalc < y:
                    test_cnt -= 1
                else:
                    test_cnt += 1
                    
                # Record how many coordinate pairs satisfy the test
                coord_cnt += 1
                
   #     print("%s: %d %d" % (self.abbr, test_cnt, coord_cnt))        
        if not ((coord_cnt - abs(test_cnt)) % 4 == 0):       
            #print("TRUE> %s: %d %d" % (self.abbr, test_cnt, coord_cnt))        
            return True
        else:
            return False
    
class arGeoDetector(Thread):
    def __init__(self, serial, cb, log=0, nmea=0):
        Thread.__init__(self)
        
        self.boundaries = []
        self.mode = 0 # 0 = serial, 1 = file
        self.verbose = False
        
        self.log_main = log
        self.log_nmea = nmea
        
        self.last_grid = ""
        self.last_qth = ""
        self.last_datetime = datetime.datetime.now(datetime.timezone.utc)
         
        self.gps_lock = False
        self.gps_datetime = datetime.datetime.now(datetime.timezone.utc)

        self.bnd_warn = 0
        
        self._do_exit = 0
    
        self.com = serial
        self.msgCB = cb
        
    def loadBoundaries(self, filename):
        self.boundaries = []
        
        # Load Kml file into string so I can remove the 
        # xmlns="http://earth.google.com/kml/2.1" string
        # from the <kml> tag.  I don't know why but this 
        # breaks the subsequent element tree?????
        
        xmlstr = ""
        try:
            kmlin = open(filename)
            for line in kmlin.readlines():
                xmlstr += line.replace(" xmlns=\"http://earth.google.com/kml/2.1\"","")
        except:
            print ("Error reading boundary file [%s]!" % filename)
            quit(1)
        
        e = xml.etree.ElementTree.fromstring(xmlstr)
        #e = xml.etree.ElementTree.parse(filename).getroot()

        for xplacemark in e[0].iter('Placemark'):
            for xname in xplacemark.iter('name'):
                # extract name info
                # Form: 'Fauquier=FAU 1'
                # only process '1' entries
                m = re.search('(\w*)=(\w\w\w) 1', xname.text)
                if (m): # If match succeeds
                    name = m.group(1)
                    abbr = m.group(2)
                    self.log ("Loading %s(%s)" % (abbr, name))
                    # Create new boundary object
                    bnd = geoBoundary(name, abbr)
                    
                    # Add coordinates to boundary object
                    # Form: '-75.87614423,37.55153989'
                    for xcoords in xplacemark.iter('coordinates'):
                        lines = xcoords.text.strip().split('\n')
                        for line in lines:
                            sline = line.strip() # remove whitespace
                            xy = sline.split(',')
                            #print ("X> %s, Y> %s" % (xy[0], xy[1]))
                            # Add coordinate to object
                            bnd.addCoord((float(xy[0]), float(xy[1])))
                            
                        # Wrap coordinate list by copying entry 0 to the end
                        bnd.wrapCoord()
                    
                    self.boundaries.append(bnd)
        self.log("Boundary file loaded")
    
    def enableLog(self, filename):
        try:
            self.log_nmea = open("%s.nmea" % filename, "w")
        except:
            print ("Error:  can not open nmea log file [%s.nmea]" % filename)
            quit(1)
        
        try:
            self.log_caic = open("%s.log" % filename, "w")
        except:
            print ("Error:  can not open caic log file [%s.log]" % filename)
            quit(1)
                
    def closeLog(self):
        self.log_nmea.close()
        self.log_caic.close()
    
    def log(self, logstr, status=1):
        if self.log_main:
            self.log_main.info(logstr)
        
        if status:
            self.msgCB((geoMsg.STAT,logstr))

    def logNMEA(self, logstr):
        if self.log_nmea:
            self.log_nmea.info(logstr)
           
    def wdTick(self):
        self.wd = datetime.datetime.now()
        
    def wdCheck(self, timeout=15):
        if datetime.datetime.now() - self.wd > datetime.timedelta(minutes=timeout):
            self._do_exit = 1
            
    def clirun(self):    
        parser = OptionParser()
        parser.add_option("-p", "--port", dest="port",
                          help="GPS serial port")
        parser.add_option("-r", "--rate", dest="rate",type="int", default=4800,
                          help="GPS serial rate")
        parser.add_option("-f", "--file", dest="nmeafile",
                          help="NMEA data file")
        parser.add_option("-b", "--boundary", dest="bndfile",
                          help="Geographic boundary kml data file")
        parser.add_option("-l", "--log", dest="logfile",
                          help="Log filename root, creates filename.log and filename.nmea")
        parser.add_option("-v", "--verbose", dest="verbose",
                          action="store_true", default=False,
                          help="Verbose output data")
        
        (opts, args) = parser.parse_args()
        
        if opts.logfile:
            self.enableLog(opts.logfile)
            
        if opts.verbose:
            self.verbose = True
        
        if opts.bndfile:
            if not os.path.isfile(opts.bndfile):
                print ("Error: geographic boundary file not found [%s]\n" % opts.bndfile)
                parser.print_help()
                return
            else:  
                self.loadBoundaries(opts.bndfile)
        else:
            print("Error: geographic boundary file not specified\n")
            parser.print_help()
            return
        
        if opts.port:
            pass
            #self.readCOM(opts.port, opts.rate)
                
        elif opts.nmeafile:
            self.log ("Opening NMEA file %s\n" % opts.nmeafile, 1)
            if not os.path.isfile(opts.nmeafile):
                print ("Error: NMEA file not found [%s]\n" % opts.nmeafile)
                parser.print_help()
                return
            else:
                self.readFile(opts.nmeafile)           
        else:
            print ("Error:  Port or NMEA File not specified\n")
            parser.print_help()            

    def stop(self):
        self._do_exit = 1
        
    def run(self):
        # init main loop watchdog
        self.wdTick()
        
        # init state variable
        # 0 = open port
        # 1 = read data
        st = 0
        while not self._do_exit:
            time.sleep(1)
            # open serial port, loop if it doesn't exist yet
            self.log("Opening serial port...")
            while st == 0 and not self._do_exit:
                #print ("STATE0")
                try:
                    if not self.com.is_open:
#                        print("opening com")
                        self.com.open()
#                        print("%s %s" %(res,self.com.is_open))
                    st = 1
                    self.wdTick()
                except serial.serialutil.SerialException:
                    time.sleep(1)
                    self.wdCheck(5)
                except KeyboardInterrupt:
                    self._do_exit = 1
                                      
            # wait for initial gps data
            self.log("Waiting for initial GPS data...")
            while st == 1 and not  self._do_exit:
                #print ("STATE1")
                if self.com.in_waiting > 0:
                    st = 2
                    self.wdTick()
                else:
                    time.sleep(1)
                    self.wdCheck()
            
            # wait for time/date sync
            self.log("Waiting for Date/Time sync...")
            while st == 2 and not self._do_exit:
                try:
                    time.sleep(1)
                    buf = self.com.readline().decode()
                    self.wdTick()
                except serial.serialutil.SerialException:
                    self.msgCB((geoMsg.GRID,"-"))
                    self.msgCB((geoMsg.CNTY,("-","-")))
                    self.log("com error")
                    st = 0
                    self.com.close()
                    self.wdCheck()
                except KeyboardInterrupt:
                    self._do_exit = 1

                if buf:
                    self.logNMEA(buf)
                    
                    # process GPRMC lines for date/time        
                    m = re.search('^\$GPRMC', buf)
                    if (m):
                        try:
                            self.updateNmeaRmcDateTime(buf)
                        except ValueError:
                            continue
                        st = 3
                        self.log("Date/Time synced!")

            # process general gps data
            self.log("Processing GPS data...")
            while st == 3 and not self._do_exit:
                try:
                    #time.sleep(1)
                    buf = self.com.readline().decode()
                    self.wdTick()
                except serial.serialutil.SerialException:
                    self.msgCB((geoMsg.GRID,"-"))
                    self.msgCB((geoMsg.CNTY,("-","-")))
                    self.log("com error")
                    st = 0
                    self.com.close()
                    self.wdCheck()
                except KeyboardInterrupt:
                    self._do_exit = 1

                if buf:
                    self.logNMEA(buf)

                    # process GPRMC lines for date/time        
                    m = re.search('^\$GPRMC', buf)
                    if (m):
                        try:
                            self.updateNmeaRmcDateTime(buf)
                        except ValueError:
                            pass
                        
                    # process GPGGA lines for location
                    m = re.search('^\$GPGGA', buf)
                    if (m):
                        changed = 0
                        # Update time
                        self.updateNmeaGgaTime(buf)
                        
                        # Extract decimal and find county/city
                        try:
                            xy = self.getNmeaGgaCoords(buf)
                        except ValueError:
                            continue
                        
                        grid = self.calcGridSquare(xy)
                        self.msgCB((geoMsg.GRID,grid))
                        if self.last_grid != grid:
                            self.last_grid = grid
                            changed = 1
                        
                        qth = self.findCAIC(xy)
                        self.msgCB((geoMsg.CNTY,(qth.name, qth.abbr)))
                        if self.last_qth != qth.abbr:
                            # New county/city detected
                            self.last_qth = qth.abbr
                            changed = 1
                        
                        if changed: # or (self.gps_datetime - self.last_datetime) >= datetime.timedelta(seconds=30):
                            self.msgCB((geoMsg.NOTIF, "Location Updated!"))
                            self.last_datetime = self.gps_datetime
                            self.log("%s %s(%s)" % (grid, qth.name, qth.abbr))
                
    def readFile(self, filename):
        with open(filename) as fp:
            for buf in fp:
                # process GPRMC lines for date/time        
                m = re.search('^\$GPRMC', buf)
                if (m):
                    try:
                        self.updateNmeaRmcDateTime(buf)
                    except ValueError:
                        pass
                # process GPGGA lines
                m = re.search('^\$GPGGA', buf)
                if (m):
                    try:
                        xy = self.getNmeaGgaCoords(buf)
                    except ValueError:
                        continue
                    grid = self.calcGridSquare(xy)
                    qth = self.findCAIC(xy)
                    self.log("%s %s(%s)" % (grid, qth.name, qth.abbr),1)
            
    # Sync datetime on RMC strings
    def updateNmeaRmcDateTime(self, nmea_str):
        #$GPRMC,154007.00,A,3835.17128,N,07745.57692,W,0.070,,220319,,,A*67
        nmea_fields = nmea_str.split(',')
        if not nmea_fields[1][:2]:
            raise ValueError("RMC record does not contain valid date and time")
        h = int(nmea_fields[1][:2])
        m = int(nmea_fields[1][2:4])
        s = int(nmea_fields[1][4:6])
        D = int(nmea_fields[9][:2])
        M = int(nmea_fields[9][2:4])
        Y = 2000 + int(nmea_fields[9][4:6])
        self.gps_datetime = datetime.datetime(Y,M,D,h,m,s,tzinfo=datetime.timezone.utc)
        self.gps_lock = True
        self.msgCB((geoMsg.TIME, self.gps_datetime.strftime("%Y/%m/%d %H:%M:%S %Z")))
        
    # Sync location on GGA strings
    def updateNmeaGgaTime(self, nmea_str):
        # Form: $GPGGA,002852.00,3835.14680,N,07745.58318,W,1,03,5.60,127.9,M,-34.5,M,,*61
        nmea_fields = nmea_str.split(',')
        if not nmea_fields[1][:2]:
            raise ValueError("GGA record does not contain valid time")
        h = int(nmea_fields[1][:2])
        m = int(nmea_fields[1][2:4])
        s = int(nmea_fields[1][4:6])
        self.gps_datetime.replace(hour=h, minute=m, second=s)
        self.msgCB((geoMsg.TIME, self.gps_datetime.strftime("%Y/%m/%d %H:%M:%S %Z")))
    
    def getNmeaGgaCoords(self, nmea_str):
        # Form: $GPGGA,002852.00,3835.14680,N,07745.58318,W,1,03,5.60,127.9,M,-34.5,M,,*61
        nmea_fields = nmea_str.split(',')
        if not nmea_fields[2]:
            raise ValueError("GGA record does not contain valid coordinates")
             #           return (0,0)
        
        nmea_y = nmea_fields[2]
        nmea_yd = nmea_fields[3]
        nmea_x = nmea_fields[4]
        nmea_xd = nmea_fields[5]
        
        y = float(nmea_y[0:2]) + (float(nmea_y[2:])/60.0)
        if nmea_yd == 'S':
            y = 0 - y
        
        x = float(nmea_x[0:3]) + (float(nmea_x[3:])/60.0)
        if nmea_xd == 'W':
            x = 0 - x
        
        self.msgCB((geoMsg.GPS, "%s%s  %s%s" % (nmea_y,nmea_yd,nmea_x,nmea_xd)))
#        print ("NMEA(LON:%f,LAT:%f) " % (x, y), end='')
        return (x,y)
    
    def findCAIC(self, xy):
        (nx,ny) = xy
        
        # return if bogus data
        if nx == 0 and ny == 0:
            return
        
        qth_list = []
        for bnd in self.boundaries:
            if bnd.contains(xy):
                qth_list.append(bnd)
        
        # If more than one boundaries match, solve for correct boundary
        # 1) city and county, find city in county
        # 2) county/county overlap, just pick one
        qth = False
        if len(qth_list) == 1:
            qth = qth_list[0]
        elif len(qth_list) > 1:
            for i in range(0,len(qth_list)):
                for j in range(0, len(qth_list)):
                    if i != j:
                        #print ("%s vs %s" % (qth_list[i].abbr, qth_list[j].abbr))
                        c = qth_list[j].coords[0]
                        if not qth_list[i].contains(c):
                            qth = qth_list[i]
        else:
            if self.bnd_warn == 0:
                print ("Warning: coordinate did not match boundary file")
                self.bnd_warn = 1
            return  geoBoundary("Unknown", "UNK")

        if not qth:
            qth = qth_list[0]
            
        self.bnd_warn = 0
        return qth
            
        #print ("QTH> %s" % (qth.abbr))

    def calcGridSquare(self, xy):
        (nx, ny) = xy
        
        # move origin to bottom left of the world 
        nx += 180
        ny += 90
        
        # field is 20x10 degree rect
        xf = math.floor(nx / 20)
        yf = math.floor(ny / 10)
        
        # convert to ascii capitals A-R
        xfc = str(chr(65 + xf))
        yfc = str(chr(65 + yf))
        
        # square is 2x1 degree rect
        xs = math.floor((nx-(xf*20)) / 2)
        ys = math.floor((ny-(yf*10)) / 1)
        
        # convert to ascii numbers 0-9
        xsc = str(xs)
        ysc = str(ys)

        # subsquare is (2/24)x(1/24) degree rect
        xss = math.floor((nx-(xf*20)-(xs*2)) / (2/24))
        yss = math.floor((ny-(yf*10)-(ys*1)) / (1/24))

        # convert to ascii capitals A-R
        xssc = str(chr(97 + xss))
        yssc = str(chr(97 + yss))

        return ("%s%s%s%s%s%s" % (xfc, yfc, xsc, ysc,xssc,yssc))

class geoHTML(wx.html.HtmlWindow):
     def OnLinkClicked(self, link):
         webbrowser.open(link.GetHref())

class geoAboutDialog(wx.Frame):
    def __init__(self, parent):
        self.parent= parent
        wx.Frame.__init__(self, parent, wx.ID_ANY, title="About", size=(500,300))
        html = geoHTML(self)
        html.SetPage(
            "<h2>About arGeoDetector 0.2</h2>"
            "<p><i>(C) 2019 Rich Ferguson, K3FRG</i></p>"
            "<P>arGeoDetector is a standalone application for assisting with "
            "mobile operators participating in state QSO parties."
            '<p><a href="https://github.com/ufergus/arGeoDetector">Source Code</a></p>'
            "<p><b>Logs:</b><br>"
            "{}<br>{}</p>".format(self.parent.LogFile, self.parent.NMEAFile)
            )

class geoFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, title="arGeoDetector", size=(500,150))
        
        self.AppDirs = AppDirs("arGeoDetector", "K3FRG")
        self.SettingsFile = ("{}{}config.txt".format(self.AppDirs.user_config_dir,os.sep))
        self.LogFile = ("{}{}log.txt".format(self.AppDirs.user_config_dir,os.sep))
        self.NMEAFile = ("{}{}nmea.txt".format(self.AppDirs.user_config_dir,os.sep))      
        
        self.config = configparser.ConfigParser()
        self.ReadSettings()
        
        self.serial = serial.Serial(baudrate=4800, timeout=1)
        
        self.InitLogs()
        
        self.geoDet = arGeoDetector(self.serial, self.GeoDetCB, self.LogMain, self.LogNMEA)
        self.geo_grid = ""
        self.geo_cnty = ""
        
        self.CreateFonts()
        self.CreateStatusBar()
        self.CreateMenus()
        self.CreateControls()
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        
        self.InitGUI()
        self.Show(True)
        
    def InitLogs(self):
        # Main log
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        handler = logging.handlers.RotatingFileHandler(self.LogFile,maxBytes=1024*1024, backupCount=5)
        handler.setFormatter(formatter)
        
        consoleHandler = logging.StreamHandler(sys.stdout)
        consoleHandler.setFormatter(formatter)
        
        self.LogMain = logging.getLogger("main")
        self.LogMain.setLevel(logging.INFO)
        self.LogMain.addHandler(handler)
        self.LogMain.addHandler(consoleHandler)
        
        # NMEA log
        formatter = logging.Formatter('%(message)s')
        handler = logging.FileHandler(self.NMEAFile)        
        handler.setFormatter(formatter)
    
        self.LogNMEA = logging.getLogger("nmea")
        self.LogNMEA.setLevel(logging.INFO)
        self.LogNMEA.addHandler(handler)
        
    def ReadSettings(self):
        self.config.read(self.SettingsFile)
        
    def WriteSettings(self):
        os.makedirs(self.AppDirs.user_config_dir, exist_ok=True)
        with open(self.SettingsFile, 'w') as configfile:
            self.config.write(configfile)

    def OpenSerialPort(self):
        try:
            self.serial.open()
            self.SetStatusText("Serial port opened")
            self.geoDet.start()
            
        except serial.serialutil.SerialException:
            self.SetStatusText("Serial port failed!")
            # FIXME
    
    def CloseSerialPort(self):
        if self.serial.is_open:
            self.serial.close()

    def InitGUI(self):
        self.stat_time = ""
        self.stat_gps = ""
        try:
            port = self.config.get('SERIAL','port')
            rate = self.config.get('SERIAL','rate')
            self.serial.port = port
            self.serial.baudrate = rate
            self.OpenSerialPort()
            
        except configparser.NoSectionError:
            self.SetStatusText("Select serial port!")
        
        try:
            bnd = self.config.get('BOUNDARY','file')
            self.geoDet.loadBoundaries(bnd)
        except configparser.NoSectionError:
            pass
            #self.txtCnty.SetLabel("No Boundaries")

        icon = wx.Icon()
        icon.CopyFromBitmap(wx.Bitmap("arGeoDetector.ico", wx.BITMAP_TYPE_ANY))
        self.SetIcon(icon)

    def CreateFonts(self):
        self.h1_font = wx.Font(18, wx.MODERN, wx.NORMAL, wx.BOLD)
        self.h2_font = wx.Font(12, wx.MODERN, wx.NORMAL, wx.BOLD)
        
    def CreateMenus(self):
        filemenu= wx.Menu()
        self.menuSerial = filemenu.Append(wx.ID_ANY, "Open &Serial Port"," Open serial port to GPS device")
        self.menuBndry = filemenu.Append(wx.ID_ANY, "Open &Boundary File"," Open KML state boundary file")
        filemenu.AppendSeparator()
        self.menuExit = filemenu.Append(wx.ID_EXIT,"E&xit"," Terminate arGeoDetector")
  
        self.Bind(wx.EVT_MENU, self.OnOpenSerialPort, self.menuSerial)
        self.Bind(wx.EVT_MENU, self.OnOpenBoundaryFile, self.menuBndry)
        self.Bind(wx.EVT_MENU, self.OnClose, self.menuExit)
    
        editmenu = wx.Menu()
        self.menuCopyGrid = editmenu.Append(wx.ID_ANY, "Copy &Grid Square\tCtrl+G"," Copy grid square to clipboard")
        self.menuCopyCnty = editmenu.Append(wx.ID_ANY,"Copy &County\tCtrl+C"," Copy county abbreviation to clipboard")

        self.Bind(wx.EVT_MENU, self.OnCopyGrid, self.menuCopyGrid)
        self.Bind(wx.EVT_MENU, self.OnCopyCnty, self.menuCopyCnty)

        helpmenu = wx.Menu()
        self.menuAboutLogs = helpmenu.Append(wx.ID_ANY, "About", " Open about dialog")
        self.Bind(wx.EVT_MENU, self.OnAboutLogs, self.menuAboutLogs)
    
        self.menuBar = wx.MenuBar()
        self.menuBar.Append(filemenu,"&File")
        self.menuBar.Append(editmenu,"&Edit")
        self.menuBar.Append(helpmenu,"&Help")
        self.SetMenuBar(self.menuBar)
    
    def CreateControls(self):
        self.panel = wx.Panel(self)
        
        # Grid Square
        self.lblGrid = wx.StaticText(self.panel, label="Grid Square", pos=(10,10))
        self.lblGrid.SetFont(self.h2_font)
        #self.txtGrid = wx.Button(self.panel, label="-", pos=(20,30),style=wx.BORDER_NONE)
        self.txtGrid = wx.StaticText(self.panel, label="-", pos=(20,30))
        self.txtGrid.SetFont(self.h1_font)
        #self.panel.Bind(wx.EVT_LEFT_UP, self.OnClickGrid)
        
        # County
        self.lblCnty = wx.StaticText(self.panel, label="County or City", pos=(160,10))
        self.lblCnty.SetFont(self.h2_font)
        self.txtCnty = wx.StaticText(self.panel, label="-", pos=(170,30))
        #self.txtCnty = wx.Button(self.panel, label="-", pos=(170,30))
        self.txtCnty.SetFont(self.h1_font)
    
    def OnClickGrid(self,event):
        print("yay")
    
    def OnClose(self, event):
        print ("closing...")
        self.WriteSettings()
        if self.geoDet.is_alive():
            print ("stopping serial thread")
            self.geoDet.stop()
            self.geoDet.join()
        self.CloseSerialPort()
        self.Destroy()
        
    def OnOpenSerialPort(self, event):
        dlg = SerialConfigDialog(self, -1, "", serial=self.serial, show=1)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.config.add_section('SERIAL')
            except:
                pass
            self.config.set('SERIAL','port', self.serial.port)
            self.config.set('SERIAL','rate', "%d" % self.serial.baudrate)
            self.OpenSerialPort()

    def OnOpenBoundaryFile(self, event):
        dlg = wx.FileDialog(self, "Select Geographic Boundary File", wildcard="KML File (*.kml)|*.kml")
        if dlg.ShowModal() == wx.ID_OK:
            file = "{}{}{}".format(dlg.GetDirectory(),os.sep,dlg.GetFilename())
            try:
                self.config.add_section('BOUNDARY')
            except:
                pass
            self.config.set('BOUNDARY','file',file)
            self.geoDet.loadBoundaries(file)
        
    def OnCopyGrid(self, event):
        if not wx.TheClipboard.IsOpened():
           clipdata = wx.TextDataObject()
           clipdata.SetText("{}\n".format(self.geo_grid))
           wx.TheClipboard.Open()
           wx.TheClipboard.SetData(clipdata)
           wx.TheClipboard.Close()            

    def OnCopyCnty(self, event):
        if not wx.TheClipboard.IsOpened():
           clipdata = wx.TextDataObject()
           clipdata.SetText("{}\n".format(self.geo_cnty))
           wx.TheClipboard.Open()
           wx.TheClipboard.SetData(clipdata)
           wx.TheClipboard.Close()            

    def OnAboutLogs(self, event):
        #dlg = wx.MessageDialog(self, "Log Path")
        #dlg.ShowModal()
        dlg = geoAboutDialog(self)
        dlg.Show()

    def UpdateGrid(self, s):
        self.txtGrid.SetLabel(s)
    
    def UpdateCnty(self, s):
        self.txtCnty.SetLabel(s)
    
    def UpdateStatus(self, s):
        self.SetStatusText(s)

    def GeoDetCB(self, msg):
        (t,s) = msg
        if t == geoMsg.GRID:
            self.geo_grid = s
            wx.CallAfter(self.UpdateGrid,s)
        elif t == geoMsg.CNTY:
            (n,a) = s
            self.geo_cnty = a
            wx.CallAfter(self.UpdateCnty,"{} ({})".format(n,a))
        elif t == geoMsg.STAT:
            wx.CallAfter(self.UpdateStatus,s)
        elif t == geoMsg.TIME:
            self.stat_time = s
            wx.CallAfter(self.UpdateStatus,"{} - {}".format(self.stat_time, self.stat_gps))
        elif t == geoMsg.GPS:
            self.stat_gps = s
            wx.CallAfter(self.UpdateStatus,"{} - {}".format(self.stat_time, self.stat_gps))
        elif t == geoMsg.NOTIF:
            self.Iconize(False)
            self.Raise()
            self.RequestUserAttention()
           
    
if __name__ == '__main__':
    app = wx.App(False)
    frame = geoFrame()
    app.MainLoop()
    
    #app = arGeoDetector()
    #try:
    #    app.run()
    #except KeyboardInterrupt:    
    #    app._do_exit = 1



