# bloodp

Bloodp is:
* bloop.tex, a latex file (using pgfplots and pgfplotstable) allowing to print a document with blood pressure and pulse figures and tables  from a csv file
* bloodp.py, a python3 tool for reading blood pressure and pulse measurements from an Omron M6 Comfort IT and put them in csv files

I used https://github.com/LazyT/obpm to know the commands to send to the device on USB and the format of the answer.

## Motivations:

* works on linux
* all data remains strictly local
* allows me to change what is printed
* nothing to compile, install

## Usage

Please verify the dependencies and the permissions (see below).

*  to put the data in 2 csv files (one for each user), plug the device in an USB port, push the power button if it is in sleep mode (noting on screen) and type:

   ```
        python3 bloodp.py --log=INFO u1-20151215-20160115.csv u2.csv --afterDate 2015-12-15
   ```

   If one of the files doesn't exist, --afterDate is mandatory and only the data after that date are dumped in the file.

   If one of the files exists, the new data is appended to the file: the date of the last measure is read on the last line of the existing file.
*  to generate a pdf file for user 1:

   ```
        pdflatex "\def\mycsv{u1-20151215-20160104.csv}\input{bloodp.tex}"
        mv bloodp.pdf u1-20151215-20160104.pdf
   ```

   Several execution of the same pdflatex command are sometimes necessary to have long tables right.
*  to generate a pdf for user 2 with texts in french and a name in the footer:

   ```
        pdflatex "\def\mycsv{u2.csv}\def\mylang{fr}\def\myname{John Doe}\input{bloodp.tex}"
        mv bloodp.pdf u2.pdf
   ```

*  to execute the doctest tests in the python program:

   ```
        python3 -m doctest -v  bloodp.py
   ```

## Dependencies

On debian, please install:

```
    apt-get install python3-usb texlive-pictures
```

## Permissions

On linux, if you get permission errors, you should create an udev rule and restart udev with the device unplugged, for example in /etc/udev/rules.d/40-bloodp.rules on Debian:

```
ACTION!="add|change", GOTO="bloodp_rules_end"
SUBSYSTEM!="usb|usb_device", GOTO="bloodp_rules_end"
# M6 Confort IT HEM 7322U-E
ATTRS{idVendor}=="0590", ATTRS{idProduct}=="0090", MODE="664", GROUP="plugdev"
LABEL="bloodp_rules_end"
```

## File format

### Version 1

For example:

```
User;Date;AmPm;Typ;Sys;Dia;Pulse;p4;p5;p6;p7;p8;p9;p10;p11;p12;p13
1;2015-12-14 10:02;am;msr;120;83;71;49;202;16;153;0;67;65;128;228;176
1;2015-12-14 10:03;am;msr;119;84;67;49;202;16;234;0;56;64;128;165;241
1;2015-12-14 10:03;am;avg;120;84;69;;;;;;;;;;
```

There are 14 bytes per measure in the raw data received from the device.
Only the first seven bytes (the 4 first fully and the 3 next partially)
are used to decode the data in the Date, Sys, Dia, Pulse fields.
To allow decoding of more data in the future, the partially decoded bytes
and the bytes not used are dumped in the p4 to p13 fields.

## Author

Marc Alber marc.alber@albemaconseil.&#102;r

