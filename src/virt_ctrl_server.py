#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import socket
from gi.repository import GLib


class VirtCtrlServer:

    def __init__(self, param):
        self.param = param
        self.serverObjDict = dict()
        self.vccList = []              # vm control channel list

    def release(self):
        assert len(self.networkDict) == 0

    def addNetwork(self, uid, nid, serverIp):
        assert serverIp.endswith(".1")
        self.serverObjDict[(uid, nid)] = _ServerObj(self, serverIp, self.param.ctrlPort)

    def removeNetwork(self, uid, nid):
        key = (uid, nid)
        serverObj = self.serverObjDict.pop(key)
        serverObj.release()

    def vmcExists(self, vmName):
        pass

    def vmcAddSambaShare(self, vmIp):
        # vcc = self._getVcc(vmIp)
        pass

    def vmcRemoveSambaShare(self, vmIp):
        # vmt = self._getVmTriple(vmIp)
        pass

    def _getVcc(self, vmIp):
        for s in self.vccList:
            if s.addr == vmIp:
                return s
        s = _VmControlChannel(vmIp)
        self.vccList.append(s)
        return s


class _ServerObj:

    def __init__(self, parentObj, serverIp, serverPort):
        self.flagError = GLib.IO_PRI | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL
        self.parentObj = parentObj
        self.serverIp = serverIp
        self.serverPort = serverPort

        self.ss = socket.socket(socket.AF_INET, socket.SOCK_STREAM)                                 # server socket
        self.ss.bind((self.serverIp, self.serverPort))
        self.ss.listen(5)
        self.hAccept = GLib.io_add_watch(self.ss, GLib.IO_IN | self.flagError, self._onAccept)

    def release(self):
        pass

    def _onAccept(self, source, cb_condition):
        assert not (cb_condition & self.flagError)
        assert source == self.ss
        try:
            new_sock, addr = self.ss.accept()
        except socket.error:
            pass
        return True


class _VmControlChannel:

    def __init__(self, addr):
        self.addr = addr
        self.sock = None
        self.msgQueue = []

    def send(self, obj):
        pass
