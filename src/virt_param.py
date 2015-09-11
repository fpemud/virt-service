#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import tempfile


class VirtParam:

    """Temp directory structure:
         /tmp/virt-service
          |----1000                             user directory
                |----0                          network directory
                     |----samba
                           |----smb.conf        samba configuration file
                           |----smb.log         samba log file"""

    def __init__(self):
        self.tmpDir = tempfile.mkdtemp(prefix="virt-service.")

        self.ctrlPort = 2207

        self.mainloop = None
        self.hostNetwork = None
        self.netManager = None
        self.vfioDevManager = None
        self.dhcpServer = None
        self.sambaServer = None

        self.initError = None

        self.timeout = 60
        self.timeoutHandler = None


class VirtInitializationError(Exception):

    def __init__(self, message):
        self.message = message
