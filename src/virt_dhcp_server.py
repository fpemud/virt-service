#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import subprocess
from virt_util import VirtUtil
from virt_param import VirtInitializationError


class VirtDhcpServer:

    def __init__(self, param):
        self.param = param
        self.serverObjDict = dict()

        if not os.path.exists("/usr/sbin/dnsmasq"):
            raise VirtInitializationError("/usr/sbin/dnsmasq not found")
        if VirtUtil.isSocketPortUsed("tcp", 53):
            raise VirtInitializationError("TCP port 53 has been already used")
        if VirtUtil.isSocketPortUsed("udp", 53):
            raise VirtInitializationError("UDP port 53 has been already used")

    def release(self):
        assert len(self.serverObjDict) == 0

    def startOnNetwork(self, netObj):
        self.serverObjDict[netObj] = _ServerLocal(self, netObj)

    def stopOnNetwork(self, netObj):
        serverObj = self.serverObjDict.pop(netObj)
        serverObj.release()


class _ServerLocal:

    def __init__(self, pObj, netObj):
        assert netObj.netip.endswith(".0")
        assert netObj.netmask == "255.255.255.0"
        assert netObj.brip.endswith(".1")

        self.param = pObj.param
        self.netObj = netObj
        self.confFile = os.path.join(self.netObj.getTmpDir(), "dnsmasq.conf")
        self.serverProc = None

        self._genDnsmasqCfgFile()
        self.serverProc = subprocess.Popen(self._genDnsmasqCommand(), shell=True)

    def release(self):
        self.serverProc.terminate()
        self.serverProc.wait()
        self.serverProc = None

    def _genDnsmasqCfgFile(self):
        buf = ""
        buf += "strict-order\n"
        buf += "bind-interfaces\n"                            # don't listen on 0.0.0.0
        buf += "except-interface=lo\n"                        # don't listen on 127.0.0.1
        buf += "interface=%s\n" % (self.netObj.brname)
        buf += "listen-address=%s\n" % (self.netObj.brip)
        buf += "dhcp-range=%s,static,%s\n" % (self.netObj.netip, self.netObj.netmask)
        for sid in range(1, 128 + 1):
            buf += "dhcp-host=%s,%s\n" % (self.netObj.getVmMac(sid), self.netObj.getVmIp(sid))
        VirtUtil.writeFile(self.confFile, buf)

    def _genDnsmasqCommand(self):
        # no pid-file, no lease-file
        # dnsmasq polls /etc/resolv.conf to get the dns change, it's good :)
        cmd = "/usr/sbin/dnsmasq"
        cmd += " --keep-in-foreground"                        # don't run as daemon, so we can control it
        cmd += " --conf-file=\"%s\"" % (self.confFile)
        cmd += " --pid-file"
        cmd += " --dhcp-no-override"
        return cmd
