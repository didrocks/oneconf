# -*- coding: utf-8 -*-
# Copyright (C) 2010 Canonical
#
# Authors:
#  Rodney Dawes <rodney.dawes@canonical.com>
#  Didier Roche <didrocks@ubuntu.com>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUTa
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

import datetime
import logging
import os

import gettext
from gettext import gettext as _

DESKTOPCOUCH_LOG = os.path.expanduser('~/.cache/desktop-couch/log/desktop-couch-replication.log')


def get_last_sync_date():
    """Check desktopcouch sync status"""
    if not os.path.exists(DESKTOPCOUCH_LOG):
        # no sync yet
        return None
    for line in BackwardsReader(file(DESKTOPCOUCH_LOG)):
        # started replicating seems to take ages, so "now syncing" can't be done right now
        if "finished replicating" in line:
            try:
                last_sync = datetime.datetime.strptime(line[:19], '%Y-%m-%d %H:%M:%S')
                today = datetime.datetime.strptime(str(datetime.date.today()), '%Y-%m-%d')
                the_daybefore = today - datetime.timedelta(days=1)
                if last_sync > today:
                    return _("Last sync %s") % last_sync.strftime('%H:%M')
                elif last_sync < today and last_sync > the_daybefore:
                    return _("Last sync yesterday %s") % last_sync.strftime('%H:%M')
                else:
                    return _("Last sync %s") % last_sync.strftime('%Y-%m-%d  %H:%M')                    
            except ValueError, e:
                logging.warning("can't convert desktopcouch sync date to %s", e)
            break
    return None

def BackwardsReader(fileread, BLKSIZE = 4096):
    """Read desktopcouch log file line by line, backwards"""
    buf = ""
    fileread.seek(-1, 2)
    lastchar = fileread.read(1)
    trailing_newline = (lastchar == "\n")

    while 1:
        newline_pos = buf.rfind("\n")
        pos = fileread.tell()
        if newline_pos != -1:
            # Found a newline
            line = buf[newline_pos+1:]
            buf = buf[:newline_pos]
            if pos or newline_pos or trailing_newline:
                line += "\n"
            yield line
        elif pos:
            # Need to fill buffer
            toread = min(BLKSIZE, pos)
            fileread.seek(-toread, 1)
            buf = fileread.read(toread) + buf
            fileread.seek(-toread, 1)
            if pos == toread:
                buf = "\n" + buf
        else:
            # Start-of-file
            return

