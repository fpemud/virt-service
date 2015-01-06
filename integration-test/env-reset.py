#!/usr/bin/env python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import subprocess


prefixList = ["vnb", "vnn", "vnr", "vni"]


def getBridgeInterfaceList():
    global prefixList

    proc = subprocess.Popen("/usr/bin/ifconfig -a", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0]
    assert proc.returncode == 0

    ret = []
    for prefix in prefixList:
        for m in re.finditer("^(%s\\d+):" % (prefix), out, re.M):
            ret.append(m.group(1))
    return ret


def getSubInterfaceList():
    global prefixList

    proc = subprocess.Popen("/usr/bin/ifconfig -a", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0]
    assert proc.returncode == 0

    ret = []
    for prefix in prefixList:
        for m in re.finditer("^(%s\\d+\\.\\S+):" % (prefix), out, re.M):
            ret.append(m.group(1))
    return ret


def delTunTapInterface(intfname):
    brname, tapname = intfname.split(".")
    ret = subprocess.Popen('/bin/ifconfig "%s" down' % (tapname), shell=True).wait()
    assert ret
    ret = subprocess.Popen('/sbin/brctl delif "%s" "%s"' % (brname, tapname), shell=True).wait()
    assert ret
    ret = subprocess.Popen('/bin/ip tuntap del dev "%s" mode tap' % (tapname), shell=True).wait()
    assert ret


def delBridgeInterface(intfname):
    brname = intfname
    ret = subprocess.Popen('/bin/ifconfig "%s" down' % (brname), shell=True).wait()
    assert ret
    ret = subprocess.Popen('/sbin/brctl delbr "%s"' % (brname), shell=True).wait()
    assert ret


def getProcessId(execName):
    proc = subprocess.Popen("/usr/bin/ps -A", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0]
    assert proc.returncode == 0

    m = re.search("^ *(\\d+) +\\S+ +\\S+ +%s$" % (execName), out, re.M)
    if m is None:
        return None
    else:
        return int(m.group(1))


def killProcess(execName):
    bKilled = False
    for i in range(0, 5):
        proc = subprocess.Popen("/usr/bin/ps -A", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.communicate()[0]
        assert proc.returncode == 0

        m = re.search("^ *(\\d+) +\\S+ +\\S+ +%s$" % (execName), out, re.M)
        if m is None:
            return
        pid = int(m.group(1))

        if not bKilled:
            ret = subprocess.Popen('/usr/bin/kill %d' % (pid), shell=True).wait()
            assert ret
            bKilled = True

        time.sleep(1)

    assert False


if __name__ == "__main__":
    for subintf in getSubInterfaceList():
        print "Removing sub-interface %s." % (subintf)
        delTunTapInterface(subintf)

    for intf in getBridgeInterfaceList():
        print "Removing interface %s." % (intf)
        delBridgeInterface(intf)

    pid = getProcessId("virt-service")
    if pid is not None:
        print "Warning: virt-serivce process (id = %d) still exists." % (pid)
