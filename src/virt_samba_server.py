#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import pwd
import grp
import shutil
import signal
import subprocess
import configparser
from virt_util import VirtUtil


class VirtSambaServer:

    """If there's a global samba server, then use that server, else we start a new samba server
       Use one server to serve all the networks"""

    def __init__(self, param):
        self.param = param
        self.networkDict = dict()
        self.serverObj = None

    def release(self):
        assert len(self.networkDict) == 0

    def addNetwork(self, uid, nid, serverPort):
        key = (uid, nid)
        value = _NetworkInfo(uid, serverPort)
        self.networkDict[key] = value

    def removeNetwork(self, uid, nid):
        key = (uid, nid)
        assert len(self.networkDict[key].shareDict) == 0
        del self.networkDict[key]

    def networkGetAccountInfo(self, uid, nid):
        """return (username, password)"""
        return ("guest", "")

    def networkAddShare(self, uid, nid, vmId, shareName, srcPath, readonly):
        assert "_" not in shareName

        # get _NetworkInfo
        key = (uid, nid)
        netInfo = self.networkDict[key]

        # add ShareInfo
        key = (vmId, shareName)
        value = _ShareInfo(srcPath, readonly)
        netInfo.shareDict[key] = value

        # enable or update server
        if self.serverObj is None:
            self._startServer()
        else:
            self.serverObj.updateShare()

    def networkRemoveShare(self, uid, nid, vmId, shareName):

        # get _NetworkInfo
        key = (uid, nid)
        netInfo = self.networkDict[key]

        # delete ShareInfo
        key = (vmId, shareName)
        del netInfo.shareDict[key]

        # disable or update server
        bShouldDisable = True
        for netInfo in list(self.networkDict.values()):
            if len(netInfo.shareDict) > 0:
                bShouldDisable = False
                break

        if bShouldDisable:
            self._stopServer()
        else:
            self.serverObj.updateShare()

    def _startServer(self):
        assert self.serverObj is None

        pid = VirtUtil.getPidBySocket("0.0.0.0:139")
        if pid != -1:
            self.serverObj = _ServerGlobal(self, pid)
            try:
                self.serverObj.checkServer()
            except:
                self.serverObj.release()
                self.serverObj = None
                raise
        else:
            self.serverObj = _ServerLocal(self)

    def _stopServer(self):
        self.serverObj.release()
        self.serverObj = None


class _NetworkInfo:

    def __init__(self, uid, serverPort):
        self.serverPort = serverPort
        self.username = pwd.getpwuid(uid).pw_name
        self.groupname = grp.getgrgid(pwd.getpwuid(uid).pw_gid).gr_name
        self.shareDict = dict()


class _ShareInfo:

    def __init__(self, srcPath, readonly):
        self.srcPath = srcPath
        self.readonly = readonly


class _ServerGlobal:

    """The configuration of global server can't be modified when it's running"""

    def __init__(self, pObj, sambaPid):
        self.param = pObj.param
        self.pObj = pObj                # parent object
        self.sambaPid = sambaPid

        self.confDir = "/etc/samba"

        self.updateShare()

    def release(self):
        os.kill(self.sambaPid, signal.SIGHUP)

    def checkServer(self):
        """Check if the configure of global server satisfy our requirement"""

        cfg = configparser.RawConfigParser()
        cfg.read("/etc/samba/smb.conf")

        if not cfg.has_option("global", "security") or cfg.get("global", "security") != "user":
            raise Exception("option \"global/security\" of main samba server must have value \"user\"")

        if cfg.has_option("global", "passdb backend") and cfg.get("global", "passdb backend") != "tdbsam":
            raise Exception("option \"global/passdb backend\" of main samba server must have value \"tdbsam\"")

        if cfg.has_option("global", "workgroup") and cfg.get("global", "workgroup") != "WORKGROUP":
            raise Exception("option \"global/workgroup\" of main samba server must have value \"WORKGROUP\"")

        if not os.path.isdir("/etc/samba/hosts.d"):
            raise Exception("per-host configuration directory (/etc/samba/hosts.d) does not exist")
        if cfg.has_option("global", "include") and cfg.get("global", "include") != "/etc/samba/hosts.d/%I.conf":
            raise Exception("option \"global/include\" of main samba server must have value \"/etc/samba/hosts.d/%I.conf\"")

        ret = VirtUtil.shell("/usr/bin/pdbedit -L", "stdout")
        m = re.search("^nobody:[0-9]+:.*$", ret, re.MULTILINE)
        if m is None:
            raise Exception("main samba server must have user \"nobody\"")

    def updateShare(self):
        # recreate all the share files
        _MyUtil.genShareFiles("/etc/samba/hosts.d", self.param, self.pObj.networkDict)

        # update samba
        os.kill(self.sambaPid, signal.SIGHUP)


class _ServerLocal:

    def __init__(self, pObj):
        self.param = pObj.param
        self.pObj = pObj        # parent object

        self.servDir = os.path.join(self.pObj.param.tmpDir, "samba")
        self.confFile = os.path.join(self.servDir, "smb.conf")
        self.passdbFile = os.path.join(self.servDir, "passdb.tdb")

        try:
            os.mkdir(self.servDir)
            self._genPassdbFile()
            self._genSmbdConf()
            self.serverProc = subprocess.Popen(self._genSmbdCommand(), shell=True)
        except:
            shutil.rmtree(self.servDir)
            raise

    def release(self):
        self.serverProc.terminate()
        self.serverProc.wait()
        self.serverProc = None
        shutil.rmtree(self.servDir)

    def updateShare(self):
        self._genSmbdConf()
        self.serverProc.send_signal(signal.SIGHUP)

    def _genPassdbFile(self):
        VirtUtil.tdbFileCreate(self.passdbFile)

    def _genSmbdConf(self):

        # get interface list
        ifList = []
        for netInfo in list(self.pObj.networkDict.values()):
            ifList.append(netInfo.serverPort)

        # generate smb.conf
        buf = ""
        buf += "[global]\n"
        buf += "security                   = user\n"
        buf += "bind interfaces only       = yes\n"
        buf += "interfaces                 = %s\n" % (" ".join(ifList))
        buf += "private dir                = %s\n" % (self.servDir)
        buf += "pid directory              = %s\n" % (self.servDir)
        buf += "lock directory             = %s\n" % (self.servDir)
        buf += "state directory            = %s\n" % (self.servDir)
        buf += "log file                   = %s/log.smbd\n" % (self.servDir)
        buf += "\n\n"
        buf += "include                    = %%m.conf\n"
        buf += "\n"
        VirtUtil.writeFile(self.confFile, buf)

        # generate share files
        _MyUtil.genShareFiles(self.servDir, self.param, self.pObj.networkDict)

    def _genSmbdCommand(self):

        cmd = "/sbin/smbd"
        cmd += " -F"                            # don't run as daemon, so we can control it
        cmd += " -s \"%s\"" % (self.confFile)
        return cmd


class _MyUtil:

    @staticmethod
    def genShareFiles(dstDir, param, networkDict):
        # create all the share files
        sfDict = dict()
        for nkey, netInfo in list(networkDict.items()):
            uid = nkey[0]
            nid = nkey[1]
            for skey, value in list(netInfo.shareDict.items()):
                vmId = skey[0]
                shareName = skey[1]
                vmIp = VirtUtil.getVmIpAddress(param.ip1, uid, nid, vmId)
                if vmIp not in sfDict:
                    sfDict[vmIp] = ""
                sfDict[vmIp] += _MyUtil.genSharePart(uid, nid, vmId, vmIp, netInfo.username, netInfo.groupname,
                                                     shareName, value.srcPath, value.readonly)
                sfDict[vmIp] += "\n"
        for vmIp, fileBuf in list(sfDict.items()):
            VirtUtil.writeFile(os.path.join(dstDir, "%s.conf" % (vmIp)), fileBuf)

    @staticmethod
    def genSharePart(uid, nid, vmId, vmIp, username, groupname, shareName, srcPath, readonly):
        assert "_" not in shareName

        buf = ""
        buf += "[%d_%d_%d_%s]\n" % (uid, nid, vmId, shareName)
        buf += "path = %s\n" % (srcPath)
        buf += "guest ok = yes\n"
        buf += "guest only = yes\n"
        buf += "force user = %s\n" % (username)
        buf += "force group = %s\n" % (groupname)
        if readonly:
            buf += "writable = no\n"
        else:
            buf += "writable = yes\n"
        buf += "hosts allow = %s\n" % (vmIp)

        return buf
