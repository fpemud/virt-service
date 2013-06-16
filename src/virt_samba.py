#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
from virt_util import VirtUtil

class VirtSambaServer:
	"""VirtSambaServer can access the private member of VirtNetworkNat or VirtNetworkRoute"""

    def __init__(self):
		pass
#		assert netObj.__class__.__name__ in ["VirtNetworkNat", "VirtNetworkRoute"]		# use this method to workaround the cycle dependency
#		self.netObj = netObj

	def setEnable(self, onOff):
		pass

	def addShare(self, vmName, shareName, srcPath, readonly):
		pass

	def removeShare(self, vmName, shareName):
		pass

	def getAccountInfo(self, vmName):
		pass
