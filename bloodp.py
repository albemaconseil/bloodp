#!/usr/bin/env python
#
# Copyright (c) 2015 Marc Alber
# License GPLv2
# This code is licensed under the GNU public license (GPL). See LICENSE for
# details.

# ID 0590:0090
# M6 Confort IT HEM 7322U-E

from operator import xor
from datetime import datetime
try:
    import usb.core
    import usb.util as util
except ImportError:
    import usb
from array import array
import sys
from functools import reduce
import argparse
import os
import logging

# omron device modes
VID = 0x0590
##PID = 0x0028
PID = 0x0090
INIT_CMD = array('B', [0x02, 0x08, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x18])
DONE_CMD = array('B', [0x02, 0x08, 0x0f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07])
PAYLOAD_MSRLEN = 14

class BloodpArgs:
    def __init__(self):
        parser = argparse.ArgumentParser(description='Transfer Omron Blood Pressure Monitor measurement values.')
        parser.add_argument('user1_csv', metavar='U1.csv',
                            help='File for user 1')
        parser.add_argument('user2_csv', metavar='U2.csv',
                            help='File for user 2')
        parser.add_argument('--afterDate', '-a', help='Date in "YYYY-MM-DD" format or date and time in "YYYY-MM-DD hh:mm" format')
        parser.add_argument('--log', '-l', help='Log level (DEBUG, INFO, WARNING)')
        self.args = parser.parse_args()
        if (self.args.log != None):
            numeric_level = getattr(logging, self.args.log.upper(), None)
            if not isinstance(numeric_level, int):
                raise ValueError('Invalid log level: %s' % self.args.log)
            logging.basicConfig(level=numeric_level)

class BloodpMonitor:
    
    @staticmethod
    def buildCRC(data):
        """ Computes the cyclic redundancy check (CRC)

        A simple one byte crc computed by xoring all the input bytes.
        
        Args:
            data (bytearray): The bytes to use to compute the crc.

        Returns:
            bytes: the crc.

        Example:
        
        >>> BloodpMonitor.buildCRC(array('B', [0x02, 0x08, 0x00, 0x00 \
            , 0x00, 0x00, 0x10, 0x00]))
        24
        >>> BloodpMonitor.buildCRC(array('B', [0x02, 0x08, 0x0f, 0x00 \
            , 0x00, 0x00, 0x00, 0x00]))
        7
        """
        crc = 0
        len = data[1] - 1
        while len > 0:
            crc = crc ^ data[len]
            len = len - 1
        return crc
    
    def __getRawMeasures(self):
        logging.debug('USB Dev reset')
        dev = usb.core.find(idVendor=VID, idProduct=PID)
        if dev is None:
            logging.error('Please connect the device to the USB bus or check the vendor and product Id')
            sys.exit()

        if dev.is_kernel_driver_active(0):
            logging.debug('USB detach device from the OS')
            dev.detach_kernel_driver(0)
        try:
            logging.debug('USB set configuration')
            dev.set_configuration()
        except usb.core.USBError as e:
            logging.error('set_configuration exception %s', str(e))
            errno, strerror = e.args
            dev.reset()
        logging.debug('USB claim interface')
        util.claim_interface(dev, 0)
        # get an endpoint instance
        cfg = dev.get_active_configuration()
        intf = cfg[(0,0)]

        epOut = usb.util.find_descriptor(
            intf,
            # match the first OUT endpoint
            custom_match = \
            lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_OUT)

        assert epOut is not None
        logging.debug('USB first OUT endpoint is %s', str(epOut))

        epIn = usb.util.find_descriptor(
            intf,
            # match the first IN endpoint
            custom_match = \
            lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_IN)

        assert epIn is not None
        logging.debug('USB first IN endpoint is %s', str(epIn))

        logging.debug('USB Out (INIT_CMD): %s', INIT_CMD)
        epOut.write(INIT_CMD)
        while True:
            try:
                answer = dev.read(epIn.bEndpointAddress, \
                                  epIn.wMaxPacketSize, timeout=1000)
                logging.debug('USB In Init answer: %s', str(answer))
            except usb.core.USBError as e:
                answer = None
                logging.error('Exception %s', str(e))
                #errno, strerror = e.args
                #sys.stderr.write("I/O error({0}): {1}\n".format(errno,strerror))
                logging.error('Please push the "Start/Stop" button')
                dev.reset()
                usb.util.release_interface(dev, 0)
                dev.attach_kernel_driver(0)
                sys.exit()
            if len(answer) > 47:
                break

        getDataCmdTmpl = array('B', [0x02, 0x08, 0x01, 0x00, 0x02, 0xac, 0x28, 0x00, 0x8f ])
        addr = 0x02AC
        payload = array('B')
        for i in range(70):
            getDataCmdTmpl[4] = addr >> 8
            getDataCmdTmpl[5] = addr & 0xFF
            getDataCmdTmpl[8] = BloodpMonitor.buildCRC(getDataCmdTmpl)
            logging.debug('USB Out get data %d: %s', i, getDataCmdTmpl)
            epOut.write(getDataCmdTmpl)
            while True:
                try:
                    answer = dev.read(epIn.bEndpointAddress, \
                                      epIn.wMaxPacketSize, timeout=1000)
                    logging.debug("USB In (%d b): %s", len(answer), str(answer))
                except usb.core.USBError as e:
                    answer = None
                    logging.error('Exception' + str(e))
                    #if e.args == ('Operation timed out',):
                    dev.reset()
                    usb.util.release_interface(dev, 0)
                    dev.attach_kernel_driver(0)
                    sys.exit()
                    #break
                if len(answer) > 47:
                    payload.extend(answer[7:47])
                    break
                else :
                    raise ValueError('Partial read')
            addr += 40
        logging.debug('USB Out (DONE_CMD): %s', DONE_CMD)
        epOut.write(DONE_CMD)
        try:
            answer = dev.read(epIn.bEndpointAddress, \
                              epIn.wMaxPacketSize, timeout=1000)
            logging.debug("USB In Done answer: %s", str(answer))
        except usb.core.USBError as e:
            answer = None
            logging.error('Done answer Exception %s', str(e))

        # release the device
        logging.debug('USB Dev reset')
        dev.reset()
        logging.debug('USB release interface')
        usb.util.release_interface(dev, 0)
        # reattach the device to the OS kernel
        logging.debug('USB reattach the device to the OS kernel')
        dev.attach_kernel_driver(0)
        return payload
        
    def __converRawMeasures(self, payload):
        """ Converts the raw data with packed date and hour into
        an array of arrays with user, year, month, etc...

        Raw data with 255 as first data (Diastolic pressure) are ignored.

        Args:
            payload (bytearray): The bytes read from the monitor.

        Returns:
            array: the (partially) decoded measures.

        Example:

         >>> monitor = BloodpMonitor(0); \
         payload = array('B', [83, 95, 15, 71, 49, 202, 16, 153, 0, \
         67, 65, 128, 228, 176, 84, 94, 15, 67, 49, 202, 16, 234, 0, \
         56, 64, 128, 165, 241]); \
         monitor._BloodpMonitor__converRawMeasures(payload)
         [(1, 2015, 12, 14, 10, 2, '2015-12-14 10:02', 120, 83, 71, \
array('B', [49, 202, 16, 153, 0, 67, 65, 128, 228, 176])), \
(1, 2015, 12, 14, 10, 3, '2015-12-14 10:03', 119, 84, 67, \
array('B', [49, 202, 16, 234, 0, 56, 64, 128, 165, 241]))]
        """
        msr = []
        for j in range(int(len(payload) / PAYLOAD_MSRLEN)):
            i = PAYLOAD_MSRLEN * j
            u = 1
            if (j >= 100):
                u = 2
            if (payload[i] == 255):
                continue
            logging.debug('payload %d: %s', j, payload[i:i + PAYLOAD_MSRLEN])
            diastolic = payload[i]
            systolic = payload[i + 1] + 25
            pulse = payload[i + 3]
            y = 2000 + payload[i + 2]
            M = (payload[i + 4]>>2) & 0x0F
            d = ((payload[i + 4]<<8 | payload[i + 5])>>5) & 0x1F
            h = payload[i + 5] & 0x1F
            m = ((payload[i + 6]<<8 | payload[i + 7])>>6) & 0x3F
            msr.append((u, y, M, d, h, m, "%04d-%02d-%02d %02d:%02d" % \
                        (y, M, d, h, m), systolic, diastolic, pulse, \
                        payload[i + 4:i + 14]))
        return sorted(msr)
    
    def getMeasures(self):
        payload = self.__getRawMeasures()
        return self.__converRawMeasures(payload)

class Csv:
    def __init__(self, fname, afterDate):
        self.__fname = fname
        self.__afterDate = afterDate
        self.__nbMsr = 0
        self.__nbAvg = 0

    def __nbMeasuresAfter(self, measures, user):
        """ Counts the number of (new) measures for a user.

        Args:
            measures (array): The measures
            user (int): The user 1 or 2

        >>> csv = Csv('f1', None, 0); \
            msr = [(1, 2015, 12, 14, 10, 2, '2015-12-14 10:02', 120, 83, 71, \
                array('B', [49, 202, 16, 153, 0, 67, 65, 128, 228, 176])), \
                (1, 2015, 12, 14, 10, 3, '2015-12-14 10:03', 119, 84, 67, \
                array('B', [49, 202, 16, 234, 0, 56, 64, 128, 165, 241]))]; \
            csv._Csv__nbMeasuresAfter(msr, 1);
        2
        """
        nb = 0
        for m in measures:
            if (m[0] != user):
                continue
            if self.__afterDate is None :
                nb = nb + 1
            else :
                pl = m[10]
                if (m[4] >= 12) :
                    ampm = "pm"
                else :
                    ampm = "am"
                strl = "%d;%s;%s;msr;%d;%d;%d;%d;%d;%d;%d;%d;%d;%d;%d;%d;%d\n" % \
                       (user, m[6], ampm, m[7], m[8], m[9], pl[0], \
                        pl[1], pl[2], pl[3], pl[4], pl[5], pl[6], \
                        pl[7], pl[8], pl[9])
                after = '%d;%s'%(user, self.__afterDate)
                if strl > after :
                    nb = nb + 1
        return nb
                
    def __writeAfterMeasures(self, f, measures, user, after):
        """ Write the new measures at the end of the file.

        New measures are those with a date after the value of the 'after'
        argument.
        
        Args:
            f (bytearray): The bytes read from the monitor.
            measures (array): The measures
            user (int): The user 1 or 2
            after (string): Use only the measures after this date 

        Example:
        >>> from io import StringIO; \
            f = StringIO(); \
            csv = Csv('f1', None, 0); \
            msr = [(1, 2015, 12, 14, 10, 2, '2015-12-14 10:02', 120, 83, 71, \
                array('B', [49, 202, 16, 153, 0, 67, 65, 128, 228, 176])), \
                (1, 2015, 12, 14, 10, 3, '2015-12-14 10:03', 119, 84, 67, \
                array('B', [49, 202, 16, 234, 0, 56, 64, 128, 165, 241]))]; \
            csv._Csv__writeAfterMeasures(f, msr, 1, '1970-01-01'); \
            print(f.getvalue())
        1;2015-12-14 10:02;am;msr;120;83;71;49;202;16;153;0;67;65;128;228;176
        1;2015-12-14 10:03;am;msr;119;84;67;49;202;16;234;0;56;64;128;165;241
        1;2015-12-14 10:03;am;avg;120;84;69;;;;;;;;;;
        <BLANKLINE>
        """
        mSys = 0
        mDia = 0
        mPulse = 0
        nb = 0
        m1 = []
        for m in measures:
            if (m[0] != user):
                continue
            if ((nb != 0) and (m[0] != m1[0] or m[1] != m1[1] \
                               or m[2] != m1[2] or m[3] != m1[3] \
                               or (m[4] * 60 + m[5] - m1[4] * 60 - m1[5]) > 30 )) :
                if (m1[4] >= 12) :
                    ampm = "pm"
                else :
                    ampm = "am"
                strl = "%d;%s;%s;avg;%d;%d;%d;;;;;;;;;;\n" % \
                       (m1[0], m1[6], ampm, round(mSys / float(nb)), \
                        round(mDia / float(nb)), round(mPulse / float(nb)))
                f.write(strl)
                self.__nbAvg += 1
                nb = 0
                mSys = 0
                mDia = 0
                mPulse = 0
            pl = m[10]
            if (m[4] >= 12) :
                ampm = "pm"
            else :
                ampm = "am"
            u = m[0]
            strl = "%d;%s;%s;msr;%d;%d;%d;%d;%d;%d;%d;%d;%d;%d;%d;%d;%d\n" % \
                   (u, m[6], ampm, m[7], m[8], m[9], pl[0], pl[1], pl[2], \
                    pl[3], pl[4], pl[5], pl[6], pl[7], pl[8], pl[9])
            if strl > after :
                m1 = m
                mSys += m[7]
                mDia += m[8]
                mPulse += m[9]
                nb = nb + 1
                f.write(strl)
                self.__nbMsr += 1
        if nb != 0 :
            if (m1[4] >= 12) :
                ampm = "pm"
            else :
                ampm = "am"
            strl = "%d;%s;%s;avg;%d;%d;%d;;;;;;;;;;\n" % \
                   (m1[0], m1[6], ampm, round(mSys / float(nb)), \
                    round(mDia / float(nb)), round(mPulse / float(nb)))
            f.write(strl)
            self.__nbAvg += 1
        
    def updateCsv(self, measures, user):
        if self.__nbMeasuresAfter(measures, user) == 0:
            logging.info("No measures to add to %s", self.__fname)
            return
        if os.access(self.__fname, os.F_OK):
            # calls close automatically at end of with block
            with open(self.__fname) as f:
                lines = f.read().splitlines()
        else :
            lines = ["User;Date;AmPm;Typ;Sys;Dia;Pulse;p4;p5;p6;p7;p8;p9;p10;p11;p12;p13"]
        #print("args=", args)
        if self.__afterDate is None :
            if len(lines) == 1 :
                logging.error("Empty user file '" + self.__fname + "': option --afterDate YYYY-MM-DD needed")
                sys.exit()
            after = lines[len(lines) - 1][0:19] + 'x'
        else :
            after = '%d;%s'%(user, self.__afterDate)
            if len(lines) > 1 :
                l = lines[len(lines) - 1][0:19] + 'x'
                if l > after :
                    after = l
        logging.debug('after=%s', after)
        f = open(self.__fname + '.tmp', 'w')
        for l in lines :
            f.write(l + '\n')
        self.__writeAfterMeasures(f, measures, user, after)
        f.close()
        if os.access(self.__fname, os.F_OK):
            os.rename(self.__fname, self.__fname + '.bak')
        os.rename(self.__fname + '.tmp', self.__fname)
        if self.__nbMsr == 0 :
            logging.info("No measures to add to %s", self.__fname)
        else :
            logging.info("%d measures and %d averages added to %s" \
                         , self.__nbMsr, self.__nbAvg, self.__fname)

class Bloodp:
    def main(self):
        args = BloodpArgs().args
        monitor = BloodpMonitor()
        file1 = Csv(args.user1_csv, args.afterDate)
        file2 = Csv(args.user2_csv, args.afterDate)
        measures = monitor.getMeasures()
        file1.updateCsv(measures, 1)
        file2.updateCsv(measures, 2)

if __name__ == "__main__":
    b = Bloodp()
    b.main()
