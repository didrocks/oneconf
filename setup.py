#!/usr/bin/env python

from setuptools import setup
from DistUtilsExtra.command import *

import re
import sys
import glob
from codecs import open
from subprocess import Popen, PIPE

# update version.py
with open('debian/changelog', encoding='utf-8') as fp:
    line = fp.readline()

m = re.match("^[\w-]+ \(([\w\.~]+)\) ([\w-]+);", line)
VERSION = m.group(1)
CODENAME = m.group(2)
DISTRO = Popen(["lsb_release", "-s", "-i"],
               stdout=PIPE,
               universal_newlines=True).communicate()[0].strip()
RELEASE = Popen(["lsb_release", "-s", "-r"],
                stdout=PIPE,
                universal_newlines=True).communicate()[0].strip()

#should be replaced by $USR
oneconf_service_path = "/usr/share/oneconf/oneconf-service"

# Only write the files if we're building.
if any(argv for argv in sys.argv if 'build' in argv):
    with open('oneconf/version.py', 'w', encoding='utf-8') as fp:
        fp.write("""\
VERSION='%s'
CODENAME='%s'
DISTRO='%s'
RELEASE='%s'
""" % (VERSION, CODENAME, DISTRO, RELEASE))
    with open('misc/com.ubuntu.OneConf.service', 'w', encoding='utf-8') as fp:
        fp.write("""\
[D-BUS Service]
Name=com.ubuntu.OneConf
Exec=%s
""" % oneconf_service_path)

# The scripts only work with Python 3.
if sys.version_info[0] == 3:
    scripts = ['oneconf-query', 'oneconf-service', 'misc/oneconf-update']
else:
    scripts = []

# real setup
setup(name="oneconf", version=VERSION,
      scripts=scripts,
      packages = ['oneconf',
                  'oneconf.distributor',
                  'oneconf.networksync',
                 ],
      data_files=[
                  ('share/oneconf/data/images/',
                   glob.glob("data/images/*.png")),
                  ('share/dbus-1/services/',
                   ["misc/com.ubuntu.OneConf.service"]),
                  ],
      cmdclass = { "build" : build_extra.build_extra,
                   "build_i18n" :  build_i18n.build_i18n,
                   "build_help" : build_help.build_help,
                   "build_icons" : build_icons.build_icons},
      test_suite = 'nose.collector',
      test_requires = [
          'piston_mini_client',
          ],
      )
