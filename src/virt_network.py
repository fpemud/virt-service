#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
from virt_util import VirtUtil

class VirtNetworkBridge:

	def __init__(self, netId):
		self.netId = netId
		self.brname = "vnb%d"%(self.netId)

		self.mainIntfList = []
		self.tapDict = dict()
		self.bActive = False

	def addMainInterface(self, ifName):
		self.mainIntfList.append(ifName)
		if self.bActive:
			VirtUtil.shell('/sbin/brctl addif "%s" "%s"'%(self.brname, ifName))

	def removeMainInterface(self, ifName):
		if self.bActive:
			VirtUtil.shell('/sbin/brctl delif "%s" "%s"'%(self.brname, ifName))
		self.mainIntfList.remove(ifName)

	def addVm(self, vmId):
		assert vmId not in self.tapDict

		if len(self.tapDict) == 0:
			self._createNetwork()

		tapname = "%s.%d"%(self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
		self._addTapInterface(tapname)
		self.tapDict[vmId] = tapname

	def removeVm(self, vmId):
		assert vmId in self.tapDict

		tapname = self.tapDict[vmId]
		self._removeTapInterface(tapname)
		del self.tapDict[vmId]

		if len(self.tapDict) == 0:
			self._destroyNetwork()

	def getTapInterface(self, vmId):
		return self.tapDict[vmId]

	def _createNetwork(self):
		assert not self.bActive

		VirtUtil.shell('/sbin/brctl addbr "%s"'%(self.brname))
		for mi in self.mainIntfList:
			VirtUtil.shell('/sbin/brctl addif "%s" "%s"'%(self.brname, mi))
		self.bActive = True

	def _destroyNetwork(self):
		assert self.bActive

		for mi in self.mainIntfList:
			VirtUtil.shell('/sbin/brctl delif "%s" "%s"'%(self.brname, mi))
		VirtUtil.shell('/bin/ifconfig "%s" down'%(self.brname))
		VirtUtil.shell('/sbin/brctl delbr "%s"'%(self.brname))
		self.bActive = False

	def _addTapInterface(self, tapname):
		VirtUtil.shell('/usr/sbin/openvpn --mktun --dev "%s"'%(tapname))
		VirtUtil.shell('/sbin/brctl addif "%s" "%s"'%(self.brname, tapname))

	def _removeTapInterface(self, tapname):
		VirtUtil.shell('/sbin/brctl delif "%s" "%s"'%(self.brname, tapname))
		VirtUtil.shell('/usr/sbin/openvpn --rmtun --dev "%s"'%(tapname))

class VirtNetworkNat:

	def __init__(self, netId):
		self.netId = netId
		self.netip = "10.%d.%d.0"%(self.netId / 256, self.netId % 256)
		self.netmask = "255.255.255.0"

		self.brname = "vnn%d"%(self.netId)
		self.brmac = "00:50:00:%02d:%02d"%(self.netId / 256, self.netId % 256)
		self.brip = "10.%d.%d.1"%(self.netId / 256, self.netId % 256)

		self.mainIntfList = []
		self.tapDict = dict()
		self.bActive = False

	def addMainInterface(self, ifName):
		self.mainIntfList.append(ifName)
		if self.bActive:
			VirtUtil.shell('/sbin/brctl addif "%s" "%s"'%(self.brname, ifName))

	def removeMainInterface(self, ifName):
		if self.bActive:
			VirtUtil.shell('/sbin/brctl delif "%s" "%s"'%(self.brname, ifName))
		self.mainIntfList.remove(ifName)

	def addVm(self, vmId):
		assert vmId not in self.tapDict

		if len(self.tapDict) == 0:
			self._createNetwork()

		tapname = "%s.%d"%(self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
		self._addTapInterface(tapname)
		self.tapDict[vmId] = tapname

	def removeVm(self, vmId):
		assert vmId in self.tapDict

		tapname = self.tapDict[vmId]
		self._removeTapInterface(tapname)
		del self.tapDict[vmId]

		if len(self.tapDict) == 0:
			self._destroyNetwork()

	def getTapInterface(self, vmId):
		return self.tapDict[vmId]

	def _createNetwork(self):
		assert not self.bActive

		VirtUtil.shell('/sbin/brctl addbr "%s"'%(self.brname))
		VirtUtil.shell('/bin/ifconfig "%s" hw ether "%s"'%(self.brname, self.brmac))
		VirtUtil.shell('/bin/ifconfig "%s" "%s" netmask "%s"'%(self.brname, self.brip, self.netmask))
		self.bActive = True

	def _destroyNetwork(self):
		assert self.bActive

		VirtUtil.shell('/bin/ifconfig "%s" down'%(self.brname))
		VirtUtil.shell('/sbin/brctl delbr "%s"'%(self.brname))
		self.bActive = False

	def _addTapInterface(self, tapname):
		VirtUtil.shell('/usr/sbin/openvpn --mktun --dev "%s"'%(tapname))
		VirtUtil.shell('/sbin/brctl addif "%s" "%s"'%(self.brname, tapname))

	def _removeTapInterface(self, tapname):
		VirtUtil.shell('/sbin/brctl delif "%s" "%s"'%(self.brname, tapname))
		VirtUtil.shell('/usr/sbin/openvpn --rmtun --dev "%s"'%(tapname))

#	def _genIptableRulesFirewall(self):
#		return
#
#	def _genIptableRulesNat(self):
#		return
#
#	def _addIptableRules(self):
#		VirtUtil.shell('/sbin/iptables -t nat -A POSTROUTING -s %s/%s -j MASQUERADE'%(self.netip, self.netmask))
#		return
#
#	def _removeIptableRules(self):
#		VirtUtil.shell('/sbin/iptables -t nat -D POSTROUTING -s %s/%s -j MASQUERADE'%(self.netip, self.netmask))
#		return

class VirtNetworkRoute:
	def __init__(self, netId):
		self.netId = netId
		self.brname = "vnr%d"%(self.netId)

class VirtNetworkIsolate:

	def __init__(self, netId):
		self.netId = netId
		self.brname = "vni%d"%(self.netId)				# it's a virtual bridge interface
		self.tapDict = dict()

	def addVm(self, vmId):
		assert vmId not in self.tapDict

		tapname = "%s.%d"%(self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
		VirtUtil.shell('/usr/sbin/openvpn --mktun --dev "%s"'%(tapname))
		self.tapDict[vmId] = tapname

	def removeVm(self, vmId):
		assert vmId in self.tapDict

		tapname = self.tapDict[vmId]
		VirtUtil.shell('/usr/sbin/openvpn --rmtun --dev "%s"'%(tapname))
		del self.tapDict[vmId]

	def getTapInterface(self, vmId):
		return self.tapDict[vmId]

