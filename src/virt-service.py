#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop
from virt_util import VirtUtil
from virt_dbus import DbusMainObject

# loading kernel module, should be in openvpn
VirtUtil.loadKernelModule("tun")

# create dbus root object
DBusGMainLoop(set_as_default=True)
dbusMainObject = DbusMainObject()

# start main loop
mainloop = GLib.MainLoop()
mainloop.run()

