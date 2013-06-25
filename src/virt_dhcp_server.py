#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import subprocess
from virt_util import VirtUtil

class VirtDhcpServer:
	"""VirtDhcpServer is implemented by dnsmasq"""

    def __init__(self, serverPort, serverIp, netip, netmask):
		assert netip.endswith(".0")
		assert netmask == "255.255.255.0"
		assert serverIp.endswith(".1")

		self.serverPort = serverPort
		self.serverIp = serverIp
		self.netip = netip
		self.netmask = netmask
		self.serverProc = None

	def enableServer(self):
		assert self.serverProc is None

		dnsmasqCmd = self._genDnsmasqCommand()
		self.serverProc = subprocess.Popen(dnsmasqCmd, shell = True)

	def disableServer(self):
		if self.serverProc is not None:
			self.serverProc.terminate()
			self.serverProc.wait()
			self.serverProc = None

	def _genDnsmasqCommand(self):
		ipStart = self.netip[:-2] + ".2"
		ipEnd = self.netip[:-2] + ".254"

		# no pid-file, no lease-file
		# dnsmasq polls /etc/resolv.conf to get the dns change, it's good :)
		cmd = "/sbin/dnsmasq"
		cmd += " --keep-in-foreground"						# don't run as daemon, so we can control it
		cmd += " --strict-order"
		cmd += " --except-interface=lo"						# don't listen on 127.0.0.1
		cmd += " --interface=%s"%(self.serverPort)
		cmd += " --listen-address=%s"%(self.serverIp)
		cmd += " --bind-interfaces"
		cmd += " --dhcp-range=%s,%s"%(ipStart, ipEnd)
		cmd += " --conf-file=\"\""
		cmd += " --pid-file"
		cmd += " --dhcp-no-override"
		return cmd

