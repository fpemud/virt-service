#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import subprocess
import time
import grp
import pwd
import socket
import re


class VirtUtil:

    @staticmethod
    def allocId(dictObj, startId=1):
        sid = startId
        while True:
            if sid not in dictObj:
                return sid
            sid = sid + 1
            continue

    @staticmethod
    def getSysctl(name):
        msg = VirtUtil.shell("/sbin/sysctl -n %s" % (name), "stdout")
        return msg.rstrip('\n')

    @staticmethod
    def setSysctl(name, value):
        return

    @staticmethod
    def copyToDir(srcFilename, dstdir, mode=None):
        """Copy file to specified directory, and set file mode if required"""

        if not os.path.isdir(dstdir):
            os.makedirs(dstdir)
        fdst = os.path.join(dstdir, os.path.basename(srcFilename))
        shutil.copy(srcFilename, fdst)
        if mode is not None:
            VirtUtil.shell("/bin/chmod " + mode + " \"" + fdst + "\"")

    @staticmethod
    def copyToFile(srcFilename, dstFilename, mode=None):
        """Copy file to specified filename, and set file mode if required"""

        if not os.path.isdir(os.path.dirname(dstFilename)):
            os.makedirs(os.path.dirname(dstFilename))
        shutil.copy(srcFilename, dstFilename)
        if mode is not None:
            VirtUtil.shell("/bin/chmod " + mode + " \"" + dstFilename + "\"")

    @staticmethod
    def readFile(filename):
        """Read file, returns the whold content"""

        f = open(filename, 'r')
        buf = f.read()
        f.close()
        return buf

    @staticmethod
    def writeFile(filename, buf, mode=None):
        """Write buffer to file"""

        f = open(filename, 'w')
        f.write(buf)
        f.close()
        if mode is not None:
            VirtUtil.shell("/bin/chmod " + mode + " \"" + filename + "\"")

    @staticmethod
    def mkDirAndClear(dirname):
        VirtUtil.forceDelete(dirname)
        os.mkdir(dirname)

    @staticmethod
    def touchFile(filename):
        assert not os.path.exists(filename)
        f = open(filename, 'w')
        f.close()

    @staticmethod
    def forceDelete(filename):
        if os.path.islink(filename):
            os.remove(filename)
        elif os.path.isfile(filename):
            os.remove(filename)
        elif os.path.isdir(filename):
            shutil.rmtree(filename)

    @staticmethod
    def forceSymlink(source, link_name):
        if os.path.exists(link_name):
            os.remove(link_name)
        os.symlink(source, link_name)

    @staticmethod
    def isSocketPortUsed(portType, port):
        if portType == "tcp":
            sType = socket.SOCK_STREAM
        elif portType == "udp":
            sType = socket.SOCK_DGRAM
        else:
            assert False

        s = socket.socket(socket.AF_INET, sType)
        try:
            s.bind((('', port)))
            return False
        except socket.error:
            return True
        finally:
            s.close()

    @staticmethod
    def getFreeSocketPort(portType, portStart, portEnd):
        if portType == "tcp":
            sType = socket.SOCK_STREAM
        elif portType == "udp":
            assert False
        else:
            assert False

        for port in range(portStart, portEnd + 1):
            s = socket.socket(socket.AF_INET, sType)
            try:
                s.bind((('', port)))
                return port
            except socket.error:
                continue
            finally:
                s.close()
        raise Exception("No valid %s port in [%d,%d]." % (portType, portStart, portEnd))

    @staticmethod
    def shell(cmd, flags=""):
        """Execute shell command"""

        assert cmd.startswith("/")

        # Execute shell command, throws exception when failed
        if flags == "":
            retcode = subprocess.Popen(cmd, shell=True, universal_newlines=True).wait()
            if retcode != 0:
                raise Exception("Executing shell command \"%s\" failed, return code %d" % (cmd, retcode))
            return

        # Execute shell command, throws exception when failed, returns stdout+stderr
        if flags == "stdout":
            proc = subprocess.Popen(cmd,
                                    shell=True, universal_newlines=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            out = proc.communicate()[0]
            if proc.returncode != 0:
                raise Exception("Executing shell command \"%s\" failed, return code %d, output %s" % (cmd, proc.returncode, out))
            return out

        # Execute shell command, returns (returncode,stdout+stderr)
        if flags == "retcode+stdout":
            proc = subprocess.Popen(cmd,
                                    shell=True, universal_newlines=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            out = proc.communicate()[0]
            return (proc.returncode, out)

        assert False

    @staticmethod
    def shellInteractive(cmd, strInput, flags=""):
        """Execute shell command with input interaction"""

        assert cmd.startswith("/")

        # Execute shell command, throws exception when failed
        if flags == "":
            proc = subprocess.Popen(cmd,
                                    shell=True, universal_newlines=True,
                                    stdin=subprocess.PIPE)
            proc.communicate(strInput)
            if proc.returncode != 0:
                raise Exception("Executing shell command \"%s\" failed, return code %d" % (cmd, proc.returncode))
            return

        # Execute shell command, throws exception when failed, returns stdout+stderr
        if flags == "stdout":
            proc = subprocess.Popen(cmd,
                                    shell=True, universal_newlines=True,
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            out = proc.communicate(strInput)[0]
            if proc.returncode != 0:
                raise Exception("Executing shell command \"%s\" failed, return code %d, output %s" % (cmd, proc.returncode, out))
            return out

        # Execute shell command, returns (returncode,stdout+stderr)
        if flags == "retcode+stdout":
            proc = subprocess.Popen(cmd,
                                    shell=True, universal_newlines=True,
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            out = proc.communicate(strInput)[0]
            return (proc.returncode, out)

        assert False

    @staticmethod
    def ipMaskToLen(mask):
        """255.255.255.0 -> 24"""

        netmask = 0
        netmasks = mask.split('.')
        for i in range(0, len(netmasks)):
            netmask *= 256
            netmask += int(netmasks[i])
        return 32 - (netmask ^ 0xFFFFFFFF).bit_length()

    @staticmethod
    def loadKernelModule(modname):
        """Loads a kernel module."""

        VirtUtil.shell("/sbin/modprobe %s" % (modname))

    @staticmethod
    def initLog(filename):
        VirtUtil.forceDelete(filename)
        VirtUtil.writeFile(filename, "")

    @staticmethod
    def printLog(filename, msg):
        f = open(filename, 'a')
        if msg != "":
            f.write(time.strftime("%Y-%m-%d %H:%M:%S  ", time.localtime()))
            f.write(msg)
            f.write("\n")
        else:
            f.write("\n")
        f.close()

    @staticmethod
    def getUsername():
        return pwd.getpwuid(os.getuid())[0]

    @staticmethod
    def getGroups():
        """Returns the group name list of the current user"""

        uname = pwd.getpwuid(os.getuid())[0]
        groups = [g.gr_name for g in grp.getgrall() if uname in g.gr_mem]
        gid = pwd.getpwnam(uname).pw_gid
        groups.append(grp.getgrgid(gid).gr_name)            # --fixme, should be prepend
        return groups

    @staticmethod
    def getMaxTapId(brname):
        ret = VirtUtil.shell('/bin/ifconfig -a', 'stdout')
        matchList = re.findall("^%s.([0-9]+):" % (brname), ret, re.MULTILINE)
        maxId = 0
        for m in matchList:
            if int(m) > maxId:
                maxId = int(m)
        return maxId

    @staticmethod
    def getPidBySocket(socketInfo):
        """need to be run by root. socketInfo is like 0.0.0.0:80"""

        rc, ret = VirtUtil.shell("/bin/netstat -anp | grep \"%s\"" % (socketInfo), "retcode+stdout")
        if rc != 0:
            return -1

        m = re.search(" +([0-9]+)/.*$", ret, re.MULTILINE)
        assert m is not None
        return int(m.group(1))

    @staticmethod
    def dbusGetUserId(connection, sender):
        if sender is None:
            raise Exception("only accept user access")
        return connection.get_unix_user(sender)

    @staticmethod
    def dbusCheckUserId(connection, sender, uid):
        if sender is None:
            raise Exception("only accept user access")
        if connection.get_unix_user(sender) != uid:
            raise Exception("priviledge violation")

    @staticmethod
    def tdbFileCreate(filename):
        assert " " not in filename            # fixme, tdbtool can't operate filename with space

        inStr = ""
        inStr += "create %s\n" % (filename)
        inStr += "quit\n"
        VirtUtil.shellInteractive("/usr/bin/tdbtool", inStr)

    @staticmethod
    def tdbFileAddUser(filename, username, password):
        """can only add unix user"""

        assert " " not in filename            # fixme, v can't operate filename with space

        inStr = ""
        inStr += "%s\n" % (password)
        inStr += "%s\n" % (password)
        VirtUtil.shellInteractive("/usr/bin/pdbedit -b tdbsam:%s -a \"%s\" -t" % (filename, username), inStr)
