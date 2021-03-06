#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import shutil
import pyroute2
import ipaddress
from virt_util import VirtUtil
from virt_param import VirtInitializationError
from virt_host_network import VirtHostNetworkEventCallback


class VirtNetworkManager:

    def __init__(self, param):
        self.param = param
        self.netDict = dict()       # { userId: { netName: netObj, netName2: netObj2, ... }, userId2: { ... }, ... }

        if not os.path.exists("/bin/ip"):
            raise VirtInitializationError("/bin/ip not found")
        if not os.path.exists("/sbin/nft"):
            raise VirtInitializationError("/sbin/nft not found")

    def release(self):
        assert len(self.netDict) == 0

    def addNetwork(self, uid, networkName):
        assert _validateNetworkName(networkName)

        if uid in self.netDict and networkName in self.netDict[uid]:
            # network object already exists, add reference count
            self.netDict[uid][networkName].refcount += 1
        else:
            # create a new network object
            if uid not in self.netDict:
                self.netDict[uid] = dict()
            try:
                if networkName == "bridge":
                    nobj = _NetworkBridge(self.param, uid, self._allocId())
                elif networkName == "nat":
                    nobj = _NetworkNat(self.param, uid, self._allocId())
                elif networkName == "route":
                    nobj = _NetworkRoute(self.param, uid, self._allocId())
                elif networkName == "isolate":
                    nobj = _NetworkIsolate(self.param, uid, self._allocId())
                else:
                    assert False
                nobj.refcount += 1
                self.netDict[uid][networkName] = nobj

                # open ipv4 forwarding, currently no other program needs it, so we do a simple implementation
                VirtUtil.writeFile("/proc/sys/net/ipv4/ip_forward", "1")
            except:
                if len(self.netDict[uid]) == 0:
                    del self.netDict[uid]
                raise

    def removeNetwork(self, uid, networkName):
        assert _validateNetworkName(networkName)

        if uid not in self.netDict or networkName not in self.netDict[uid]:
            return

        nobj = self.netDict[uid][networkName]
        nobj.refcount -= 1
        if nobj.refcount == 0:
            nobj.release()
            del self.netDict[uid][networkName]
            if len(self.netDict[uid]) == 0:
                del self.netDict[uid]
            if len(self.netDict) == 0:
                VirtUtil.writeFile("/proc/sys/net/ipv4/ip_forward", "0")

    def addTapIntf(self, uid, networkName, sid):
        assert _validateNetworkName(networkName) and _validateResSetId(sid)
        self.netDict[uid][networkName].addTapIntf(sid)

    def removeTapIntf(self, uid, networkName, sid):
        assert _validateNetworkName(networkName) and _validateResSetId(sid)
        if self.netDict[uid][networkName].getTapInterface(sid) is not None:
            self.netDict[uid][networkName].removeTapIntf(sid)

    def hasTapIntf(self, uid, networkName, sid):
        assert _validateNetworkName(networkName) and _validateResSetId(sid)
        if uid not in self.netDict or networkName not in self.netDict[uid]:
            return False
        return self.netDict[uid][networkName].getTapInterface(sid) is not None

    def getTapIntf(self, uid, networkName, sid):
        assert _validateNetworkName(networkName) and _validateResSetId(sid)
        ret = self.netDict[uid][networkName].getTapInterface(sid)
        assert ret is not None
        return ret

    def getVmIp(self, uid, networkName, sid):
        assert _validateNetworkName(networkName)
        return self.netDict[uid][networkName].getVmIp(sid)

    def getVmMac(self, uid, networkName, sid):
        assert _validateNetworkName(networkName)
        return self.netDict[uid][networkName].getVmMac(sid)

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


class _NetworkBase:

    def __init__(self, param, uid, nid):
        self.macOui = "00:50:01"
        self.ip1 = 10
        self.minIpNumber = 11       # IP X.X.X.0 ~ X.X.X.10 are reserved

        self.param = param
        self.uid = uid
        self.nid = nid
        self.refcount = 0

        # create network temp directory
        if not os.path.exists(os.path.join(self.param.tmpDir, str(self.nid))):
            os.makedirs(os.path.join(self.param.tmpDir, str(self.nid)))

    def release(self):
        shutil.rmtree(os.path.join(self.param.tmpDir, str(self.nid)))

    def getTmpDir(self):
        return os.path.join(self.param.tmpDir, str(self.nid))

    def getVmIp(self, sid):
        assert _validateResSetId(sid)
        return "%d.%d.%d.%d" % (self.ip1, self.nid // 256, self.nid % 256, self.minIpNumber + sid)

    def getVmMac(self, sid):
        assert _validateResSetId(sid)
        return "%s:%02x:%02x:%02x" % (self.macOui, self.nid // 256, self.nid % 256, self.minIpNumber + sid)


class _NetworkBridge(_NetworkBase, VirtHostNetworkEventCallback):

    def __init__(self, param, uid, nid):
        super(_NetworkBridge, self).__init__(param, uid, nid)

        self.brname = "vnb%d" % (self.nid)
        self.mainIntfList = []
        self.tapDict = dict()

        with pyroute2.IPRoute() as ip:
            ip.link("add", kind="bridge", ifname=self.brname)
            idx = ip.link_lookup(ifname=self.brname)[0]
            ip.link("set", index=idx, state="up")
        self.param.hostNetwork.registerEventCallback(self)

    def release(self):
        assert len(self.tapDict) == 0
        self.param.hostNetwork.unregisterEventCallback(self)
        with pyroute2.IPRoute() as ip:
            idx = ip.link_lookup(ifname=self.brname)[0]
            ip.link("set", index=idx, state="down")
            ip.link("del", index=idx)
        super(_NetworkBridge, self).release()

    def onActiveInterfaceAdd(self, ifName):
        # some interface like wlan0 has no bridging capbility, we ignore them
        # fixme: how to send this error to user?
        VirtUtil.addInterfaceToBridge(self.brname, ifName)
        self.mainIntfList.append(ifName)

    def onActiveInterfaceRemove(self, ifName):
        if ifName in self.mainIntfList:
            VirtUtil.removeInterfaceFromBridge(self.brname, ifName)
            self.mainIntfList.remove(ifName)

    def addTapIntf(self, sid):
        assert sid not in self.tapDict

        tapname = "%s.%d" % (self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
        VirtUtil.shell('/bin/ip tuntap add dev "%s" mode tap' % (tapname))
        VirtUtil.addInterfaceToBridge(self.brname, tapname)
        with pyroute2.IPRoute() as ip:
            idx = ip.link_lookup(ifname=tapname)[0]
            ip.link("set", index=idx, state="up")
        self.tapDict[sid] = tapname

    def removeTapIntf(self, sid):
        assert sid in self.tapDict

        tapname = self.tapDict[sid]
        with pyroute2.IPRoute() as ip:
            idx = ip.link_lookup(ifname=tapname)[0]
            ip.link("set", index=idx, state="down")
        VirtUtil.removeInterfaceFromBridge(self.brname, tapname)
        VirtUtil.shell('/bin/ip tuntap del dev "%s" mode tap' % (tapname))
        del self.tapDict[sid]

    def getTapInterface(self, sid):
        return self.tapDict.get(sid, None)


class _NetworkNat(_NetworkBase, VirtHostNetworkEventCallback):

    def __init__(self, param, uid, nid):
        super(_NetworkNat, self).__init__(param, uid, nid)

        self.netip = "10.%d.%d.0" % (self.nid // 256, self.nid % 256)
        self.netmask = "255.255.255.0"

        self.brname = "vnb%d" % (self.nid)
        self.brmac = "00:50:00:%02d:%02d" % (self.nid // 256, self.nid % 256)
        self.brip = "10.%d.%d.1" % (self.nid // 256, self.nid % 256)

        self.mainIntfList = []
        self.tapDict = dict()

        with pyroute2.IPRoute() as ip:
            brnet = ipaddress.IPv4Network(self.brip + "/" + self.netmask, strict=False)
            ip.link("add", kind="bridge", ifname=self.brname)
            idx = ip.link_lookup(ifname=self.brname)[0]
            ip.link('set', index=idx, address='00:11:22:33:44:55')
            ip.addr("add", index=idx, address=str(self.brip), mask=brnet.prefixlen, broadcast=str(brnet.broadcast_address))
            ip.link("set", index=idx, state="up")
        self._addNftNatRule(self.netip, self.netmask)

        self.param.dhcpServer.startOnNetwork(self)
        self.param.sambaServer.startOnNetwork(uid, self)
        self.param.hostNetwork.registerEventCallback(self)

    def release(self):
        assert len(self.tapDict) == 0

        self.param.hostNetwork.unregisterEventCallback(self)
        self.param.sambaServer.stopOnNetwork(self)
        self.param.dhcpServer.stopOnNetwork(self)

        self._removeNftNatRule(self.netip, self.netmask)
        with pyroute2.IPRoute() as ip:
            idx = ip.link_lookup(ifname=self.brname)[0]
            ip.link("set", index=idx, state="down")
            ip.link("del", index=idx)

        super(_NetworkNat, self).release()

    def onActiveInterfaceAdd(self, ifName):
        self.mainIntfList.append(ifName)

    def onActiveInterfaceRemove(self, ifName):
        self.mainIntfList.remove(ifName)

    def addTapIntf(self, sid):
        assert sid not in self.tapDict

        tapname = "%s.%d" % (self.brname, VirtUtil.getMaxTapId(self.brname) + 1)
        VirtUtil.shell('/bin/ip tuntap add dev "%s" mode tap' % (tapname))
        VirtUtil.addInterfaceToBridge(self.brname, tapname)
        with pyroute2.IPRoute() as ip:
            idx = ip.link_lookup(ifname=tapname)[0]
            ip.link("set", index=idx, state="up")
        self.tapDict[sid] = tapname

    def removeTapIntf(self, sid):
        assert sid in self.tapDict

        tapname = self.tapDict[sid]
        with pyroute2.IPRoute() as ip:
            idx = ip.link_lookup(ifname=tapname)[0]
            ip.link("set", index=idx, state="down")
        VirtUtil.removeInterfaceFromBridge(self.brname, tapname)
        VirtUtil.shell('/bin/ip tuntap del dev "%s" mode tap' % (tapname))
        del self.tapDict[sid]

    def getTapInterface(self, sid):
        return self.tapDict.get(sid, None)

    def _addNftNatRule(self, netip, netmask):
        # create table
        rc, msg = VirtUtil.shell('/sbin/nft list table ip virt-service-nat', "retcode+stdout")
        if rc != 0:
            VirtUtil.shell('/sbin/nft add table ip virt-service-nat')
            VirtUtil.shell('/sbin/nft add chain virt-service-nat prerouting { type nat hook prerouting priority 0 \\; }')
            VirtUtil.shell('/sbin/nft add chain virt-service-nat postrouting { type nat hook postrouting priority 0 \\; }')

        # create rule
        VirtUtil.shell('/sbin/nft add rule virt-service-nat postrouting ip saddr %s/%s masquerade' % (netip, VirtUtil.ipMaskToLen(netmask)))

    def _removeNftNatRule(self, netip, netmask):
        # table must be there
        rc, msg = VirtUtil.shell('/sbin/nft list table ip virt-service-nat', "retcode+stdout")
        assert rc == 0

        # delete my rule
        msg = VirtUtil.shell('/sbin/nft list table ip virt-service-nat -a', "stdout")
        m = re.search("^.* %s/%s .* # handle ([0-9]+)$" % (netip, VirtUtil.ipMaskToLen(netmask)), msg, re.M)
        if m is not None:
            VirtUtil.shell('/sbin/nft delete rule virt-service-nat postrouting handle %s' % (m.group(1)))

        # delete table if no rules left
        msg = VirtUtil.shell('/sbin/nft list table ip virt-service-nat -a', "stdout")
        m = re.search("handle [0-9]+", msg, re.M)
        if m is None:
            VirtUtil.shell('/sbin/nft delete table virt-service-nat')


class _NetworkRoute(_NetworkBase, VirtHostNetworkEventCallback):

    def __init__(self, param, uid, nid):
        super(_NetworkRoute, self).__init__(param, uid, nid)

        self.brname = "vnb%d" % (self.nid)
        self.param.dhcpServer.startOnNetwork(self)
        self.param.sambaServer.startOnNetwork(uid, self)
        self.param.hostNetwork.registerEventCallback(self)

    def release(self):
        self.param.hostNetwork.unregisterEventCallback(self)
        self.param.sambaServer.stopOnNetwork(self)
        self.param.dhcpServer.stopOnNetwork(self)
        super(_NetworkRoute, self).release()

    def onActiveInterfaceAdd(self, ifName):
        assert False

    def onActiveInterfaceRemove(self, ifName):
        assert False


class _NetworkIsolate(_NetworkBase):

    def __init__(self, param, uid, nid):
        super(_NetworkIsolate, self).__init__(param, uid, nid)
        self.brname = "vnb%d" % (self.nid)                # it's a virtual bridge interface
        self.tapDict = dict()

    def release(self):
        super(_NetworkIsolate, self).release()

    def addTapIntf(self, param, sid):
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


def _validateNetworkName(networkName):
    return networkName in ["bridge", "nat", "route", "isolate"]


def _validateResSetId(sid):
    return 1 <= sid <= 128
