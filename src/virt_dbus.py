#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import dbus
import dbus.service
from gi.repository import GLib
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
#   (devpath:string)                   GetVfioDevInfo(dev_id:int)
#
#   void                               AddTapIntf(network_name:string)
#   void                               RemoveTapIntf()
#   void                               NewSambaShare(share_name:string, share_path:string, readonly:boolean)
#   void                               DeleteSambaShare(share_name:string)
#   dev_id:int                         AddVfioDevice(devName:string, vfioType:string)
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
        # nothing to do if len(self.resSetDict) > 0 or len(self.vmDict) > 0
        dbus.SystemBus().remove_signal_receiver(self.handle)
        self.remove_from_connection()

    def onNameOwnerChanged(self, name, old, new):
        # focus on name deletion, filter other circumstance
        if not name.startswith(":") or new != "":
            return
        assert name == old

        for vmu in self.vmDict.values():
            for vm in vmu.values():
                if vm.owner == old:
                    self._vmRemove(vm.uid, vm.vmid, vm)

        for ressetu in self.resSetDict.values():
            for resset in ressetu.values():
                if resset.owner == old:
                    self._resSetRemove(resset.uid, resset.sid, resset)

        # add timeout
        if len(self.resSetDict) == 0 and self.param.timeoutHandler is None:
            self.param.timeoutHandler = GLib.timeout_add_seconds(self.param.timeout, lambda *args: self.param.mainloop.quit())

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', out_signature='i')
    def NewVmResSet(self, sender=None):
        self._checkInitError()
        uid = VirtUtil.dbusGetUserId(self.connection, sender)

        # create new resource set object
        sid = None
        if uid not in self.resSetDict:
            self.resSetDict[uid] = dict()
        try:
            sid = VirtUtil.allocId(self.resSetDict[uid])
            if sid > 128:
                raise VirtServiceException("too many virt-machine resource set allocated")

            sObj = DbusResSetObject(self.param, uid, sid, sender)
            self.resSetDict[uid][sid] = sObj
        except:
            if len(self.resSetDict[uid]) == 0:
                del self.resSetDict[uid]
            raise

        # remove timeout
        if self.param.timeoutHandler is not None:
            GLib.source_remove(self.param.timeoutHandler)
            self.param.timeoutHandler = None

        return sid

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', in_signature='i')
    def DeleteVmResSet(self, sid, sender=None):
        self._checkInitError()
        uid = VirtUtil.dbusGetUserId(self.connection, sender)

        resset = self._resSetGet(uid, sid)
        if resset is None:
            raise VirtServiceException("virt-machine resource set not found")

        vm = self._resSetGetAttachedVm(uid, sid)
        if vm is not None:
            raise VirtServiceException("virt-machine resource set has been binded to virt-machine %s" % (vm.name))

        self._resSetRemove(uid, sid, resset)

        # add timeout
        assert self.param.timeoutHandler is None
        if len(self.resSetDict) == 0:
            self.param.timeoutHandler = GLib.timeout_add_seconds(self.param.timeout, lambda *args: self.param.mainloop.quit())

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', in_signature='si', out_signature='i')
    def AttachVm(self, vmname, sid, sender=None):
        self._checkInitError()
        uid = VirtUtil.dbusGetUserId(self.connection, sender)

        resset = self._resSetGet(uid, sid)
        if resset is None:
            raise VirtServiceException("virt-machine resource set not found")

        vm = self._resSetGetAttachedVm(uid, sid)
        if vm is not None:
            raise VirtServiceException("virt-machine resource set has been binded to virt-machine %s" % (vm.name))

        # create new vm object, using sid as vmid
        if uid not in self.vmDict:
            self.vmDict[uid] = dict()
        try:
            vmid = sid
            vmObj = DbusVmObject(self.param, uid, vmid, sender)
            self.vmDict[uid][vmid] = vmObj
            return vmid
        except:
            if len(self.vmDict[uid]) == 0:
                del self.vmDict[uid]
            raise

    @dbus.service.method('org.fpemud.VirtService', sender_keyword='sender', in_signature='i')
    def DetachVm(self, vmid, sender=None):
        self._checkInitError()
        uid = VirtUtil.dbusGetUserId(self.connection, sender)

        vm = self._vmGet(uid, vmid)
        if vm is None:
            raise VirtServiceException("virt-machine not found")

        self._vmRemove(uid, vmid, vm)

    def _checkInitError(self):
        if self.param.initError is not None:
            raise VirtServiceException("virt-service initialization failed, %s" % (self.param.initError))

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
            for vmObj in self.vmDict[uid].values():
                if vmObj.vmid == sid:
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
        if self.networkName is not None:
            vmip = self.param.netManager.getVmIp(self.uid, self.networkName, self.sid)
            self.param.sambaServer.networkRemoveShareAll(vmip)
            self.param.netManager.removeTapIntf(self.uid, self.networkName, self.sid)
            self.param.netManager.removeNetwork(self.uid, self.networkName)
            self.networkName = None
        self.remove_from_connection()

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', out_signature='s')
    def GetTapIntf(self, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)
        if self.networkName is None:
            raise VirtServiceException("no tap interface found in the specified virt-machine resource set")
        return self.param.netManager.getTapIntf(self.uid, self.networkName, self.sid)

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', out_signature='s')
    def GetVmMacAddr(self, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)
        if self.networkName is None:
            raise VirtServiceException("no tap interface found in the specified virt-machine resource set")
        return self.param.netManager.getVmMac(self.uid, self.networkName, self.sid)

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', out_signature='s')
    def GetVmIpAddr(self, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)
        if self.networkName is None:
            raise VirtServiceException("no tap interface found in the specified virt-machine resource set")
        return self.param.netManager.getVmIp(self.uid, self.networkName, self.sid)

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', in_signature='s')
    def AddTapIntf(self, network_name, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)
        if self.networkName is not None:
            raise VirtServiceException("tap interface exists in the specified virt-machine resource set")

        self.param.netManager.addNetwork(self.uid, network_name)
        self.param.netManager.addTapIntf(self.uid, network_name, self.sid)
        self.networkName = network_name

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender')
    def RemoveTapIntf(self, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)

        if self.networkName is None:
            return

        self.param.netManager.removeTapIntf(self.uid, self.networkName, self.sid)
        self.param.netManager.removeNetwork(self.uid, self.networkName)
        self.networkName = None

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', in_signature='ssb')
    def NewSambaShare(self, share_name, share_path, readonly, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)

        if not os.path.isabs(share_path):
            raise VirtServiceException("share_path must be absoulte path")
        if self.networkName is None:
            raise VirtServiceException("no network resource found in the specified virt-machine resource set")

        vmip = self.param.netManager.getVmIp(self.uid, self.networkName, self.sid)
        ret = self.param.sambaServer.networkAddShare(vmip, self.uid, share_name, share_path, readonly)
        if ret == 0:
            pass
        elif ret == 1:
            raise VirtServiceException("the specified samba share duplicates")
        else:
            assert False

    @dbus.service.method('org.fpemud.VirtService.VmResSet', sender_keyword='sender', in_signature='i')
    def DeleteSambaShare(self, share_name, sender):
        assert self.uid == VirtUtil.dbusGetUserId(self.connection, sender)

        if self.networkName is None:
            return

        vmip = self.param.netManager.getVmIp(self.uid, self.networkName, self.sid)
        self.param.sambaServer.networkRemoveShare(vmip, share_name)


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
