#!/usr/bin/python3.4
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import pwd
import grp
# import signal
import ipaddress
import configparser
from virt_util import VirtUtil
from virt_param import VirtInitializationError


class VirtSambaServer:

    def __init__(self, param):
        self.param = param
        self.netList = []
        self.uidDict = dict()
        self.shareDict = dict()

        if not os.path.exists("/usr/sbin/smbd"):
            raise VirtInitializationError("/usr/sbin/smbd not found")

        if not os.path.exists("/usr/bin/pdbedit"):
            raise VirtInitializationError("/usr/bin/pdbedit not found")

        if VirtUtil.getPidBySocket("0.0.0.0:139") == -1:
            raise VirtInitializationError("no samba server running")

        smbCfg = "/etc/samba/smb.conf"
        if not os.path.exists(smbCfg):
            raise VirtInitializationError("samba configuration file %s does not exists" % (smbCfg))

        cfg = None
        try:
            cfg = configparser.RawConfigParser()
            cfg.read("/etc/samba/smb.conf")
        except:
            raise VirtInitializationError("invalid samba configuration file %s" % (smbCfg))

        if not cfg.has_option("global", "security") or cfg.get("global", "security") != "user":
            raise VirtInitializationError("option \"global/security\" in samba configuration must have value \"user\"")

        if cfg.has_option("global", "passdb backend") and cfg.get("global", "passdb backend") != "tdbsam":
            raise VirtInitializationError("option \"global/passdb backend\" in samba configuration must have value \"tdbsam\"")

        if cfg.has_option("global", "workgroup") and cfg.get("global", "workgroup") != "WORKGROUP":
            raise VirtInitializationError("option \"global/workgroup\" in samba configuration must have value \"WORKGROUP\"")

        if not os.path.isdir("/etc/samba/hosts.d"):
            raise VirtInitializationError("per-host configuration directory (/etc/samba/hosts.d) does not exist")

        if cfg.has_option("global", "include") and cfg.get("global", "include") != "/etc/samba/hosts.d/%I.conf":
            raise VirtInitializationError("option \"global/include\" in samba configuration must have value \"/etc/samba/hosts.d/%I.conf\"")

        ret = VirtUtil.shell("/usr/bin/pdbedit -L", "stdout")
        m = re.search("^nobody:[0-9]+:.*$", ret, re.MULTILINE)
        if m is None:
            raise VirtInitializationError("main samba server must have user \"nobody\"")

    def release(self):
        assert len(self.uidDict) == 0
        assert len(self.shareDict) == 0

    def startOnNetwork(self, uid, netObj):
        self.netList.append(_NetworkInfo(netObj.netip, netObj.netmask, uid))

    def stopOnNetwork(self, netObj):
        try:
            self.netList.remove(_NetworkInfo(netObj.netip, netObj.netmask, None))
        except ValueError:
            pass

    def networkAddShare(self, vmIp, uid, shareName, srcPath, readonly):
        # return 0: success
        # return 1: share already exists;
        assert "_" not in shareName

        found = False
        for n in self.netList:
            if ipaddress.ip_address(vmIp) in ipaddress.ip_network("%s/%s" % (n.netip, n.netmask)):
                assert uid == n.uid
                found = True
                break
        assert found

        if vmIp not in self.shareDict:
            self.uidDict[vmIp] = uid
            self.shareDict[vmIp] = [_ShareInfo(shareName, srcPath, readonly)]
        else:
            assert self.uidDict[vmIp] == uid
            si = _ShareInfo(shareName, srcPath, readonly)
            if si in self.shareDict[vmIp]:
                return 1
            self.shareDict[vmIp].append(si)

        self._updateSambaCfg(vmIp)
        return 0

    def networkRemoveShare(self, vmIp, shareName):
        try:
            si = _ShareInfo(shareName, None, None)
            self.shareDict.get(vmIp, []).remove(si)
        except ValueError:
            pass

        if len(self.shareDict[vmIp]) == 0:
            del self.shareDict[vmIp]
            del self.uidDict[vmIp]

        self._updateSambaCfg(vmIp)

    def networkRemoveShareAll(self, vmIp):
        if vmIp in self.shareDict:
            del self.shareDict[vmIp]
            del self.uidDict[vmIp]
        self._updateSambaCfg(vmIp)

    def _updateSambaCfg(self, vmIp):
        cfgfile = "/etc/samba/hosts.d/%s.conf" % (vmIp)

        if vmIp not in self.shareDict:
            if os.path.exists(cfgfile):
                os.remove(cfgfile)
        else:
            username = pwd.getpwuid(self.uidDict[vmIp]).pw_name
            groupname = grp.getgrgid(pwd.getpwuid(self.uidDict[vmIp]).pw_gid).gr_name

            buf = ""
            for si in self.shareDict[vmIp]:
                buf += "[%s]\n" % (si.shareName)
                buf += "path = %s\n" % (si.srcPath)
                buf += "guest ok = yes\n"
                buf += "guest only = yes\n"
                buf += "force user = %s\n" % (username)
                buf += "force group = %s\n" % (groupname)
                if si.readonly:
                    buf += "writable = no\n"
                else:
                    buf += "writable = yes\n"
                buf += "hosts allow = %s\n" % (vmIp)
                buf += "\n"
            with open(cfgfile, "w") as f:
                f.write(buf)

        # tell samba to re-read configuration
        # os.kill(self.sambaPid, signal.SIGHUP)


class _NetworkInfo:

    def __init__(self, netip, netmask, uid):
        self.netip = netip
        self.netmask = netmask
        self.uid = uid

    def __eq__(self, other):
        return self.netip == other.netip and self.netmask == other.netmask

    def __ne__(self, other):
        return self.netip != other.netip and self.netmask == other.netmask


class _ShareInfo:

    def __init__(self, shareName, srcPath, readonly):
        self.shareName = shareName
        self.srcPath = srcPath
        self.readonly = readonly

    def __eq__(self, other):
        return self.shareName == other.shareName

    def __ne__(self, other):
        return self.shareName != other.shareName
