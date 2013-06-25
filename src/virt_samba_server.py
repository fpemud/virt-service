#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import pwd
from virt_util import VirtUtil

class VirtSambaServer:
	"""VirtSambaServer """

	class ShareInfo:
		srcPath = None
		readonly = None

    def __init__(self, param, uid, nid, serverPort):
		self.param = param
		self.uid = uid
		self.nid = nid
		self.serverPort = serverPort
		self.username = pwd.getpwuid(self.uid).pw_name
		self.shareDict = dict()
		self.vmDict = dict()				# vmId => passwords

		self.servDir = os.path.join(self.param.tmpDir, str(self.uid), str(self.nid), "samba")
		self.confFile = os.path.join(self.servDir, "smbd.conf")
		self.passdbFile = os.path.join(self.servDir, "passdb.tdb")
		self.serverProc = None

	def enableServer(self):
		assert self.serverProc is None

		os.mkdir(self.servDir)
		self._genPassdbFile(self.passdbFile)
		self._genSmbdConf(self.confFile)
		self.serverProc = subprocess.Popen(self._genSmbdCommand(), shell = True)

	def disableServer(self):
		if self.serverProc is not None:
			self.serverProc.terminate()
			self.serverProc.wait()
			self.serverProc = None
			shutil.rmtree(self.servDir)

	def isServerEnabled(self):
		return self.serverProc is not None

	def addShare(self, vmId, shareName, srcPath, readonly):
		assert "_" not in shareName

		# add ShareInfo
		key = (vmId, shareName)
		value = self.ShareInfo()
		value.srcPath = srcPath
		value.readonly = readonly
		self.shareDict[key] = value

		# add vmInfo
		if vmId not in self.vmDict:
			self.vmdict[vmId] = vmId

		# update server
		if self.serverProc is not None:
			self._genSmbdConf(self.confFile)
			self.serverProc.send_signal(SIGHUP)

	def removeShare(self, vmId, shareName):
		# delete ShareInfo
		key = (vmId, shareName)
		del self.shareDict[key]

		# update server
		if self.serverProc is not None:
			self._genSmbdConf(self.confFile)
			self.serverProc.send_signal(SIGHUP)

	def getAccountInfo(self, vmId):
		return (self.username, self.username)

	def _genPassdbFile(self, filename):
		VirtUtil.tdbFileCreate(filename)
		VirtUtil.tdbFileAddUser(filename, self.username, self.username)

	def _genSmbdConf(self, filename):

		buf = ""
		buf += "[global]\n"
		buf += "security                   = user\n"
		buf += "bind interfaces only       = yes\n"
		buf += "interfaces                 = %s\n"%(self.serverPort)
		buf += "netbios name               = vmaster\n"
		buf += "private dir                = \"%s\"\n"%(self.servDir)
		buf += "pid directory              = \"%s\"\n"%(self.servDir)
		buf += "lock directory             = \"%s\"\n"%(self.servDir)
		buf += "state directory            = \"%s\"\n"%(self.servDir)
		buf += "log file                   = \"%s/log.smbd\"\n"%(self.servDir)
		buf += "\n"

		for key, value in self.shareDict.items():
			buf += "[%d_%s]\n"%(key[0], key[1])
			buf += "path = \"%s\"\n"%(value.srcPath)
			buf += "browseable = no\n"
			if value.readonly:
				buf += "writable = no\n"
			else:
				buf += "writable = yes\n"
			buf += "\n"

		f = open(filename, 'w')
		f.write(buf)
		f.close()

	def _genSmbdCommand(self):

		cmd = "/sbin/smbd"
		cmd += " -F"							# don't run as daemon, so we can control it
		cmd += " -s \"%s\""%(self.confFile)
		return cmd



