#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import dbus
import dbus.service
from virt_util import VirtUtil
from virt_network import VirtNetworkBridge
from virt_network import VirtNetworkNat
from virt_network import VirtNetworkRoute
from virt_network import VirtNetworkIsolate
from virt_dhcp_server import VirtDhcpServer
from virt_samba_server import VirtSambaServer

################################################################################
# DBus API Docs
################################################################################
#
# ==== Main Application ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService
# Object path           /
#
# Methods:
# networkId:int    NewNetwork(networkType:string)
# void             DeleteNetwork(networkId:int)
# devPath:string   NewVfioDevicePci(devName:string)
# devPath:string   NewVfioDeviceVga(devName:string)
# devPath:string   NewVfioDeviceUsb(devName:string)
# void             DeleteVfioDevice(devPath:string)
#
# Signals:
#
# Notes:
#   networkType can be: bridge, nat, route
#   one user can have 6 networks, one network can have 32 virtual machines, it's caused by ip/mac address allocation limit
#   one user can only have one network of a same type
#   service exits when the last network is deleted
#
# ==== Network ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService.Network
# Object path           /{user-id:int}/Networks/{networkId:int}
#
# Methods:
# vmId:int         AddVm(vmName:string)
# void             DeleteVm(vmId:int)
# shareId:int      AddSambaShare(vmId:int, shareName:string, srcPath:string, readonly:boolean)
# void             DeleteSambaShare(vmId:int, shareName:string)
#
# Signals:
#
# ==== NetVirtMachine ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService.NetVirtMachine
# Object path           /{user-id:int}/Networks/{networkId:int}/NetVirtMachines/{vmId:int}
#
# Methods:
# tapifname:string GetTapInterface()
# macaddr:string   GetTapVmMacAddress()
#
# Signals:
#
# ==== NetSambaShare ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService.NetSambaShare
# Object path           /{user-id:int}/Networks/{networkId:int}/NetSambaShares/{shareId:int}
#
# Methods:
# account:string   GetAccount()
#
# Signals:
#


class VirtServiceException(Exception):

    def __init__(self, msg):
        self.msg = msg


class DbusMainObject(dbus.service.Object):

    def __init__(self, param):
        self.param = param
        self.netObjList = []
        self.dhcpServer = VirtDhcpServer(self.param)
        self.sambaServer = VirtSambaServer(self.param)

        bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService')

        self.handle1 = dbus.SystemBus().add_signal_receiver(self.onNameOwnerChanged, 'NameOwnerChanged', None, None)

    def release(self):
        assert len(self.netObjList) == 0

        dbus.SystemBus().remove_signal_receiver(self.handle1)
        self.remove_from_connection()
        self.sambaServer.release()
        self.dhcpServer.release()

    def abort(self):
        for i in reversed(range(0, len(self.netObjList))):
            nobj = self.netObjList[i]

            for j in reversed(range(0, len(nobj.sambaShareObjList))):
                ssobj = nobj.sambaShareObjList.pop(j)
                ssobj.release()

            for j in reversed(range(0, len(nobj.vmObjList))):
                vobj = nobj.vmObjList.pop(j)
                vobj.release()

            self.netObjList.pop(i)
            nobj.release()
            if len(self.netObjList) == 0:
                VirtUtil.writeFile("/proc/sys/net/ipv4/ip_forward", "0")

        self.release()

    def onNameOwnerChanged(self, name, old, new):
        if not name.startswith(":") or new != "":
            return

        assert name == old
        for i in reversed(range(0, len(self.netObjList))):
            nobj = self.netObjList[i]

            for j in reversed(range(0, len(nobj.sambaShareObjList))):
                ssobj = nobj.sambaShareObjList[j]
                if ssobj.owner == name:
                    nobj.sambaShareObjList.pop(j)
                    ssobj.release()

            for j in reversed(range(0, len(nobj.vmObjList))):
                vobj = nobj.vmObjList[j]
                if vobj.owner == name:
                    nobj.vmObjList.pop(j)
                    vobj.release()

            while name in nobj.ownerList:
                if nobj.removeOwner(name):
                    self.netObjList.pop(i)
                    nobj.release()
                    if len(self.netObjList) == 0:
                        VirtUtil.writeFile("/proc/sys/net/ipv4/ip_forward", "0")

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender',
                         in_signature='s', out_signature='i')
    def NewNetwork(self, networkType, sender=None):
        # get user id
        uid = VirtUtil.dbusGetUserId(self.connection, sender)

        # find existing network object
        for no in self.netObjList:
            if no.uid == uid and no.networkType == networkType:
                no.addOwner(sender)
                return no.nid

        # allocate network id, range is [1, 6]
        nid = 1
        while True:
            found = False
            for no in self.netObjList:
                if no.uid == uid and no.nid == nid:
                    found = True
            if not found:
                break
            if nid >= 6:
                raise VirtServiceException("network number limit is reached")
            nid = nid + 1
            continue

        # create new network object
        netObj = DbusNetworkObject(self.param, uid, nid, networkType, self.dhcpServer, self.sambaServer)
        netObj.addOwner(sender)
        self.netObjList.append(netObj)

        # open ipv4 forwarding, now no other program needs it, so we do a simple implementation
        VirtUtil.writeFile("/proc/sys/net/ipv4/ip_forward", "1")

        return nid

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender',
                         in_signature='i')
    def DeleteNetwork(self, nid, sender=None):
        # get user id
        uid = VirtUtil.dbusGetUserId(self.connection, sender)

        # find and delete network object
        for i in range(0, len(self.netObjList)):
            if self.netObjList[i].uid == uid and self.netObjList[i].nid == nid:
                if self.netObjList[i].removeOwner(sender):
                    no = self.netObjList.pop(i)
                    no.release()
                    if len(self.netObjList) == 0:
                        VirtUtil.writeFile("/proc/sys/net/ipv4/ip_forward", "0")
                return

        raise VirtServiceException("the specified network does not exist")

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender',
                         in_signature='s', out_signature='s')
    def NewVfioDevicePci(self, devName, sender=None):
        uid = VirtUtil.dbusGetUserId(self.connection, sender)
        return self.param.vfioDevManager.newVfioDeviceVga(uid, devName)

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender',
                         in_signature='s')
    def DeleteVfioDevice(self, devPath, sender=None):
        uid = VirtUtil.dbusGetUserId(self.connection, sender)
        self.param.vfioDevManager.releaseVfioDevice(uid, devPath)


class DbusNetworkObject(dbus.service.Object):

    def __init__(self, param, uid, nid, networkType, dhcpServer, sambaServer):
        self.param = param
        self.uid = uid
        self.nid = nid
        self.networkType = networkType
        self.gDhcpServer = dhcpServer
        self.gSambaServer = sambaServer

        self.ownerList = []
        self.vmObjList = []
        self.sambaShareObjList = []

        # create network temp directory
        os.makedirs(os.path.join(self.param.tmpDir, str(self.uid), str(self.nid)))

        # create network object
        if self.networkType == "bridge":
            self.netObj = VirtNetworkBridge(self.param, self.uid, self.nid)
        elif self.networkType == "nat":
            self.netObj = VirtNetworkNat(self.param, self.uid, self.nid)
        elif self.networkType == "route":
            self.netObj = VirtNetworkRoute(self.param, self.uid, self.nid)
        elif self.networkType == "isolate":
            self.netObj = VirtNetworkIsolate(self.param, self.uid, self.nid)
        else:
            raise VirtServiceException("invalid networkType %s" % (networkType))

        # enable server
        if self.networkType in ["nat", "route"]:
            self.gDhcpServer.addNetwork(self.uid, self.nid, self.netObj.brname, self.netObj.brip, self.netObj.netip, self.netObj.netmask)
            self.gSambaServer.addNetwork(self.uid, self.nid, self.netObj.brname)

        # register host network callback
        if self.networkType in ["bridge", "nat", "route"]:
            self.param.hostNetwork.registerEventCallback(self.netObj)

        # register dbus object path
        bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/%d/Networks/%d' % (self.uid, self.nid))

    def release(self):
        assert len(self.ownerList) == 0
        assert len(self.vmObjList) == 0
        assert len(self.sambaShareObjList) == 0

        # deregister dbus object path
        self.remove_from_connection()

        # deregister host network callback
        if self.networkType in ["bridge", "nat", "route"]:
            self.param.hostNetwork.unregisterEventCallback(self.netObj)

        # disable server
        if self.networkType in ["nat", "route"]:
            self.gSambaServer.removeNetwork(self.uid, self.nid)
            self.gDhcpServer.removeNetwork(self.uid, self.nid)

        # release network object
        self.netObj.release()

        # delete network temp directory
        shutil.rmtree(os.path.join(self.param.tmpDir, str(self.uid), str(self.nid)))

    def addOwner(self, owner):
        self.ownerList.append(owner)

    def removeOwner(self, owner):
        self.ownerList.remove(owner)
        return len(self.ownerList) == 0

    @dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
                         in_signature='s', out_signature='i')
    def AddVm(self, vmName, sender=None):
        # check user id
        VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

        # find existing vm object
        for vo in self.vmObjList:
            if vo.vmName == vmName:
                raise VirtServiceException("virtual machine already exists")

        # allocate vmId, range is [0, 31]
        vmId = 0
        while True:
            found = False
            for vo in self.vmObjList:
                if vo.vmId == vmId:
                    found = True
                    break
            if not found:
                break
            if vmId >= 31:
                raise VirtServiceException("virtual machine number limit is reached")
            vmId = vmId + 1
            continue

        # create new virtual machine object
        vmObj = DbusNetVmObject(self.param, self.uid, self.netObj, self.nid, vmName, vmId)
        vmObj.setOwner(sender)
        self.vmObjList.append(vmObj)

        return vmId

    @dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
                         in_signature='i')
    def DeleteVm(self, vmId, sender=None):
        # check user id
        VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

        # find existing vm object
        for i in range(0, len(self.vmObjList)):
            if self.vmObjList[i].vmId == vmId:
                vo = self.vmObjList.pop(i)
                vo.release()
                return

        raise VirtServiceException("virtual machine does not exist")

    @dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
                         in_signature='issb')
    def AddSambaShare(self, vmId, shareName, srcPath, readonly, sender=None):
        # check user id
        VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

        if not srcPath.startswith("/"):
            raise VirtServiceException("srcPath must be absoulte path")

        # allocate shareId
        if len(self.sambaShareObjList) > 0:
            shareId = self.sambaShareObjList[-1].shareId + 1
        else:
            shareId = 1

        # create new samba share object
        shareObj = DbusNetSambaShareObject(self.param, self.uid, self.nid, self.gSambaServer, vmId, shareName, shareId, srcPath, readonly)
        shareObj.setOwner(sender)
        self.sambaShareObjList.append(shareObj)

        return shareId

    @dbus.service.method('org.fpemud.VirtService.Network', sender_keyword='sender',
                         in_signature='is')
    def DeleteSambaShare(self, vmId, shareName, sender=None):
        # check user id
        VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

        # find existing share object
        for i in range(0, len(self.vmObjList)):
            if self.sambaShareObjList[i].vmId == vmId and self.sambaShareObjList[i].shareName == shareName:
                so = self.sambaShareObjList.pop(i)
                so.release()
                return

        raise VirtServiceException("samba share does not exist")


class DbusNetVmObject(dbus.service.Object):

    def __init__(self, param, uid, netObj, nid, vmName, vmId):
        self.param = param
        self.uid = uid
        self.netObj = netObj
        self.nid = nid
        self.vmName = vmName
        self.vmId = vmId

        self.owner = ""

        # add vm object
        self.netObj.addVm(vmId)

        # register dbus object path
        bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/%d/Networks/%d/NetVirtMachines/%d' % (self.uid, self.nid, self.vmId))

    def release(self):
        self.remove_from_connection()
        self.netObj.removeVm(self.vmId)

    def setOwner(self, owner):
        self.owner = owner

    @dbus.service.method('org.fpemud.VirtService.NetVirtMachine', sender_keyword='sender',
                         out_signature='s')
    def GetTapInterface(self, sender=None):
        # check user id
        VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

        # get tap interface
        return self.netObj.getTapInterface(self.vmId)

    @dbus.service.method('org.fpemud.VirtService.NetVirtMachine', sender_keyword='sender',
                         out_signature='s')
    def GetTapVmMacAddress(self, sender=None):
        # check user id
        VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

        # do job
        return VirtUtil.getVmMacAddress(self.param.macOuiVm, self.uid, self.nid, self.vmId)


class DbusNetSambaShareObject(dbus.service.Object):

    def __init__(self, param, uid, nid, sambaServer, vmId, shareName, shareId, srcPath, readonly):
        self.param = param
        self.uid = uid
        self.nid = nid
        self.gSambaServer = sambaServer
        self.vmId = vmId
        self.shareName = shareName
        self.shareId = shareId
        self.srcPath = srcPath
        self.readonly = readonly

        self.owner = ""

        self.gSambaServer.networkAddShare(self.uid, self.nid, self.vmId, self.shareName, self.srcPath, self.readonly)

        # register dbus object path
        bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/%d/Networks/%d/NetSambaShares/%d' % (self.uid, self.nid, self.shareId))

    def release(self):
        self.remove_from_connection()
        self.gSambaServer.networkRemoveShare(self.uid, self.nid, self.vmId, self.shareName)

    def setOwner(self, owner):
        self.owner = owner

    @dbus.service.method('org.fpemud.VirtService.NetSambaShare', sender_keyword='sender',
                         out_signature='s')
    def GetAccount(self, sender=None):
        # check user id
        VirtUtil.dbusCheckUserId(self.connection, sender, self.uid)

        # do job
        username, password = self.gSambaServer.networkGetAccountInfo(self.uid, self.nid)
        return "%s:%s" % (username, password)
