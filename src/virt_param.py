#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-


class VirtParam:

    """Temp directory structure:
         /tmp/virt-service
          |----1000                             user directory
                |----0                          network directory
                     |----samba
                           |----smb.conf        samba configuration file
                           |----smb.log         samba log file"""

    def __init__(self):
        self.mainloop = None
        self.hostNetwork = None
        self.vfioDevManager = None
        self.tmpDir = None
        self.macOuiVm = "00:50:01"
        self.ip1 = 10
        self.ctrlPort = 2207
