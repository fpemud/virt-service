#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import dbus
import dbus.service
from virt_network import VirtNetworkBridge
from virt_network import VirtNetworkNat
from virt_network import VirtNetworkRoute
from virt_network import VirtNetworkIsolate
from virt_samba import VirtSambaServer

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
# networkId:string NewNetwork(networkType:string)
# void             DeleteNetwork(networkId:string)
#
# Signals:
#
# ==== Network ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService.Network
# Object path           /Networks/{networkId:string}
#
# Methods:
# vmId:int         AddVm(vmName:string)
# void             DeleteVm(vmId:int)
# tapifname:string GetTapInterface(vmId:int)
# 
# Signals:
#
# ==== VmService ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService.Network.VmService
# Object path           /Networks/{networkId:string}/VmServices/{vmId:int}
#
# Methods:
# void             SambaSetEnable(onOff:boolean)
# account:string   SambaGetAccount()
# void             SambaAddShare(shareName:string, srcPath:string, readonly:boolean)
# void             SambaDeleteShare(shareName:string)
#
# Signals:
#

class VirtServiceException(dbus.DBusException):
    _dbus_error_name = 'org.fpemud.VirtService.Exception'

class DbusMainObject(dbus.service.Object):

	def __init__(self):
		self.netObjList = []

		bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService')

	def __del__(self):
		assert len(self.netObjList) == 0

	@dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', 
	                     in_signature='s', out_signature='s')
	def NewNetwork(self, networkType, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		uid = self.connection.get_unix_user(sender)

		# find existing network object
		for no in self.netObjList:
			if no.uid == uid and no.networkType == networkType:
				return no.networkId

		# create new network object
		nid = 0
		for no in self.netObjList:
			if no.uid == uid and no.nid >= nid:
				nid = no.nid + 1
		networkId = "%d_%d"%(uid, nid)
		self.netObjList.append(DbusNetworkObject(uid, nid, networkId, networkType))

		return networkId

	@dbus.service.method('org.fpemud.VirtService', sender_keyword='sender',
	                     in_signature='s')
	def DeleteNetwork(self, networkId, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		uid = self.connection.get_unix_user(sender)

		# find network object
		netObj = None
		for no in self.netObjList:
			if no.uid != uid and no.networkId == networkId:
				netObj = no
				break
		if netObj is None:
			raise Exception("the specified network does not exist")

		# delete network object
		self.netObjList.remove(netObj)
		del netObj

class DbusNetworkObject(dbus.service.Object):

	def __init__(self, uid, nid, networkId, networkType):
		self.uid = uid
		self.nid = nid
		self.networkId = networkId
		self.networkType = networkType

		if self.networkType == "bridge":
			self.netObj = VirtNetworkBridge(self.uid)
		elif self.networkType == "nat":
			self.netObj = VirtNetworkNat(self.uid)
		elif self.networkType == "route":
			self.netObj = VirtNetworkRoute(self.uid)
		elif self.networkType == "isolate":
			self.netObj = VirtNetworkIsolate(self.uid)
		else:
			raise Exception("invalid networkType %s"%(networkType))

		self.vmIdDict = dict()		# vmName -> vmId
		self.vmsObjList = []

		bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/Networks/%s'%(self.networkId))

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='s', out_signature='i')
	def AddVm(self, vmName, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		if self.connection.get_unix_user(sender) != self.uid:
			raise Exception("priviledge violation")
		uid = self.connection.get_unix_user(sender)

		# find existing vm object
		if vmName in self.vmIdDict:
			raise Exception("virt-machine already exists")

		# allocate vmId
		vmId = 0
		if len(self.vmIdDict.values()) > 0:
			vmId = max(self.vmIdDict.values()) + 1

		# do job
		self.netObj.addVm(vmId)
		self.vmsObjList.append(DbusVmServiceObj(uid, self.networkId, vmId))
		self.vmIdDict[vmName] = vmId

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i')
	def DeleteVm(self, vmId, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		if self.connection.get_unix_user(sender) != self.uid:
			raise Exception("priviledge violation")
		uid = self.connection.get_unix_user(sender)

		# find existing vm object
		if vmId not in self.vmIdDict.values():
			raise Exception("virt-machine does not exist")

		# do job
		for vms in self.vmsObjList:
			if vms.vmId == vmId:
				self.vmsObjList.remove(vms)
				del vms
				break

		self.netObj.removeVm(vmId)

		for k in self.vmIdDict:
			if self.vmIdDict[k] == vmId:
				del self.vmIdDict[k]
				break

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i', out_signature='s')
	def GetTapInterface(self, vmId, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		if self.connection.get_unix_user(sender) != self.uid:
			raise Exception("priviledge violation")
		uid = self.connection.get_unix_user(sender)

		# find existing vm object
		if vmId not in self.vmIdDict.values():
			raise Exception("virt-machine does not exist")

		# do job
		return self.netObj.getTapInterface(vmId)

class DbusVmServiceObj(dbus.service.Object):

	def __init__(self, uid, networkId, vmId):
		self.uid = uid
		self.networkId = networkId
		self.vmId = vmId
		self.sambaObj = VirtSambaServer()

		bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/Networks/%s/VmServices/%d'%(self.networkId, self.vmId))

	@dbus.service.method('org.fpemud.VirtService.Network.VmService', sender_keyword='sender',
	                     in_signature='b')
	def SambaSetEnable(self, onOff, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		if self.connection.get_unix_user(sender) != self.uid:
			raise Exception("priviledge violation")
		uid = self.connection.get_unix_user(sender)

		assert False

	@dbus.service.method('org.fpemud.VirtService.Network.VmService', sender_keyword='sender',
	                     out_signature='s')
	def SambaGetAccount(self, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		if self.connection.get_unix_user(sender) != self.uid:
			raise Exception("priviledge violation")
		uid = self.connection.get_unix_user(sender)

		assert False

	@dbus.service.method('org.fpemud.VirtService.Network.VmService', sender_keyword='sender',
	                     in_signature='ssb')
	def SambaAddShare(self, shareName, srcPath, readonly, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		if self.connection.get_unix_user(sender) != self.uid:
			raise Exception("priviledge violation")
		uid = self.connection.get_unix_user(sender)

		assert False

	@dbus.service.method('org.fpemud.VirtService.Network.VmService', sender_keyword='sender',
	                     in_signature='s')
	def SambaDeleteShare(self, shareName, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		if self.connection.get_unix_user(sender) != self.uid:
			raise Exception("priviledge violation")
		uid = self.connection.get_unix_user(sender)

		assert False

