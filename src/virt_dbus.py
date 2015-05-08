#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import dbus
import dbus.service
from virt_util import VirtUtil

################################################################################
# DBus API Docs
################################################################################
#
#
# ==== Main Application ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService
# Object path           /
#
# Methods:
#   vmResSetId:int        NewVmResSet()
#   void                  DeleteVmResSet(vmResSetId:int)
#   vmId:int              AttachVm(vmName:string, vmResSetId:int)
#   void                  DetachVm(vmId:int)
#
# Signals:
#
# Notes:
#   each user can have 128 virt-machine resource sets, vmResSetId must be in range [1,128]
#   service exits when the last virtual-machine resource set is deleted?
#
#
# ==== VmResSet ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService.VmResSet
# Object path           /{user-id:int}/VmResSets/{setId:int}
#
# Methods:
#   tapifname:string                   GetTapIntf()
#   macaddr:string                     GetVmMacAddr()
#   ipaddr:string                      GetVmIpAddr()
#   (devpath:string)                   GetVfioDevInfo(devId:int)
#
#   void                               AddTapIntf(networkName:string)
#   void                               RemoveTapIntf()
#   void                               NewSambaShare(shareName:string, srcPath:string, readonly:boolean)
#   void                               DeleteSambaShare(shareName:string)
#   devId:int                          AddVfioDevice(devName:string, vfioType:string)
#   void                               RemoveDevice(devId:int)
#
# Notes:
#   networkName can be: bridge, nat, route, isolate
#   vfioType can be: pci, vga, usb
#
#
# ==== VirtMachine ====
# Service               org.fpemud.VirtService
# Interface             org.fpemud.VirtService.VirtMachine
# Object path           /{user-id:int}/VirtMachines/{vmId:int}
#
# Methods:
#   boolean                            IsControlChannelEstablished()
#   void                               RunExecutable(filename:string, arguments:string)
#
# Signals:
#
# Notes:
#


class VirtServiceException(Exception):

    def __init__(self, msg):
        self.msg = msg


class DbusMainObject(dbus.service.Object):

    def __init__(self, param):
        self.param = param
        self.resSetDict = dict()       # { userId: { resSetId: resSetObj, resSet2: resSetObj, ... }, userId2: { ... }, ... }
        self.vmDict = dict()           # { userId: { vmId: vmObj, vmId2: vmObj, ... }, userId2: { ... }, ... }

        bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService')

        # for handling client process termination
        self.handle = dbus.SystemBus().add_signal_receiver(self.onNameOwnerChanged, 'NameOwnerChanged', None, None)

    def release(self):
        assert len(self.resSetDict) == 0
        assert len(self.vmDict) == 0

        dbus.SystemBus().remove_signal_receiver(self.handle)
        self.remove_from_connection()

    def onNameOwnerChanged(self, name, old, new):
        # focus on name deletion, filter other circumstance
        if not name.startswith(":") or new != "":
            return
        assert name == old

        for vmu in list(self.vmDict.values()):
            for vm in list(vmu.values()):
                if vm.owner == old:
                    self._vmRemove(vm.uid, vm.vmid, vm)

        for ressetu in list(self.resSetDict.values()):
            for resset in list(ressetu.values()):
                if resset.owner == old:
                    self._resSetRemove(resset.uid, resset.sid, resset)

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', out_signature='i')
    def NewVmResSet(self, sender=None):
        uid = VirtUtil.dbusGetUserId(self.connection, sender)

        if self.param.initError is not None:
            raise VirtServiceException("virt-service initialization failed, %s" % (self.param.initError))

        # create new resource set object
        try:
            if uid not in self.resSetDict:
                self.resSetDict[uid] = dict()

            sid = VirtUtil.allocId(self.resSetDict[uid])
            if sid > 128:
                raise VirtServiceException("too many virt-machine resource set allocated")

            sObj = DbusResSetObject(self.param, uid, sid, sender)
            self.resSetDict[uid][sid] = sObj
            return sid
        except:
            if uid in self.resSetDict and len(self.resSetDict[uid]) == 0:
                del self.resSetDict[uid]

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', in_signature='i')
    def DeleteVmResSet(self, sid, sender=None):
        uid = VirtUtil.dbusGetUserId(self.connection, sender)

        if self.param.initError is not None:
            raise VirtServiceException("virt-service initialization failed, %s" % (self.param.initError))

        resset = self._resSetGet(uid, sid)
        if resset is None:
            raise VirtServiceException("virt-machine resource set not found")

        vm = self._resSetGetAttachedVm(uid, sid)
        if vm is not None:
            raise VirtServiceException("virt-machine resource set has been binded to virt-machine %s" % (vm.name))

        self._resSetRemove(uid, sid, resset)

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', in_signature='si', out_signature='i')
    def AttachVm(self, vmname, sid, sender=None):
        uid = VirtUtil.dbusGetUserId(self.connection, sender)

        if self.param.initError is not None:
            raise VirtServiceException("virt-service initialization failed, %s" % (self.param.initError))

        resset = self._resSetGet(uid, sid)
        if resset is None:
            raise VirtServiceException("virt-machine resource set not found")

        vm = self._resSetGetAttachedVm(uid, sid)
        if vm is not None:
            raise VirtServiceException("virt-machine resource set has been binded to virt-machine %s" % (vm.name))

        # create new vm object, using sid as vmid
        try:
            if uid not in self.vmDict:
                self.vmDict[uid] = dict()
            vmid = sid
            vmObj = DbusVmObject(self.param, uid, vmid, sender)
            self.vmDict[uid][vmid] = vmObj
            return vmid
        except:
            if uid in self.vmDict and len(self.vmDict[uid]) == 0:
                del self.vmDict[uid]

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', in_signature='i')
    def DetachVm(self, vmid, sender=None):
        uid = VirtUtil.dbusGetUserId(self.connection, sender)

        if self.param.initError is not None:
            raise VirtServiceException("virt-service initialization failed, %s" % (self.param.initError))

        vm = self._vmGet(uid, vmid)
        if vm is None:
            raise VirtServiceException("virt-machine not found")

        self._vmRemove(uid, vmid, vm)

    def _resSetGet(self, uid, sid):
        if uid in self.resSetDict:
            return self.resSetDict[uid].get(sid, None)
        else:
            return None

    def _vmGet(self, uid, vmid):
        if uid in self.vmDict:
            return self.vmDict[uid].get(vmid, None)
        else:
            return None

    def _resSetGetAttachedVm(self, uid, sid):
        if uid in self.vmDict:
            for vmObj in list(self.vmDict[uid].values()):
                if vmObj.sid == sid:
                    return vmObj
        return None

    def _resSetRemove(self, uid, sid, resset):
        resset.release()
        del self.resSetDict[uid][sid]
        if len(self.resSetDict[uid]) == 0:
            del self.resSetDict[uid]

    def _vmRemove(self, uid, vmid, vm):
        vm.release()
        del self.vmDict[uid][vmid]
        if len(self.vmDict[uid]) == 0:
            del self.vmDict[uid]


class DbusResSetObject(dbus.service.Object):

    def __init__(self, param, uid, sid, owner):
        self.param = param
        self.uid = uid
        self.sid = sid
        self.owner = owner

        self.networkName = None           # not None means tap interface is allocated

        bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/%d/VmResSets/%d' % (self.uid, self.sid))

    def release(self):
        assert self.networkName is None
        self.remove_from_connection()

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', out_signature='s')
    def GetTapIntf(self, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)
        assert self.networkName is not None
        self.param.netManager.getTapIntf(self.uid, self.networkName, self.sid)

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', out_signature='s')
    def GetVmMacAddr(self, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)
        assert self.networkName is not None
        self.param.netManager.getVmMac(self.uid, self.networkName, self.sid)

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', out_signature='s')
    def GetVmIpAddr(self, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)
        assert self.networkName is not None
        self.param.netManager.getVmIp(self.uid, self.networkName, self.sid)

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', in_signature='s')
    def AddTapIntf(self, networkName, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)
        assert self.networkName is None

        self.param.netManager.addNetwork(self.uid, networkName)
        self.param.netManager.addTapIntf(self.uid, networkName, self.sid)
        self.networkName = networkName

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender')
    def RemoveTapIntf(self, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)
        assert self.networkName is not None

        self.param.netManager.removeTapIntf(self.uid, self.networkName, self.sid)
        self.param.netManager.removeNetwork(self.uid, self.networkName)
        self.networkName = None

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', in_signature='ssb')
    def NewSambaShare(self, shareName, srcPath, readonly, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)

        if not srcPath.startswith("/"):
            raise VirtServiceException("srcPath must be absoulte path")

        self.param.sambaServer.networkAddShare(self.nid, self.vmId, self.shareName, self.srcPath, self.readonly)

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', in_signature='i')
    def DeleteSambaShare(self, shareName, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)

        self.param.sambaServer.networkRemoveShare(self.nid, self.vmId, self.shareName)


class DbusVmObject(dbus.service.Object):

    def __init__(self, param, uid, vmid, owner):
        self.param = param
        self.uid = uid
        self.vmid = vmid
        self.owner = owner

        bus_name = dbus.service.BusName('org.fpemud.VirtService', bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/org/fpemud/VirtService/%d/VirtMachines/%d' % (self.uid, self.vmid))

    def release(self):
        self.remove_from_connection()
