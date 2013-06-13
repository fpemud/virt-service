#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop
from virt_util import VirtUtil
from virt_network import VirtNetworkBridge
from virt_network import VirtNetworkNat
from virt_network import VirtNetworkRoute
from virt_network import VirtNetworkIsolate
from virt_dbus import MainDbusItem

assert len(sys.argv) >= 6

# get arguments
g_uid = int(sys.argv[1])
g_username = sys.argv[2]
g_gid = int(sys.argv[3])
g_groupname = sys.argv[4]
g_pwd = sys.argv[5]

# loading kernel module, should be in openvpn
loadKernelModule("tun")

# create network object
g_netObjDict = dict()
g_netObjDict["bridge"] = VirtNetworkBridge(g_uid)
g_netObjDict["nat"] = VirtNetworkNat(g_uid)
g_netObjDict["route"] = VirtNetworkRoute(g_uid)
g_netObjDict["isolate"] = VirtNetworkIsolate(g_uid)

# create dbus root object
g_mainDbusItem = MainDbusItem()

# start main loop
DBusGMainLoop(set_as_default=True)
mainloop = GLib.MainLoop()
mainloop.run()

