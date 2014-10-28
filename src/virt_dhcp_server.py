#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
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

    def addNetwork(self, uid, nid, serverPort, serverIp, netip, netmask):
        assert netip.endswith(".0")
        assert netmask == "255.255.255.0"
        assert serverIp.endswith(".1")

        # add network info
        key = (uid, nid)
        value = _NetworkInfo(serverPort, serverIp, netip, netmask)
        self.networkDict[key] = value

        # create server object
        key = (uid, nid)
        severObj = _ServerLocal(self, uid, nid)
        self.serverObjDict[key] = severObj

    def removeNetwork(self, uid, nid):
        # remove server object
        key = (uid, nid)
        serverObj = self.serverObjDict.pop(key)
        serverObj.release()

        # remove network info
        key = (uid, nid)
        self.networkDict.pop(key)


class _NetworkInfo:

    def __init__(self, serverPort, serverIp, netip, netmask):
        self.serverPort = serverPort
        self.serverIp = serverIp
        self.netip = netip
        self.netmask = netmask


class _ServerLocal:

    def __init__(self, pObj, uid, nid):
        self.param = pObj.param
        self.pObj = pObj        # parent object
        self.uid = uid
        self.nid = nid

        self.servDir = os.path.join(self.param.tmpDir, str(self.uid), str(self.nid), "dnsmasq")
        self.confFile = os.path.join(self.servDir, "dnsmasq.conf")
        self.serverProc = None

        try:
            os.mkdir(self.servDir)
            self._genDnsmasqCfgFile()
            self.serverProc = subprocess.Popen(self._genDnsmasqCommand(), shell=True)
        except:
            shutil.rmtree(self.servDir)
            raise

    def release(self):
        self.serverProc.terminate()
        self.serverProc.wait()
        self.serverProc = None
        shutil.rmtree(self.servDir)

    def _genDnsmasqCfgFile(self):

        key = (self.uid, self.nid)
        netInfo = self.pObj.networkDict[key]

        buf = ""
        buf += "strict-order\n"
        buf += "bind-interfaces\n"
        buf += "except-interface=lo\n"                        # don't listen on 127.0.0.1
        buf += "interface=%s\n" % (netInfo.serverPort)
        buf += "listen-address=%s\n" % (netInfo.serverIp)
        buf += "dhcp-range=%s,static,%s\n" % (netInfo.netip, netInfo.netmask)
        for vmId in range(0, 32):
            macaddr = VirtUtil.getVmMacAddress(self.param.macOuiVm, self.uid, self.nid, vmId)
            ipaddr = VirtUtil.getVmIpAddress(self.param.ip1, self.uid, self.nid, vmId)
            buf += "dhcp-host=%s,%s\n" % (macaddr, ipaddr)

        VirtUtil.writeFile(self.confFile, buf)

    def _genDnsmasqCommand(self):

        # no pid-file, no lease-file
        # dnsmasq polls /etc/resolv.conf to get the dns change, it's good :)
        cmd = "/sbin/dnsmasq"
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
