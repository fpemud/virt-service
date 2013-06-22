#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop
from virt_util import VirtUtil
from virt_dbus import DbusMainObject
from virt_host_network import VirtHostNetwork

# loading kernel module, should be in openvpn
VirtUtil.loadKernelModule("tun")

# create main loop
DBusGMainLoop(set_as_default=True)
mainloop = GLib.MainLoop()

# create network manager of host machine
hostNetwork = VirtHostNetwork()

# create dbus root object
dbusMainObject = DbusMainObject(mainloop, hostNetwork)

# start main loop
mainloop.run()

# release operation
dbusMainObject.release()

