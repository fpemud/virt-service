#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
from virt_util import VirtUtil
from virt_param import VirtInitializationError
from virt_host_network import VirtHostNetworkEventCallback


class VirtNetworkManager:

    def __init__(self, param):
        self.param = param
        self.macOui = "00:50:01"
        self.ip1 = 10
        self.minIpNumber = 11       # IP X.X.X.0 ~ X.X.X.10 are reserved
        self.netDict = dict()       # { userId: { netName: netObj, netName2: netObj2, ... }, userId2: { ... }, ... }

        if not os.path.exists("/sbin/brctl"):
            raise VirtInitializationError("/sbin/brctl not found")
        if not os.path.exists("/bin/ifconfig"):
            raise VirtInitializationError("/bin/ifconfig not found")
        if not os.path.exists("/bin/ip"):
            raise VirtInitializationError("/bin/ip not found")
        if not os.path.exists("/sbin/nft"):
            raise VirtInitializationError("/sbin/nft not found")

    def release(self):
        assert len(self.netDict) == 0

    def addNetwork(self, uid, networkName):
        assert self._validateNetworkName(networkName)

        if uid in self.netDict and networkName in self.netDict[uid]:
            # network object already exists, add reference count
            self.netDict[uid][networkName].refcount += 1
        else:
            # create a new network object
            if uid not in self.netDict:
                self.netDict[uid] = dict()
            if networkName == "bridge":
                nobj = _NetworkBridge(self._allocId())
            elif networkName == "nat":
                nobj = _NetworkNat(self._allocId())
            elif networkName == "route":
                nobj = _NetworkRoute(self._allocId())
            elif networkName == "isolate":
                nobj = _NetworkIsolate(self._allocId())
            else:
                assert False
            nobj.refcount += 1
            self.netDict[uid][networkName] = nobj

            # open ipv4 forwarding, now no other program needs it, so we do a simple implementation
            VirtUtil.writeFile("/proc/sys/net/ipv4/ip_forward", "1")

            # create network temp directory
            if not os.path.exists(os.path.join(self.param.tmpDir, str(nobj.nid))):
                os.makedirs(os.path.join(self.param.tmpDir, str(nobj.nid)))

            # enable server
            if networkName in ["nat", "route"]:
                self.param.dhcpServer.addNetwork(nobj.nid, nobj.brname, nobj.brip, nobj.netip, nobj.netmask)
                self.param.sambaServer.addNetwork(nobj.nid, uid, nobj.brip, nobj.netip, nobj.netmask)

            # register host network callback
            if networkName in ["bridge", "nat", "route"]:
                self.param.hostNetwork.registerEventCallback(nobj)

    def removeNetwork(self, uid, networkName):
        assert self._validateNetworkName(networkName)

        if uid not in self.netDict or networkName not in self.netDict[uid]:
            return

        nobj = self.netDict[uid][networkName]
        nobj.refcount -= 1
        if nobj.refcount == 0:
            if networkName in ["bridge", "nat", "route"]:
                self.param.hostNetwork.unregisterEventCallback(nobj)
            if networkName in ["nat", "route"]:
                self.param.sambaServer.removeNetwork(nobj.nid)
                self.param.dhcpServer.removeNetwork(nobj.nid)
            nobj.release()
            del self.netDict[uid][networkName]
            if len(self.netDict[uid]) == 0:
                del self.netDict[uid]
            if len(self.netDict) == 0:
                VirtUtil.writeFile("/proc/sys/net/ipv4/ip_forward", "0")

    def addTapIntf(self, uid, networkName, sid):
        assert self._validateNetworkName(networkName) and self._validateResSetId(sid)
        self.netDict[uid][networkName].addTapIntf(sid)

    def removeTapIntf(self, uid, networkName, sid):
        assert self._validateNetworkName(networkName) and self._validateResSetId(sid)
        if self.netDict[uid][networkName].getTapInterface(sid) is not None:
            self.netDict[uid][networkName].removeTapIntf(sid)

    def hasTapIntf(self, uid, networkName, sid):
        assert self._validateNetworkName(networkName) and self._validateResSetId(sid)
        if uid not in self.netDict or networkName not in self.netDict[uid]:
            return False
        return self.netDict[uid][networkName].getTapInterface(sid) is not None

    def getTapIntf(self, uid, networkName, sid):
        assert self._validateNetworkName(networkName) and self._validateResSetId(sid)
        ret = self.netDict[uid][networkName].getTapInterface(sid)
        assert ret is not None
        return ret

    def getVmIp(self, uid, networkName, sid):
        assert self._validateNetworkName(networkName)
        return self.nidGetVmIp(self.netDict[uid][networkName].nid, sid)

    def getVmMac(self, uid, networkName, sid):
        assert self._validateNetworkName(networkName)
        return self.nidGetVmMac(self.netDict[uid][networkName].nid, sid)

    def nidGetTmpDir(self, nid):
        return os.path.join(self.param.tmpDir, str(nid))

    def nidGetVmIp(self, nid, sid):
        assert self._validateResSetId(sid)
        return "%d.%d.%d.%d" % (self.ip1, nid / 256, nid % 256, self.minIpNumber + sid)

    def nidGetVmMac(self, nid, sid):
        assert self._validateResSetId(sid)
        return "%s:%02x:%02x:%02x" % (self.macOui, nid / 256, nid % 256, self.minIpNumber + sid)

    def _validateNetworkName(self, networkName):
        return networkName in ["bridge", "nat", "route", "isolate"]

    def _validateResSetId(self, sid):
        return 1 <= sid <= 128

    def _allocId(self):
        for nid in range(1, 256 * 256):
            found = False
            for netu in list(self.netDict.values()):
                for net in list(netu.values()):
                    if net.nid == nid:
                        found = True
                        break
                if found:
                    break
            if not found:
                return nid
        assert False


class _NetworkBridge(VirtHostNetworkEventCallback):

    def __init__(self, nid):
        self.nid = nid
        self.refcount = 0
        self.brname = "vnb%d" % (self.nid)
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

    def addTapIntf(self, sid):
        assert sid not in self.tapDict

        tapname = "%s.%d" % (self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
        VirtUtil.shell('/bin/ip tuntap add dev "%s" mode tap' % (tapname))
        VirtUtil.shell('/sbin/brctl addif "%s" "%s"' % (self.brname, tapname))
        VirtUtil.shell('/bin/ifconfig "%s" up' % (tapname))
        self.tapDict[sid] = tapname

    def removeTapIntf(self, sid):
        assert sid in self.tapDict

        tapname = self.tapDict[sid]
        VirtUtil.shell('/bin/ifconfig "%s" down' % (tapname))
        VirtUtil.shell('/sbin/brctl delif "%s" "%s"' % (self.brname, tapname))
        VirtUtil.shell('/bin/ip tuntap del dev "%s" mode tap' % (tapname))
        del self.tapDict[sid]

    def getTapInterface(self, sid):
        return self.tapDict.get(sid, None)


class _NetworkNat(VirtHostNetworkEventCallback):

    def __init__(self, nid):
        self.nid = nid
        self.refcount = 0
        self.netip = "10.%d.%d.0" % (self.nid / 256, self.nid % 256)
        self.netmask = "255.255.255.0"

        self.brname = "vnb%d" % (self.nid)
        self.brmac = "00:50:00:%02d:%02d" % (self.nid / 256, self.nid % 256)
        self.brip = "10.%d.%d.1" % (self.nid / 256, self.nid % 256)

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

    def addTapIntf(self, sid):
        assert sid not in self.tapDict

        tapname = "%s.%d" % (self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
        VirtUtil.shell('/bin/ip tuntap add dev "%s" mode tap' % (tapname))
        VirtUtil.shell('/sbin/brctl addif "%s" "%s"' % (self.brname, tapname))
        VirtUtil.shell('/bin/ifconfig "%s" up' % (tapname))
        self.tapDict[sid] = tapname

    def removeTapIntf(self, sid):
        assert sid in self.tapDict

        tapname = self.tapDict[sid]
        VirtUtil.shell('/bin/ifconfig "%s" down' % (tapname))
        VirtUtil.shell('/sbin/brctl delif "%s" "%s"' % (self.brname, tapname))
        VirtUtil.shell('/bin/ip tuntap del dev "%s" mode tap' % (tapname))
        del self.tapDict[sid]

    def getTapInterface(self, sid):
        return self.tapDict.get(sid, None)

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


class _NetworkRoute(VirtHostNetworkEventCallback):

    def __init__(self, nid):
        self.nid = nid
        self.refcount = 0
        self.brname = "vnb%d" % (self.nid)

    def release(self):
        pass

    def onActiveInterfaceAdd(self, ifName):
        assert False

    def onActiveInterfaceRemove(self, ifName):
        assert False


class _NetworkIsolate:

    def __init__(self, nid):
        self.nid = nid
        self.refcount = 0
        self.brname = "vnb%d" % (self.nid)                # it's a virtual bridge interface
        self.tapDict = dict()

    def release(self):
        pass

    def addTapIntf(self, sid):
        assert sid not in self.tapDict

        tapname = "%s.%d" % (self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
        VirtUtil.shell('/bin/ip tuntap add dev "%s" mode tap' % (tapname))
        self.tapDict[sid] = tapname

    def removeTapIntf(self, sid):
        assert sid in self.tapDict

        tapname = self.tapDict[sid]
        VirtUtil.shell('/bin/ip tuntap del dev "%s" mode tap' % (tapname))
        del self.tapDict[sid]

    def getTapInterface(self, sid):
        return self.tapDict.get(sid, None)
