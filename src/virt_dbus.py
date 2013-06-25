#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import dbus
import dbus.service
from virt_util import VirtUtil
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
# void             SambaEnable()
# void             SambaDisable()
# account:string   SambaGetAccount()
# void             SambaAddShare(shareName:string, srcPath:string, readonly:boolean)
# void             SambaDeleteShare(shareName:string)
# 
# Signals:
#

class VirtServiceException(dbus.DBusException):
    _dbus_error_name = 'org.fpemud.VirtService.Exception'

class DbusMainObject(dbus.service.Object):

	def __init__(self, param):
		self.param = param
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
		uid = VirtUtil.dbusGetUserId(self.connection, sender)

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
		netObj = DbusNetworkObject(self.param, uid, nid, networkType)
		netObj.refCount = 1												# fixme: strange, maintain refcount out side the object
		self.netObjList.append(netObj)

		return nid

	@dbus.service.method('org.fpemud.VirtService', sender_keyword='sender',
	                     in_signature='i')
	def DeleteNetwork(self, nid, sender=None):
		# get user id
		uid = VirtUtil.dbusGetUserId(self.connection, sender)

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
			self.param.mainloop.quit()

class DbusNetworkObject(dbus.service.Object):

	def __init__(self, param, uid, nid, networkType):
		self.param = param
		self.uid = uid
		self.nid = nid
		self.networkType = networkType

		# create network temp directory
		os.makedirs(os.path.join(self.param.tmpDir, str(self.uid), str(self.nid)))

		# create network object
		if self.networkType == "bridge":
			self.netObj = VirtNetworkBridge(self.param, self.uid, self.nid)
		elif self.networkType == "nat":
			self.netObj = VirtNetworkNat(self.param, self.uid, self.nid)
		elif self.networkType == "route":
			self.netObj = VirtNetworkRoute(self.param, self.uid, self.nid)
		elif self.networkType == "isolate":
			self.netObj = VirtNetworkIsolate(self.param, self.uid, self.nid)
		else:
			raise Exception("invalid networkType %s"%(networkType))

		# register host network callback
		if self.networkType in ["bridge", "nat", "route"]:
			self.param.hostNetwork.registerEventCallback(self.netObj)

		# create data structure
		self.vmIdDict = dict()		# vmName -> vmId

		# register dbus object path
		bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
		dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/%d/Networks/%d'%(self.uid, self.nid))

	def release(self):
		assert len(self.vmIdDict) == 0

		# deregister dbus object path
		self.remove_from_connection()

		# deregister host network callback
		if self.networkType in ["bridge", "nat", "route"]:
			self.param.hostNetwork.unregisterEventCallback(self.netObj)

		# release network object
		self.netObj.release()

		# delete network temp directory
		shutil.rmtree(os.path.join(self.param.tmpDir, str(self.uid), str(self.nid)))

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='s', out_signature='i')
	def AddVm(self, vmName, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# find existing vm object
		if vmName in self.vmIdDict:
			raise Exception("virt-machine already exists")

		# allocate vmId
		vmId = 0
		while True:
			if vmId not in self.vmIdDict.values():
				break
			if vmId >= 31:
				raise Exception("virtual machine number limit is reached")
			vmId = vmId + 1
			continue

		# add virtual machine
		self.netObj.addVm(vmId)
		self.vmIdDict[vmName] = vmId

		return vmId

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i')
	def DeleteVm(self, vmId, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# find existing vm object
		if vmId not in self.vmIdDict.values():
			raise Exception("virt-machine does not exist")

		self.netObj.removeVm(vmId)

		for k in self.vmIdDict:
			if self.vmIdDict[k] == vmId:
				del self.vmIdDict[k]
				break

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i', out_signature='s')
	def GetTapInterface(self, vmId, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# find existing vm object
		if vmId not in self.vmIdDict.values():
			raise Exception("virt-machine does not exist")

		# get tap interface
		return self.netObj.getTapInterface(vmId)

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='i', out_signature='s')
	def GetTapVmMacAddress(self, vmId, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# find existing vm object
		if vmId not in self.vmIdDict.values():
			raise Exception("virt-machine does not exist")

		# get mac address for virtual machine
		# this mac address is not the same as the mac address of the tap interface
		assert self.nid < 8 and vmId < 32
		macOuiVm = "00:50:01"
		mac4 = self.uid / 256
		mac5 = self.uid % 256
		mac6 = self.nid * 32 + vmId
		return "%s:%02x:%02x:%02x"%(macOuiVm, mac4, mac5, mac6)

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='')
	def SambaEnable(self, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# check networkType
		if not isinstance(netObj, VirtNetworkNat):
			raise Exception("only network type NAT support samba server")

		if not self.netObj.getSambaServer().isServerEnabled():
			self.netObj.getSambaServer().enableServer()

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='')
	def SambaDisable(self, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# check networkType
		if not isinstance(netObj, VirtNetworkNat):
			raise Exception("only network type NAT support samba server")

		self.netObj.getSambaServer().disableServer()

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     out_signature='s')
	def SambaGetAccount(self, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# check networkType
		if not isinstance(netObj, VirtNetworkNat):
			raise Exception("only network type NAT support samba server")

		return self.netObj.getSambaServer().getAccountInfo()

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='issb')
	def SambaAddShare(self, vmId, shareName, srcPath, readonly, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# check networkType
		if not isinstance(netObj, VirtNetworkNat):
			raise Exception("only network type NAT support samba server")

		return self.netObj.addShare(vmId, shareName, srcPath, readonly)

	@dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
	                     in_signature='is')
	def SambaDeleteShare(self, vmId, shareName, sender=None):
		# check user id
		VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

		# check networkType
		if not isinstance(netObj, VirtNetworkNat):
			raise Exception("only network type NAT support samba server")

		return self.netObj.removeShare(vmId, shareName)


