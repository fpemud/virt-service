#!/usr/bin/env python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import time
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
    brname = intfname.split(".")[0]
    ret = subprocess.Popen('/usr/bin/ifconfig "%s" down' % (intfname), shell=True).wait()
    assert ret == 0
    ret = subprocess.Popen('/usr/sbin/brctl delif "%s" "%s"' % (brname, intfname), shell=True).wait()
    assert ret == 0
    ret = subprocess.Popen('/usr/bin/ip tuntap del dev "%s" mode tap' % (intfname), shell=True).wait()
    assert ret == 0


def delBridgeInterface(intfname):
    brname = intfname
    ret = subprocess.Popen('/usr/bin/ifconfig "%s" down' % (brname), shell=True).wait()
    assert ret == 0
    ret = subprocess.Popen('/usr/sbin/brctl delbr "%s"' % (brname), shell=True).wait()
    assert ret == 0


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


def readFile(filename):
    with open(filename, "r") as f:
        return f.read()


def writeFile(filename, buf):
    with open(filename, "w") as f:
        f.write(buf)


if __name__ == "__main__":
    assert os.path.exists("/usr/bin/rm")
    assert os.path.exists("/usr/bin/ifconfig")
    assert os.path.exists("/usr/bin/ip")
    assert os.path.exists("/usr/bin/ps")
    assert os.path.exists("/usr/bin/kill")
    assert os.path.exists("/usr/sbin/brctl")
    assert os.path.exists("/usr/sbin/nft")

    for subintf in getSubInterfaceList():
        print("Removing sub-interface %s." % (subintf))
        delTunTapInterface(subintf)

    for intf in getBridgeInterfaceList():
        print("Removing interface %s." % (intf))
        delBridgeInterface(intf)

    if getProcessId("virt-service") is not None:
        killProcess("virt-service")

    if os.path.exists("/tmp/virt-service"):
        print("Removing directory /tmp/virt-service")
        ret = subprocess.Popen('/usr/bin/rm -rf /tmp/virt-service', shell=True).wait()
        assert ret == 0

    if readFile("/proc/sys/net/ipv4/ip_forward").strip() != "0":
        print("Resetting /proc/sys/net/ipv4/ip_forward")
        writeFile("/proc/sys/net/ipv4/ip_forward", "0")

    if True:
        proc = subprocess.Popen("/usr/sbin/nft list tables", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.communicate()[0]
        assert proc.returncode == 0
        if re.search("^table virt-service-nat$", out, re.M) is not None:
            print("Deleting nftable virt-service-nat")
            subprocess.Popen("/usr/sbin/nft delete table virt-service-nat", shell=True).wait()