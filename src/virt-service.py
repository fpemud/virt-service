#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import shutil
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop
from virt_util import VirtUtil
from virt_param import VirtParam
from virt_dbus import DbusMainObject
from virt_host_network import VirtHostNetwork
from virt_vfiodev_manager import VirtVfioDeviceManager

# create VirtParam object
param = VirtParam()
dbusMainObject = None
try:
	# create temp directory
	param.tmpDir = "/tmp/virt-service"
	os.mkdir(param.tmpDir)

	# create main loop
	DBusGMainLoop(set_as_default=True)
	param.mainloop = GLib.MainLoop()

	# create network manager of host machine
	param.hostNetwork = VirtHostNetwork()

	# create VFIO device manager
	param.vfioDevManager = VirtVfioDeviceManager()

	# create dbus root object
	dbusMainObject = DbusMainObject(param)

	# start main loop
	param.mainloop.run()
finally:
	if dbusMainObject is not None:
		dbusMainObject.release()
	if param.tmpDir is not None and os.path.exists(param.tmpDir):
		shutil.rmtree(param.tmpDir)

