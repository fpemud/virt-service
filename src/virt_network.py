#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
from virt_util import VirtUtil
from virt_host_network import VirtHostNetworkEventCallback


class VirtNetworkBridge(VirtHostNetworkEventCallback):

    def __init__(self, param, uid, nid):
        self.param = param
        self.uid = uid
        self.nid = nid
        self.brname = "vnb%d" % (self.uid)
        self.mainIntfList = []
        self.tapDict = dict()

        VirtUtil.shell('/sbin/brctl addbr "%s"' % (self.brname))
        VirtUtil.shell('/bin/ifconfig "%s" up' % (self.brname))

    def release(self):
        assert len(self.tapDict) == 0
        VirtUtil.shell('/bin/ifconfig "%s" down' % (self.brname))
        VirtUtil.shell('/sbin/brctl delbr "%s"' % (self.brname))

    def onActiveInterfaceAdd(self, ifName):
        # some interface like wlan0 has no bridging capbility, we ignore them
        # fixme: how to send this error to user?
        ret, dummy = VirtUtil.shell('/sbin/brctl addif "%s" "%s"' % (self.brname, ifName), "retcode+stdout")
        if ret == 0:
            self.mainIntfList.append(ifName)

    def onActiveInterfaceRemove(self, ifName):
        if ifName in self.mainIntfList:
            VirtUtil.shell('/sbin/brctl delif "%s" "%s"' % (self.brname, ifName))
            self.mainIntfList.remove(ifName)

    def addVm(self, vmId):
        assert vmId not in self.tapDict

        tapname = "%s.%d" % (self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
        VirtUtil.shell('/bin/ip tuntap add dev "%s" mode tap' % (tapname))
        VirtUtil.shell('/sbin/brctl addif "%s" "%s"' % (self.brname, tapname))
        VirtUtil.shell('/bin/ifconfig "%s" up' % (tapname))
        self.tapDict[vmId] = tapname

    def removeVm(self, vmId):
        assert vmId in self.tapDict

        tapname = self.tapDict[vmId]
        VirtUtil.shell('/bin/ifconfig "%s" down' % (tapname))
        VirtUtil.shell('/sbin/brctl delif "%s" "%s"' % (self.brname, tapname))
        VirtUtil.shell('/bin/ip tuntap del dev "%s" mode tap' % (tapname))
        del self.tapDict[vmId]

    def getTapInterface(self, vmId):
        return self.tapDict[vmId]


class VirtNetworkNat(VirtHostNetworkEventCallback):

    def __init__(self, param, uid, nid):
        self.param = param
        self.uid = uid
        self.nid = nid
        self.netip = "10.%d.%d.0" % (self.uid / 256, self.uid % 256)
        self.netmask = "255.255.255.0"

        self.brname = "vnn%d" % (self.uid)
        self.brmac = "00:50:00:%02d:%02d" % (self.uid / 256, self.uid % 256)
        self.brip = "10.%d.%d.1" % (self.uid / 256, self.uid % 256)

        self.mainIntfList = []
        self.tapDict = dict()

        VirtUtil.shell('/sbin/brctl addbr "%s"' % (self.brname))
        VirtUtil.shell('/bin/ifconfig "%s" hw ether "%s"' % (self.brname, self.brmac))
        VirtUtil.shell('/bin/ifconfig "%s" "%s" netmask "%s"' % (self.brname, self.brip, self.netmask))
        VirtUtil.shell('/bin/ifconfig "%s" up' % (self.brname))
        self._addNftNatRule(self.netip, self.netmask)

    def release(self):
        assert len(self.tapDict) == 0

        self._removeNftNatRule(self.netip, self.netmask)
        VirtUtil.shell('/bin/ifconfig "%s" down' % (self.brname))
        VirtUtil.shell('/sbin/brctl delbr "%s"' % (self.brname))

    def onActiveInterfaceAdd(self, ifName):
        self.mainIntfList.append(ifName)

    def onActiveInterfaceRemove(self, ifName):
        self.mainIntfList.remove(ifName)

    def addVm(self, vmId):
        assert vmId not in self.tapDict

        tapname = "%s.%d" % (self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
        VirtUtil.shell('/bin/ip tuntap add dev "%s" mode tap' % (tapname))
        VirtUtil.shell('/sbin/brctl addif "%s" "%s"' % (self.brname, tapname))
        VirtUtil.shell('/bin/ifconfig "%s" up' % (tapname))
        self.tapDict[vmId] = tapname

    def removeVm(self, vmId):
        assert vmId in self.tapDict

        tapname = self.tapDict[vmId]
        VirtUtil.shell('/bin/ifconfig "%s" down' % (tapname))
        VirtUtil.shell('/sbin/brctl delif "%s" "%s"' % (self.brname, tapname))
        VirtUtil.shell('/bin/ip tuntap del dev "%s" mode tap' % (tapname))
        del self.tapDict[vmId]

    def getTapInterface(self, vmId):
        return self.tapDict[vmId]

    def _addNftNatRule(self, netip, netmask):
        # create table
        rc, msg = VirtUtil.shell('/sbin/nft list table virt-service-nat', "retcode+stdout")
        if rc != 0:
            VirtUtil.shell('/sbin/nft add table ip virt-service-nat')
            VirtUtil.shell('/sbin/nft add chain virt-service-nat prerouting { type nat hook prerouting priority 0 \\; }')
            VirtUtil.shell('/sbin/nft add chain virt-service-nat postrouting { type nat hook postrouting priority 0 \\; }')

        # create rule
        VirtUtil.shell('/sbin/nft add rule virt-service-nat postrouting ip saddr %s/%s masquerade' % (netip, VirtUtil.ipMaskToLen(netmask)))

    def _removeNftNatRule(self, netip, netmask):
        # table must be there
        assert re.search("^table virt-service-nat$", VirtUtil.shell('/sbin/nft list tables', "stdout"), re.M) is not None

        # delete my rule
        msg = VirtUtil.shell('/sbin/nft list table virt-service-nat -a', "stdout")
        m = re.search("^.* %s/%s .* # handle ([0-9]+)$" % (netip, VirtUtil.ipMaskToLen(netmask)), msg, re.M)
        if m is not None:
            VirtUtil.shell('/sbin/nft delete rule virt-service-nat postrouting handle %s' % (m.group(1)))

        # delete table if no rules left
        msg = VirtUtil.shell('/sbin/nft list table virt-service-nat -a', "stdout")
        m = re.search("handle [0-9]+", msg, re.M)
        if m is None:
            VirtUtil.shell('/sbin/nft delete table virt-service-nat')


class VirtNetworkRoute(VirtHostNetworkEventCallback):

    def __init__(self, param, uid, nid):
        self.param = param
        self.uid = uid
        self.nid = nid
        self.brname = "vnr%d" % (self.uid)

    def release(self):
        pass

    def onActiveInterfaceAdd(self, ifName):
        assert False

    def onActiveInterfaceRemove(self, ifName):
        assert False


class VirtNetworkIsolate:

    def __init__(self, param, uid, nid):
        self.param = param
        self.uid = uid
        self.nid = nid
        self.brname = "vni%d" % (self.uid)                # it's a virtual bridge interface
        self.tapDict = dict()

    def release(self):
        pass

    def addVm(self, vmId):
        assert vmId not in self.tapDict

        tapname = "%s.%d" % (self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
        VirtUtil.shell('/bin/ip tuntap add dev "%s" mode tap' % (tapname))
        self.tapDict[vmId] = tapname

    def removeVm(self, vmId):
        assert vmId in self.tapDict

        tapname = self.tapDict[vmId]
        VirtUtil.shell('/bin/ip tuntap del dev "%s" mode tap' % (tapname))
        del self.tapDict[vmId]

    def getTapInterface(self, vmId):
        return self.tapDict[vmId]
