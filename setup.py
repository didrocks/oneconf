#!/usr/bin/env python

from distutils.core import setup
from DistUtilsExtra.command import *

import re
import glob
import os
from subprocess import Popen, PIPE, call
import sys

# update version.py
line = open("debian/changelog").readline()
m = re.match("^[\w-]+ \(([\w\.~]+)\) ([\w-]+);", line)
VERSION = m.group(1)
CODENAME = m.group(2)
DISTRO = Popen(["lsb_release", "-s", "-i"], stdout=PIPE).communicate()[0].strip()
RELEASE = Popen(["lsb_release", "-s", "-r"], stdout=PIPE).communicate()[0].strip()
open("oneconf/version.py","w").write("""
VERSION='%s'
CODENAME='%s'
DISTRO='%s'
RELEASE='%s'
""" % (VERSION, CODENAME, DISTRO, RELEASE))

#should be replaced by $USR
oneconf_service_path = "/usr/share/oneconf/oneconf-service"
open("misc/com.ubuntu.OneConf.service","w").write("""[D-BUS Service]
Name=com.ubuntu.OneConf
Exec=%s""" % oneconf_service_path)

# real setup
setup(name="oneconf", version=VERSION,
      scripts=["oneconf-query",
               "oneconf-service",
               "misc/oneconf-update",
               ],
      packages = ['oneconf',
                  'oneconf.uscplugin',
                  'oneconf.networksync',
                 ],
      data_files=[
                  ('share/oneconf/data/ui/',
                   glob.glob("data/ui/*.ui")),
                  ('share/oneconf/data/images/',
                   glob.glob("data/images/*.png")),
                  ('share/dbus-1/services/',
                   ["misc/com.ubuntu.OneConf.service"]),
                  ],
      cmdclass = { "build" : build_extra.build_extra,
                   "build_i18n" :  build_i18n.build_i18n,
                   "build_help" : build_help.build_help,
                   "build_icons" : build_icons.build_icons}
      )


