#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import dbus
import dbus.service
from virt_network import VirtNetworkBridge
from virt_network import VirtNetworkNat
from virt_network import VirtNetworkRoute
from virt_network import VirtNetworkIsolate
from virt_samba_server import VirtSambaServer

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
# networkId:int NewNetwork(networkType:string)
# void          DeleteNetwork(networkId:int)
#
# Signals:
#
# Notes:
#   networkType can be: bridge, nat, route
#   one user can have 8 networks, one network can have 32 virtual machines, it's caused by mac address allocation limit
#   one user can only have one network of a same type
#   service exits when the last network is deleted
#
# ==== Network ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService.Network
# Object path           /{user-id:int}/Networks/{networkId:int}
#
# Methods:
# vmId:int         AddVm(vmName:string)
# void             DeleteVm(vmId:int)
# tapifname:string GetTapInterface(vmId:int)
# macaddr:string   GetTapVmMacAddress(vmId:int)
# 
# Signals:
#
# ==== VmService ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService.Network.VmService
# Object path           /{user-id:int}/Networks/{networkId:int}/VmServices/{vmId:int}
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

	def __init__(self, mainloop, hostNetwork):
		self.mainloop = mainloop
		self.hostNetwork = hostNetwork
		self.netObjList = []

		bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService')

	def release(self):
		assert len(self.netObjList) == 0
		self.remove_from_connection()

	@dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', 
	                     in_signature='s', out_signature='i')
	def NewNetwork(self, networkType, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		uid = self.connection.get_unix_user(sender)

		# find existing network object
		for no in self.netObjList:
			if no.uid == uid and no.networkType == networkType:
				no.refCount = no.refCount + 1
				return no.nid

		# allocate network id
		nid = 0
		while True:
			found = False
			for no in self.netObjList:
				if no.uid == uid and no.nid == nid:
					found = True
			if not found:
				break
			if nid >= 7:
				raise Exception("network number limit is reached")
			nid = nid + 1
			continue

		# create new network object
		netObj = DbusNetworkObject(uid, nid, networkType, self.hostNetwork)
		netObj.refCount = 1												# fixme: strange, maintain refcount out side the object
		self.netObjList.append(netObj)

		return nid

	@dbus.service.method('org.fpemud.VirtService', sender_keyword='sender',
	                     in_signature='i')
	def DeleteNetwork(self, nid, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		uid = self.connection.get_unix_user(sender)

		# find and delete network object
		found = False
		for i in range(0, len(self.netObjList)):
			if self.netObjList[i].uid == uid and self.netObjList[i].nid == nid:
				self.netObjList[i].refCount -= 1
				if self.netObjList[i].refCount == 0:
					no = self.netObjList.pop(i)
					no.release()
				found = True
				break
		if not found:
			raise Exception("the specified network does not exist")

		# service exits when the last network is deleted
		if len(self.netObjList) == 0:
			self.mainloop.quit()

class DbusNetworkObject(dbus.service.Object):

	def __init__(self, uid, nid, networkType, hostNetwork):
		self.uid = uid
		self.nid = nid
		self.networkType = networkType
		self.hostNetwork = hostNetwork

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

		if self.networkType in ["bridge", "nat", "route"]:
			self.hostNetwork.registerEventCallback(self.netObj)

		self.vmIdDict = dict()		# vmName -> vmId
		self.vmsObjList = []

		bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/%d/Networks/%d'%(self.uid, self.nid))

	def release(self):
		assert len(self.vmIdDict) == 0
		self.remove_from_connection()

		if self.networkType in ["bridge", "nat", "route"]:
			self.hostNetwork.unregisterEventCallback(self.netObj)
		self.netObj.release()

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
		while True:
			if vmId not in self.vmIdDict.values():
				break
			if vmId >= 31:
				raise Exception("network number limit is reached")
			vmId = vmId + 1
			continue

		# add virtual machine
		self.netObj.addVm(vmId)
		self.vmsObjList.append(DbusVmServiceObj(uid, self.nid, vmId))
		self.vmIdDict[vmName] = vmId

		return vmId

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
		for i in range(0, len(self.vmsObjList)):
			if self.vmsObjList[i].uid == uid and self.vmsObjList[i].vmId == vmId:
				vo = self.vmsObjList.pop(i)
				vo.release()
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

		# get tap interface
		return self.netObj.getTapInterface(vmId)

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i', out_signature='s')
	def GetTapVmMacAddress(self, vmId, sender=None):
		# get user id
		if sender is None:
			raise Exception("only accept user access")
		if self.connection.get_unix_user(sender) != self.uid:
			raise Exception("priviledge violation")
		uid = self.connection.get_unix_user(sender)

		# find existing vm object
		if vmId not in self.vmIdDict.values():
			raise Exception("virt-machine does not exist")

		# get mac address for virtual machine
		# this mac address is not the same as the mac address of the tap interface
		assert self.nid < 8 and vmId < 32
		macOuiVm = "00:50:01"
		mac4 = uid / 256
		mac5 = uid % 256
		mac6 = self.nid * 32 + vmId
		return "%s:%02x:%02x:%02x"%(macOuiVm, mac4, mac5, mac6)

class DbusVmServiceObj(dbus.service.Object):

	def __init__(self, uid, nid, vmId):
		self.uid = uid
		self.nid = nid
		self.vmId = vmId
		self.sambaObj = VirtSambaServer()

		bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/%d/Networks/%d/VmServices/%d'%(self.uid, self.nid, self.vmId))

	def release(self):
		self.remove_from_connection()

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

