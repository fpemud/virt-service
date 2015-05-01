#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import subprocess
from virt_util import VirtUtil


class VirtDhcpServer:

    """If there's a global dnsmasq server, then use that server, else we start a new dnsmasq server
       Use one server to serve all the networks"""
    """But, now we only support local dnsmasq server, and use one server to serve one network"""

    def __init__(self, param):
        self.param = param
        self.networkDict = dict()
        self.serverObjDict = dict()

    def release(self):
        assert len(self.networkDict) == 0

    def addNetwork(self, nid, serverPort, serverIp, netip, netmask):
        assert netip.endswith(".0")
        assert netmask == "255.255.255.0"
        assert serverIp.endswith(".1")

        self.networkDict[nid] = _NetworkInfo(serverPort, serverIp, netip, netmask)
        self.serverObjDict[nid] = _ServerLocal(self, nid)

    def removeNetwork(self, nid):
        serverObj = self.serverObjDict.pop(nid)
        serverObj.release()
        self.networkDict.pop(nid)


class _NetworkInfo:

    def __init__(self, serverPort, serverIp, netip, netmask):
        self.serverPort = serverPort
        self.serverIp = serverIp
        self.netip = netip
        self.netmask = netmask


class _ServerLocal:

    def __init__(self, pObj, nid):
        self.param = pObj.param
        self.nid = nid
        self.netInfo = pObj.networkDict[self.nid]

        self.confFile = os.path.join(self.param.netManager.nidGetTmpDir(self.nid), "dnsmasq.conf")
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
        buf += "bind-interfaces\n"
        buf += "except-interface=lo\n"                        # don't listen on 127.0.0.1
        buf += "interface=%s\n" % (self.netInfo.serverPort)
        buf += "listen-address=%s\n" % (self.netInfo.serverIp)
        buf += "dhcp-range=%s,static,%s\n" % (self.netInfo.netip, self.netInfo.netmask)
        for sid in range(1, 128 + 1):
            macaddr = self.param.netManager.nidGetVmMac(self.nid, sid)
            ipaddr = self.param.netManager.nidGetVmIp(self.nid, sid)
            buf += "dhcp-host=%s,%s\n" % (macaddr, ipaddr)

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

#    def _startServer(self):
#        try:
#            os.mkdir(self.servDir)
#            self._genDnsmasqCfgFile(self.confFile)
#            self.serverProc = subprocess.Popen(self._genDnsmasqCommand(), shell = True)
#        except:
#            shutil.rmtree(self.servDir)
#            raise
#
#    def _stopServer(self):
#        self.serverProc.terminate()
#        self.serverProc.wait()
#        self.serverProc = None
#        shutil.rmtree(self.servDir)
#
#    def _restartServer(self):
#        self.serverProc.terminate()
#        self.serverProc.wait()
#        self.serverProc = None
#
#        try:
#            self._genDnsmasqCfgFile()
#            self.serverProc = subprocess.Popen(self._genDnsmasqCommand(), shell = True)
#        except:
#            shutil.rmtree(self.servDir)
#            raise
#
#        self.servDir = os.path.join(tmpDir, str(uid), str(nid), "dnsmasq")
#        self.confFile = os.path.join(self.servDir, "dnsmasq.conf")
#        self.leaseFile = os.path.join(self.servDir, "dnsmasq.leases")
#
#
#    def _genDnsmasqCfgFile(self):
#
#        buf = ""
#        buf += "strict-order\n"
#        buf += "bind-interfaces\n"
# buf += "except-interface=lo\n"                        # don't listen on 127.0.0.1
#        buf += "\n"
#        for key, value in self.networkDict.items():
#            uid, nid = key
#            buf += "interface=%s"%(value.serverPort)
#            buf += "listen-address=%s\n"%(value.serverIp)
#            buf += "dhcp-range=%s/%s,static\n"%(value.netip, value.netmask)
#            for vmId in range(0, 32):
#                macaddr = VirtUtil.getVmMacAddress(self.param.macOuiVm, uid, nid, vmId)
#                ipaddr = VirtUtil.getVmIpAddress(self.param.ip1, uid, nid, vmId)
#                buf += "dhcp-host=%s,%s\n"%(macaddr, ipaddr)
#            buf += "\n"
#
#        VirtUtil.writeFile(self.confFile, buf)
#
#    def _genDnsmasqCommand(self):
#
# no pid-file, no lease-file
# dnsmasq polls /etc/resolv.conf to get the dns change, it's good :)
#        cmd = "/sbin/dnsmasq"
# cmd += " --keep-in-foreground"                        # don't run as daemon, so we can control it
#        cmd += " --no-hosts"
#        cmd += " --dhcp-no-override"
#        cmd += " --conf-file=\"%s\""%(self.confFile)
#        cmd += " --dhcp-leasefile=\"%s\""%(self.leaseFile)
#        cmd += " --pid-file"
#        return cmd
