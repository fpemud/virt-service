#!/usr/bin/env python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import dbus
import subprocess
import unittest


class Test_ResSet_Basic(unittest.TestCase):

    def setUp(self):
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.uid = os.getuid()

    def runTest(self):
        sid = self.dbusObj.NewVmResSet(dbus_interface='org.fpemud.VirtService')
        dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService/%d/VmResSets/%d' % (self.uid, sid))

        self.dbusObj.DeleteVmResSet(sid, dbus_interface='org.fpemud.VirtService')

    def tearDown(self):
        pass


class Test_ResSet_TapIntfNat(unittest.TestCase):

    def setUp(self):
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.uid = os.getuid()

    def runTest(self):
        sid = self.dbusObj.NewVmResSet(dbus_interface='org.fpemud.VirtService')
        obj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService/%d/VmResSets/%d' % (self.uid, sid))

        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")
        self.assertFalse(_intfExists("vnb1"))

        obj.AddTapIntf("nat", dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "1")
        self.assertTrue(_intfExists("vnb1"))
        self.assertTrue(_intfExists("vnb1.1"))

        obj.RemoveTapIntf(dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")
        self.assertFalse(_intfExists("vnb1"))
        self.assertFalse(_intfExists("vnb1.1"))

        self.dbusObj.DeleteVmResSet(sid, dbus_interface='org.fpemud.VirtService')

    def tearDown(self):
        pass


class Test_ResSet_SambaShare(unittest.TestCase):

    def setUp(self):
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.uid = os.getuid()

    def runTest(self):
        sid = self.dbusObj.NewVmResSet(dbus_interface='org.fpemud.VirtService')
        obj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService/%d/VmResSets/%d' % (self.uid, sid))
        obj.AddTapIntf("nat", dbus_interface='org.fpemud.VirtService.VmResSet')

        obj.NewSambaShare("abc", os.getcwd(), True, dbus_interface='org.fpemud.VirtService.VmResSet')
        self.assertTrue(os.path.exists("/etc/samba/hosts.d/10.0.1.12.conf"))
        self.assertTrue("[abc]\n" in open("/etc/samba/hosts.d/10.0.1.12.conf").read())

        obj.NewSambaShare("abc2", os.getcwd(), True, dbus_interface='org.fpemud.VirtService.VmResSet')
        self.assertTrue("[abc]\n" in open("/etc/samba/hosts.d/10.0.1.12.conf").read())
        self.assertTrue("[abc2]\n" in open("/etc/samba/hosts.d/10.0.1.12.conf").read())

        obj.DeleteSambaShare("abc", dbus_interface='org.fpemud.VirtService.VmResSet')
        self.assertTrue(os.path.exists("/etc/samba/hosts.d/10.0.1.12.conf"))
        self.assertTrue("[abc2]\n" in open("/etc/samba/hosts.d/10.0.1.12.conf").read())
        self.assertFalse("[abc]\n" in open("/etc/samba/hosts.d/10.0.1.12.conf").read())

        obj.DeleteSambaShare("abc2", dbus_interface='org.fpemud.VirtService.VmResSet')
        self.assertTrue(len(os.listdir("/etc/samba/hosts.d")) == 0)

        obj.RemoveTapIntf(dbus_interface='org.fpemud.VirtService.VmResSet')
        self.dbusObj.DeleteVmResSet(sid, dbus_interface='org.fpemud.VirtService')

    def tearDown(self):
        pass


class Test_ResSet_MultiInstance(unittest.TestCase):

    def setUp(self):
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.uid = os.getuid()

    def runTest(self):
        sid = self.dbusObj.NewVmResSet(dbus_interface='org.fpemud.VirtService')
        obj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService/%d/VmResSets/%d' % (self.uid, sid))

        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")
        self.assertFalse(_intfExists("vnb1"))

        obj.AddTapIntf("nat", dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "1")
        self.assertTrue(_intfExists("vnb1"))
        self.assertTrue(_intfExists("vnb1.1"))

        obj.NewSambaShare("abc", os.getcwd(), True, dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertTrue(os.path.exists("/etc/samba/hosts.d/10.0.1.12.conf"))
        self.assertTrue("[abc]\n" in open("/etc/samba/hosts.d/10.0.1.12.conf").read())

        obj.NewSambaShare("abc2", os.getcwd(), True, dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertTrue("[abc]\n" in open("/etc/samba/hosts.d/10.0.1.12.conf").read())
        self.assertTrue("[abc2]\n" in open("/etc/samba/hosts.d/10.0.1.12.conf").read())

        sid2 = self.dbusObj.NewVmResSet(dbus_interface='org.fpemud.VirtService')
        obj2 = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService/%d/VmResSets/%d' % (self.uid, sid2))
        obj2.AddTapIntf("nat", dbus_interface='org.fpemud.VirtService.VmResSet')
        obj2.NewSambaShare("abc", os.getcwd(), True, dbus_interface='org.fpemud.VirtService.VmResSet')
        obj2.NewSambaShare("abc2", os.getcwd(), True, dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "1")
        self.assertTrue(_intfExists("vnb1"))
        self.assertTrue(_intfExists("vnb1.1"))
        self.assertTrue(_intfExists("vnb1.2"))
        self.assertTrue(os.path.exists("/etc/samba/hosts.d/10.0.1.13.conf"))
        self.assertTrue("[abc]\n" in open("/etc/samba/hosts.d/10.0.1.13.conf").read())
        self.assertTrue("[abc2]\n" in open("/etc/samba/hosts.d/10.0.1.13.conf").read())

        obj.DeleteSambaShare("abc", dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertTrue(os.path.exists("/etc/samba/hosts.d/10.0.1.12.conf"))
        self.assertTrue("[abc2]\n" in open("/etc/samba/hosts.d/10.0.1.12.conf").read())
        self.assertFalse("[abc]\n" in open("/etc/samba/hosts.d/10.0.1.12.conf").read())

        obj.DeleteSambaShare("abc2", dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertFalse(os.path.exists("/etc/samba/hosts.d/10.0.1.12.conf"))

        obj.RemoveTapIntf(dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "1")
        self.assertTrue(_intfExists("vnb1"))
        self.assertFalse(_intfExists("vnb1.1"))
        self.assertTrue(_intfExists("vnb1.2"))

        obj2.DeleteSambaShare("abc", dbus_interface='org.fpemud.VirtService.VmResSet')
        obj2.DeleteSambaShare("abc2", dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertTrue(len(os.listdir("/etc/samba/hosts.d")) == 0)

        obj2.RemoveTapIntf(dbus_interface='org.fpemud.VirtService.VmResSet')

        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")
        self.assertFalse(_intfExists("vnb1"))
        self.assertFalse(_intfExists("vnb1.1"))
        self.assertFalse(_intfExists("vnb1.2"))

        self.dbusObj.DeleteVmResSet(sid, dbus_interface='org.fpemud.VirtService')
        self.dbusObj.DeleteVmResSet(sid2, dbus_interface='org.fpemud.VirtService')

    def tearDown(self):
        pass


class Test_Vm_Basic(unittest.TestCase):

    def setUp(self):
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.uid = os.getuid()

    def runTest(self):
        sid = self.dbusObj.NewVmResSet(dbus_interface='org.fpemud.VirtService')
        dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService/%d/VmResSets/%d' % (self.uid, sid))

        vmid = self.dbusObj.AttachVm("abc", sid, dbus_interface='org.fpemud.VirtService')
        dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService/%d/VirtMachines/%d' % (self.uid, vmid))

        self.dbusObj.DetachVm(vmid, dbus_interface='org.fpemud.VirtService')
        self.dbusObj.DeleteVmResSet(sid, dbus_interface='org.fpemud.VirtService')

    def tearDown(self):
        pass


def suite():
    suite = unittest.TestSuite()
    suite.addTest(Test_ResSet_Basic())
    suite.addTest(Test_ResSet_TapIntfNat())
    suite.addTest(Test_ResSet_SambaShare())
    suite.addTest(Test_ResSet_MultiInstance())
    suite.addTest(Test_Vm_Basic())
    return suite


def _fileRead(filename):
    with open(filename, "r") as f:
        ret = f.read()
        ret = ret[:-1]        # eliminate the last '\n'
        return ret


def _intfExists(intfname):
    proc = subprocess.Popen("/bin/ifconfig -a", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0]
    assert proc.returncode == 0
    return re.search("^%s:" % (intfname), out, re.M) is not None


def _getSubIntfSet(intfname):
    proc = subprocess.Popen("/bin/ifconfig -a", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0]
    assert proc.returncode == 0

    ret = []
    for m in re.finditer("^(%s\\.\\S):" % (intfname), out, re.M):
        ret.append(m.group(1))

    ret2 = set(ret)
    assert len(ret2) == len(ret)
    return ret2


def _testWebsite(intfname, website):
    return True  # fixme

    proc = subprocess.Popen("/bin/ifconfig %s" % (intfname), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0]
    assert proc.returncode == 0

    localIp = re.search("inet ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", out).group(1)
    ret = subprocess.Popen("/usr/bin/wget --bind-address %s www.baidu.com" % (localIp), shell=True).wait()
    return ret == 0


if __name__ == "__main__":
    unittest.main(defaultTest='suite')
