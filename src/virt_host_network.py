#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sets
import dbus


class VirtHostNetwork:

    """The network management program on host machine"""

    def __init__(self):
        self.cbObjList = []              # callback objects
        self.intfSet = sets.Set()        # active interface name list

        # NetworkManager: register signal, fill self.intfSet
        if dbus.SystemBus().name_has_owner("org.freedesktop.NetworkManager"):
            nmObj = dbus.SystemBus().get_object('org.freedesktop.NetworkManager', '/org/freedesktop/NetworkManager')
            nmObj.connect_to_signal("PropertiesChanged", self._eventProcNetworkManagerPropertiesChanged, dbus_interface="org.freedesktop.NetworkManager")
            for oconn in nmObj.Get("org.freedesktop.NetworkManager", "ActiveConnections", dbus_interface="org.freedesktop.DBus.Properties"):
                connObj = dbus.SystemBus().get_object('org.freedesktop.NetworkManager', oconn)
                for odev in connObj.Get("org.freedesktop.NetworkManager.Connection.Active", "Devices", dbus_interface="org.freedesktop.DBus.Properties"):
                    devObj = dbus.SystemBus().get_object('org.freedesktop.NetworkManager', odev)
                    intf = devObj.Get("org.freedesktop.NetworkManager.Device", "IpInterface", dbus_interface="org.freedesktop.DBus.Properties")
                    self.intfSet.add(intf)

    def registerEventCallback(self, cbObject):
        assert isinstance(cbObject, VirtHostNetworkEventCallback)
        self.cbObjList.append(cbObject)

        for ai in self.intfSet:
            cbObject.onActiveInterfaceAdd(ai)

    def unregisterEventCallback(self, cbObject):
        assert isinstance(cbObject, VirtHostNetworkEventCallback)
        self.cbObjList.remove(cbObject)

    def _eventProcNetworkManagerPropertiesChanged(self, props):
        if 'ActiveConnections' not in props:
            return

        # get the new interface list
        newIntfSet = sets.Set()
        for oconn in props['ActiveConnections']:
            connObj = dbus.SystemBus().get_object('org.freedesktop.NetworkManager', oconn)
            for odev in connObj.Get("org.freedesktop.NetworkManager.Connection.Active", "Devices", dbus_interface="org.freedesktop.DBus.Properties"):
                devObj = dbus.SystemBus().get_object('org.freedesktop.NetworkManager', odev)
                intf = devObj.Get("org.freedesktop.NetworkManager.Device", "IpInterface", dbus_interface="org.freedesktop.DBus.Properties")
                newIntfSet.add(intf)

        # delete interfaces
        for ai in self.intfSet.difference(newIntfSet):
            for cbObject in self.cbObjList:
                cbObject.onActiveInterfaceRemove(ai)
            self.intfSet.remove(ai)

        # add interfaces
        for ai in newIntfSet.difference(self.intfSet):
            for cbObject in self.cbObjList:
                cbObject.onActiveInterfaceAdd(ai)
            self.intfSet.add(ai)


class VirtHostNetworkEventCallback:

    """Callback function of network event"""

    def onActiveInterfaceAdd(self, ifName):
        assert False

    def onActiveInterfaceRemove(self, ifName):
        assert False
