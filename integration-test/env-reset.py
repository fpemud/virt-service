#!/usr/bin/env python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import time
import subprocess


prefixList = ["vnb", "vnn", "vnr", "vni"]


def getBridgeInterfaceList():
    global prefixList

    proc = subprocess.Popen("/bin/ifconfig -a", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0]
    assert proc.returncode == 0

    ret = []
    for prefix in prefixList:
        for m in re.finditer("^(%s\\d+):" % (prefix), out, re.M):
            ret.append(m.group(1))
    return ret


def getSubInterfaceList():
    global prefixList

    proc = subprocess.Popen("/bin/ifconfig -a", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0]
    assert proc.returncode == 0

    ret = []
    for prefix in prefixList:
        for m in re.finditer("^(%s\\d+\\.\\S+):" % (prefix), out, re.M):
            ret.append(m.group(1))
    return ret


def delTunTapInterface(intfname):
    ret = subprocess.Popen('/bin/ifconfig "%s" down' % (intfname), shell=True).wait()
    assert ret == 0

    # bridge interface may not exists
    brname = intfname.split(".")[0]
    subprocess.Popen('/sbin/brctl delif "%s" "%s" > /dev/null' % (brname, intfname), shell=True).wait()

    ret = subprocess.Popen('/bin/ip tuntap del dev "%s" mode tap' % (intfname), shell=True).wait()
    assert ret == 0


def delBridgeInterface(intfname):
    brname = intfname
    ret = subprocess.Popen('/bin/ifconfig "%s" down' % (brname), shell=True).wait()
    assert ret == 0
    ret = subprocess.Popen('/sbin/brctl delbr "%s"' % (brname), shell=True).wait()
    assert ret == 0


def getProcessId(execName):
    proc = subprocess.Popen("/bin/ps -A", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
        proc = subprocess.Popen("/bin/ps -A", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.communicate()[0]
        assert proc.returncode == 0

        m = re.search("^ *(\\d+) +\\S+ +\\S+ +%s$" % (execName), out, re.M)
        if m is None:
            return
        pid = int(m.group(1))

        if not bKilled:
            ret = subprocess.Popen('/bin/kill %d' % (pid), shell=True).wait()
            assert ret == 0
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
    assert os.path.exists("/bin/rm")
    assert os.path.exists("/bin/ifconfig")
    assert os.path.exists("/bin/ip")
    assert os.path.exists("/bin/ps")
    assert os.path.exists("/bin/kill")
    assert os.path.exists("/sbin/brctl")
    assert os.path.exists("/sbin/nft")
    assert os.getuid() == 0

    for subintf in getSubInterfaceList():
        print("Removing sub-interface %s." % (subintf))
        delTunTapInterface(subintf)

    for intf in getBridgeInterfaceList():
        print("Removing interface %s." % (intf))
        delBridgeInterface(intf)

    if getProcessId("virt-service") is not None:
        print("Killing process virt-service")
        killProcess("virt-service")

    if getProcessId("dnsmasq") is not None:
        print("Killing process dnsmasq")
        killProcess("dnsmasq")

    if os.path.exists("/tmp/virt-service"):
        print("Removing directory /tmp/virt-service")
        ret = subprocess.Popen('/bin/rm -rf /tmp/virt-service', shell=True).wait()
        assert ret == 0

    if readFile("/proc/sys/net/ipv4/ip_forward").strip() != "0":
        print("Resetting /proc/sys/net/ipv4/ip_forward")
        writeFile("/proc/sys/net/ipv4/ip_forward", "0")

    if True:
        proc = subprocess.Popen("/sbin/nft list tables", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.communicate()[0]
        assert proc.returncode == 0
        if re.search("^table ip virt-service-nat$", out, re.M) is not None:
            print("Deleting nftable virt-service-nat")
            subprocess.Popen("/sbin/nft delete table virt-service-nat", shell=True).wait()
