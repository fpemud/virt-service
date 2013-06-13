#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import dbus
import dbus.service

################################################################################
# DBus API Docs
################################################################################
#
# ==== Main Application ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService
# Object path           /
#
# Methods:
# void newNetworkService(vmUuid:string, networkType:string)
# void deleteNetworkService(vmUuid:string)
#
# Signals:
#
# ==== Service ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService.NetworkService
# Object path           /NetworkServices/{vmUuid:string}
#
# Methods:
# tapname:string getTapInterface()
# account:string getSambaAccount()
# void           addSambaShare(name:string, srcPath:string, readonly:boolean)
# void           deleteSambaShare(name:string)
# 
# Signals:
#

class VirtServiceException(dbus.DBusException):
    _dbus_error_name = 'org.fpemud.VirtService.Exception'

class MainDbusItem(dbus.service.Object):

	def __init__(self):
		bus_name = dbus.service.BusName('org.fpemud.VirtService',bus=dbus.SessionBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService')
		self.netServDict = dict()

	def __del__(self):
		assert len(self.netServDict) == 0

	@dbus.service.method('org.fpemud.VirtService')
	def newNetworkService(self, vmUuid, networkType):
		self.netServDict[vmUuid] = NetworkService(vmUuid, networkType)

	@dbus.service.method('org.fpemud.VirtService')
	def deleteNetworkService(self, vmUuid):
		del self.netServDict[vmUuid]

class NetworkService(dbus.service.Object):

	def __init__(self, vmUuid, networkType):
		bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SessionBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/Services/%s'(vmUuid))

		self.vmUuid = vmUuid
		self.netObj = g_netObjDict[networkType]
		self.netObj.addVmObj(self.vmUuid)

	def __del__(self):
		self.netObj.removeVmObj(self.vmUuid)

	@dbus.service.method('org.fpemud.VirtService.Service')
	def getTapInterface(self, netType):
		return self.netObj.getTapInterface(self.vmUuid)

	@dbus.service.method('org.fpemud.VirtService.Service')
	def getSambaAccount(self):
		return self.netObj.getSambaServer().getAccountInfo(self.vmUuid)

	@dbus.service.method('org.fpemud.VirtService.Service')
	def addSambaShare(self, shareName, srcPath, readonly):
		return self.netObj.getSambaServer().addShare(self.vmUuid, shareName, srcPath, readonly)

	@dbus.service.method('org.fpemud.VirtService.Service')
	def deleteSambaShare(self, shareName):
		return self.netObj.getSambaServer().removeShare(self.vmUuid, shareName)


