#!/usr/bin/python2
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import subprocess
import time
import grp
import pwd
import socket

class VirtUtil:

    @staticmethod
	def getSysctl(name):
		msg = VirtUtil.shell("/sbin/sysctl -n %s"%(name), "stdout")
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
	def getFreeSocketPort(portType, portStart, portEnd):
		if portType == "tcp":
			sType = socket.SOCK_STREAM
		elif portType == "udp":
			assert False
		else:
			assert False

		for port in range(portStart, portEnd+1):
			s = socket.socket(socket.AF_INET, sType)
			try:
				s.bind((('', port)))
				return port
			except socket.error:
				continue
			finally:
				s.close()
		raise Exception("No valid %s port in [%d,%d]."%(portType, portStart, portEnd))

    @staticmethod
	def shell(cmd, flags=""):
		"""Execute shell command"""

		assert cmd.startswith("/")

		# Execute shell command, throws exception when failed
		if flags == "":
			retcode = subprocess.Popen(cmd, shell = True).wait()
			if retcode != 0:
				raise Exception("Executing shell command \"%s\" failed, return code %d"%(cmd, retcode))
			return

		# Execute shell command, throws exception when failed, returns stdout+stderr
		if flags == "stdout":
			proc = subprocess.Popen(cmd,
				                    shell = True,
				                    stdout = subprocess.PIPE,
				                    stderr = subprocess.STDOUT)
			out = proc.communicate()[0]
			if proc.returncode != 0:
				raise Exception("Executing shell command \"%s\" failed, return code %d"%(cmd, proc.returncode))
			return out

		# Execute shell command, returns (returncode,stdout+stderr)
		if flags == "retcode+stdout":
			proc = subprocess.Popen(cmd,
				                    shell = True,
				                    stdout = subprocess.PIPE,
				                    stderr = subprocess.STDOUT)
			out = proc.communicate()[0]
			return (proc.returncode, out)

		assert False

    @staticmethod
	def ipMaskToLen(mask):
		"""255.255.255.0 -> 24"""

		netmask = 0
		netmasks = mask.split('.')
		for i in range(0,len(netmasks)):
			netmask *= 256
			netmask += int(netmasks[i])
		return 32 - (netmask ^ 0xFFFFFFFF).bit_length()

    @staticmethod
	def loadKernelModule(modname):
		"""Loads a kernel module."""

		VirtUtil.shell("/sbin/modprobe %s"%(modname))

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
		groups.append(grp.getgrgid(gid).gr_name)			# --fixme, should be prepend
		return groups

    @staticmethod
	def getMaxTapId(self, brname):
		ret = VirUtil.shell('/bin/ifconfig -a', 'stdout')
		matchList = re.findall("^%s.([0-9]+):"%(brname), ret, re.MULTILINE)
		maxId = 0
		for m in matchList:
			if int(m) > maxId:
				maxId = int(m)
		return maxId
