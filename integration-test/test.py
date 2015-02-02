#!/usr/bin/env python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import dbus
import subprocess
import unittest


class Test_Root_NetworkBridge(unittest.TestCase):

    def setUp(self):
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.uid = os.getuid()

    def runTest(self):
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")
        self.assertFalse(_intfExists("vnb%d" % (self.uid)))

        netId = self.dbusObj.NewNetwork("bridge", dbus_interface='org.fpemud.VirtService')
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "1")
        self.assertTrue(_intfExists("vnb%d" % (self.uid)))

        self.dbusObj.DeleteNetwork(netId, dbus_interface='org.fpemud.VirtService')
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")
        self.assertFalse(_intfExists("vnb%d" % (self.uid)))

    def tearDown(self):
        pass


class Test_Root_NetworkNat(unittest.TestCase):

    def setUp(self):
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.uid = os.getuid()

    def runTest(self):
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")
        self.assertFalse(_intfExists("vnn%d" % (self.uid)))

        netId = self.dbusObj.NewNetwork("nat", dbus_interface='org.fpemud.VirtService')
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "1")
        self.assertTrue(_intfExists("vnn%d" % (self.uid)))

        self.dbusObj.DeleteNetwork(netId, dbus_interface='org.fpemud.VirtService')
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")
        self.assertFalse(_intfExists("vnn%d" % (self.uid)))

    def tearDown(self):
        pass


class Test_Root_NetworkRoute(unittest.TestCase):

    def setUp(self):
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.uid = os.getuid()

    def runTest(self):
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")
        self.assertFalse(_intfExists("vnr%d" % (self.uid)))

        netId = self.dbusObj.NewNetwork("route", dbus_interface='org.fpemud.VirtService')
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "1")
        self.assertTrue(_intfExists("vnr%d" % (self.uid)))

        self.dbusObj.DeleteNetwork(netId, dbus_interface='org.fpemud.VirtService')
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")
        self.assertFalse(_intfExists("vnr%d" % (self.uid)))

    def tearDown(self):
        pass


class Test_Root_NetworkIsolate(unittest.TestCase):

    def setUp(self):
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.uid = os.getuid()

    def runTest(self):
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")

        netId = self.dbusObj.NewNetwork("isolate", dbus_interface='org.fpemud.VirtService')
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "1")

        self.dbusObj.DeleteNetwork(netId, dbus_interface='org.fpemud.VirtService')
        self.assertEqual(_fileRead("/proc/sys/net/ipv4/ip_forward"), "0")

    def tearDown(self):
        pass


class Test_Network_BridgeVm(unittest.TestCase):

    def setUp(self):
        self.uid = os.getuid()
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.netId = self.dbusObj.NewNetwork("bridge", dbus_interface='org.fpemud.VirtService')
        self.netObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService/%d/Networks/%d' % (self.uid, self.netId))

    def runTest(self):
        subIntfSet1 = _getSubIntfSet("vnb%d" % (self.uid))

        vmId = self.netObj.AddVm("_test_", dbus_interface='org.fpemud.VirtService.Network')
        subIntfSet2 = _getSubIntfSet("vnb%d" % (self.uid))
        self.assertTrue(len(subIntfSet2) - len(subIntfSet1) == 1)

        self.netObj.DeleteVm(vmId, dbus_interface='org.fpemud.VirtService.Network')
        subIntfSet3 = _getSubIntfSet("vnb%d" % (self.uid))
        self.assertEqual(subIntfSet1, subIntfSet3)

    def tearDown(self):
        self.dbusObj.DeleteNetwork(self.netId, dbus_interface='org.fpemud.VirtService')


class Test_Network_NatVm(unittest.TestCase):

    def setUp(self):
        self.uid = os.getuid()
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.netId = self.dbusObj.NewNetwork("nat", dbus_interface='org.fpemud.VirtService')
        self.netObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService/%d/Networks/%d' % (self.uid, self.netId))

    def runTest(self):
        subIntfSet1 = _getSubIntfSet("vnn%d" % (self.uid))

        vmId = self.netObj.AddVm("_test_", dbus_interface='org.fpemud.VirtService.Network')
        subIntfSet2 = _getSubIntfSet("vnn%d" % (self.uid))
        self.assertTrue(len(subIntfSet2) - len(subIntfSet1) == 1)

        ret = _testWebsite(list(subIntfSet2 - subIntfSet1)[0], "www.baidu.com")
        self.assertTrue(ret)

        self.netObj.DeleteVm(vmId, dbus_interface='org.fpemud.VirtService.Network')
        subIntfSet3 = _getSubIntfSet("vnn%d" % (self.uid))
        self.assertEqual(subIntfSet1, subIntfSet3)

    def tearDown(self):
        self.dbusObj.DeleteNetwork(self.netId, dbus_interface='org.fpemud.VirtService')


class Test_Network_IsolateVm(unittest.TestCase):

    def setUp(self):
        self.uid = os.getuid()
        self.dbusObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService')
        self.netId = self.dbusObj.NewNetwork("isolate", dbus_interface='org.fpemud.VirtService')
        self.netObj = dbus.SystemBus().get_object('org.fpemud.VirtService', '/org/fpemud/VirtService/%d/Networks/%d' % (self.uid, self.netId))

    def runTest(self):
        subIntfSet1 = _getSubIntfSet("vni%d" % (self.uid))

        vmId = self.netObj.AddVm("_test_", dbus_interface='org.fpemud.VirtService.Network')
        subIntfSet2 = _getSubIntfSet("vni%d" % (self.uid))
        self.assertTrue(len(subIntfSet2) - len(subIntfSet1) == 1)

        self.netObj.DeleteVm(vmId, dbus_interface='org.fpemud.VirtService.Network')
        subIntfSet3 = _getSubIntfSet("vni%d" % (self.uid))
        self.assertEqual(subIntfSet1, subIntfSet3)

    def tearDown(self):
        self.dbusObj.DeleteNetwork(self.netId, dbus_interface='org.fpemud.VirtService')


def suite():
    suite = unittest.TestSuite()
    suite.addTest(Test_Root_NetworkBridge())
    suite.addTest(Test_Root_NetworkNat())
#    suite.addTest(Test_Root_NetworkRoute())
    suite.addTest(Test_Root_NetworkIsolate())
    suite.addTest(Test_Network_BridgeVm())
    suite.addTest(Test_Network_NatVm())
#    suite.addTest(Test_Network_RouteVm())
    suite.addTest(Test_Network_IsolateVm())
    return suite


def _fileRead(filename):
    with open(filename, "r") as f:
        ret = f.read()
        ret = ret[:-1]        # eliminate the last '\n'
        return ret


def _intfExists(intfname):
    proc = subprocess.Popen("/usr/bin/ifconfig -a", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0]
    assert proc.returncode == 0
    return re.search("^%s:" % (intfname), out, re.M) is not None


def _getSubIntfSet(intfname):
    proc = subprocess.Popen("/usr/bin/ifconfig -a", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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

    proc = subprocess.Popen("/usr/bin/ifconfig %s" % (intfname), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.communicate()[0]
    assert proc.returncode == 0

    localIp = re.search("inet ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", out).group(1)
    ret = subprocess.Popen("/usr/bin/wget --bind-address %s www.baidu.com" % (localIp), shell=True).wait()
    return ret == 0


if __name__ == "__main__":
    unittest.main(defaultTest='suite')
