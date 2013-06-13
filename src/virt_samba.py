#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
from virt_util import VirtUtil
from virt_network import VirtNetworkNat

class VirtSambaServer:
	"""VirtSambaServer can access the private member of VirtNetworkNat"""

    def __init__(self, netObj):
		assert isinstance(netObj, VirtNetworkNat)
		self.netObj = netObj

	def addShare(self, vmName, shareName, srcPath, readonly):
		pass

	def removeShare(self, vmName, shareName):
		pass

	def getAccountInfo(self, vmName):
		pass
