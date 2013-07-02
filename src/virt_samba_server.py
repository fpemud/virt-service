#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import pwd
import grp
import shutil
import signal
import subprocess
import ConfigParser
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
		assert not self.networkDict[key].bEnable
		del self.networkDict[key]

	def networkEnableServer(self, uid, nid):
		key = (uid, nid)
		assert not self.networkDict[key].bEnable

		if self.serverObj is None:
			self._startServer()
		else:
			self.serverObj.updateShare()

		self.networkDict[key].bEnable = True

	def networkDisableServer(self, uid, nid):
		key = (uid, nid)
		assert self.networkDict[key].bEnable

		self.networkDict[key].bEnable = False

		if self._getEnableCount() == 0:
			self._stopServer()
		else:
			self.serverObj.updateShare()

	def networkGetAccountInfo(self, uid, nid):
		"""return (username, password)"""

		key = (uid, nid)
		assert self.networkDict[key].bEnable

		return (self.networkDict[key].username, self.networkDict[key].username)

	def networkAddShare(self, uid, nid, vmId, shareName, srcPath, readonly):
		assert "_" not in shareName

		# get _NetworkInfo
		key = (uid, nid)
		netInfo = self.networkDict[key]

		# add ShareInfo
		key = (vmId, shareName)
		value = _ShareInfo(srcPath, readonly)
		netInfo.shareDict[key] = value

		# update server
		if self.serverObj is not None:
			self.serverObj.updateShare()

	def networkRemoveShare(self, uid, nid, vmId, shareName):

		# get _NetworkInfo
		key = (uid, nid)
		netInfo = self.networkDict[key]

		# delete ShareInfo
		key = (vmId, shareName)
		del netInfo.shareDict[key]

		# update server
		if self.serverObj is not None:
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

	def _getEnableCount(self):
		count = 0
		for value in self.networkDict.values():
			if value.bEnable:
				count += 1
		return count

class _NetworkInfo:

	def __init__(self, uid, serverPort):
		self.serverPort = serverPort
		self.username = pwd.getpwuid(uid).pw_name
		self.groupname = grp.getgrgid(pwd.getpwuid(uid).pw_gid)
		self.shareDict = dict()
		self.bEnable = False

class _ShareInfo:
	def __init__(self, srcPath, readonly):
		self.srcPath = srcPath
		self.readonly = readonly

class _ServerGlobal:
	"""The configuration of global server can't be modified when it's running"""

	def __init__(self, pObj, sambaPid):
		self.param = pObj.param
		self.pObj = pObj				# parent object
		self.sambaPid = sambaPid

		self.confDir = "/etc/samba"
		self.confFile = os.path.join(self.confDir, "smb.conf")
		self.bakConfFile = os.path.join(self.confDir, "smb.conf.bak.virt-service")

		shutil.move(self.confFile, self.bakConfFile)
		self.updateShare()

	def release(self):
		shutil.move(self.bakConfFile, self.confFile)
		os.kill(self.sambaPid, signal.SIGHUP)

	def checkServer(self):
		"""Check if the configure of global server satisfy our requirement"""

		cfg = ConfigParser.RawConfigParser()
		cfg.read(self.confFile)

		if not cfg.has_option("global", "security") or cfg.get("global", "security") != "user":
			raise Exception("Option \"global/security\" of main samba server must have value \"user\"")

		if cfg.has_option("global", "passdb backend") and cfg.get("global", "passdb backend") != "tdbsam":
			raise Exception("Option \"global/passdb backend\" of main samba server must have value \"tdbsam\"")

		if cfg.has_option("global", "workgroup") and cfg.get("global", "workgroup") != "WORKGROUP":
			raise Exception("Option \"global/workgroup\" of main samba server must have value \"WORKGROUP\"")

	def updateShare(self):
		buf = VirtUtil.readFile(self.bakConfFile)
		buf += "\n\n"
		buf += _MyUtil.genSharePart(self.pObj, self.param)
		VirtUtil.writeFile(self.confFile, buf)

		os.kill(self.sambaPid, signal.SIGHUP)

class _ServerLocal:

	def __init__(self, pObj):
		self.param = pObj.param
		self.pObj = pObj		# parent object

		self.servDir = os.path.join(self.pObj.param.tmpDir, "samba")
		self.confFile = os.path.join(self.servDir, "smbd.conf")
		self.passdbFile = os.path.join(self.servDir, "passdb.tdb")

		try:
			os.mkdir(self.servDir)
			self._genPassdbFile()
			self._genSmbdConf()
			self.serverProc = subprocess.Popen(self._genSmbdCommand(), shell = True)
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
		pass
#		VirtUtil.tdbFileCreate(self.passdbFile)
#		VirtUtil.tdbFileAddUser(self.passdbFile, self.username, self.username)

	def _genSmbdConf(self):

		ifList = []
		for netInfo in self.pObj.networkDict.values():
			ifList.append(netInfo.serverPort)

		buf = ""
		buf += "[global]\n"
		buf += "security                   = user\n"
		buf += "bind interfaces only       = yes\n"
		buf += "interfaces                 = %s\n"%(" ".join(ifList))
		buf += "netbios name               = vmaster\n"
		buf += "private dir                = \"%s\"\n"%(self.servDir)
		buf += "pid directory              = \"%s\"\n"%(self.servDir)
		buf += "lock directory             = \"%s\"\n"%(self.servDir)
		buf += "state directory            = \"%s\"\n"%(self.servDir)
		buf += "log file                   = \"%s/log.smbd\"\n"%(self.servDir)
		buf += "\n\n"
		buf += _MyUtil.genSharePart(self.pObj, self.param)

		VirtUtil.writeFile(self.confFile, buf)

	def _genSmbdCommand(self):

		cmd = "/sbin/smbd"
		cmd += " -F"							# don't run as daemon, so we can control it
		cmd += " -s \"%s\""%(self.confFile)
		return cmd

class _MyUtil:

	@staticmethod
	def genSharePart(pObj, param):
		buf = ""
		for nkey, netInfo in pObj.networkDict.items():
			uid = nkey[0]
			nid = nkey[1]

			if not netInfo.bEnable:
				continue

			for skey, value in netInfo.shareDict.items():
				vmId = skey[0]
				shareName = skey[1]

				assert "_" not in shareName

				buf += "[%d_%d_%d_%s]\n"%(uid, nid, vmId, shareName)
				buf += "path = \"%s\"\n"%(value.srcPath)
				buf += "browseable = no\n"
				buf += "guest ok = yes\n"
				buf += "guest only = yes\n"
				buf += "force user = %s\n"%(netInfo.username)
				buf += "force group = %s\n"%(netInfo.groupname)
				if value.readonly:
					buf += "writable = no\n"
				else:
					buf += "writable = yes\n"
				buf += "hosts allow = %s\n"%(VirtUtil.getVmIpAddress(param.ip1, uid, nid, vmId))


				buf += "\n"
		return buf

