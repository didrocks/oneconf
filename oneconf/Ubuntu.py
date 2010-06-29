# Copyright (C) 2010 Canonical
#
# Authors:
#  Didier Roche <didrocks@ubuntu.com>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

from oneconf.distributor import Distro
import re


class Ubuntu(Distro):

    def get_distro_channel_name(self):
        """ The name in the Release file """
        return "Ubuntu"

    def is_recommends_as_dep(self):
        return True

    def get_false_defaults(self):
        return set(['p7zip-full', 'vim-gnome', 'vim'])

    def get_distribution_meta_packages(self):
        return set(['ubuntu-minimal', 'ubuntu-standard', 'ubuntu-desktop',
                    'ubuntu-netbook', 'xubuntu-desktop', 'lubuntu-desktop',
                    'mythbuntu-desktop'])



