# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: t -*-
# vi: set ft=python sts=4 ts=4 sw=4 noet :

# This file is part of Fail2Ban.
#
# Fail2Ban is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Fail2Ban is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Fail2Ban; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# Author: Daniel Black
# 

__author__ = "Daniel Black"
__copyright__ = "Copyright (c) 2013 Daniel Black"
__license__ = "GPL"

import time
import os
import tempfile

from ..server.actions import Actions
from ..server.ticket import FailTicket
from ..server.utils import Utils
from .dummyjail import DummyJail
from .utils import LogCaptureTestCase, with_alt_time, MyTime

TEST_FILES_DIR = os.path.join(os.path.dirname(__file__), "files")


class ExecuteActions(LogCaptureTestCase):

	def setUp(self):
		"""Call before every test case."""
		super(ExecuteActions, self).setUp()
		self.__jail = DummyJail()
		self.__actions = Actions(self.__jail)

	def tearDown(self):
		super(ExecuteActions, self).tearDown()

	def defaultAction(self):
		self.__actions.add('ip')
		act = self.__actions['ip']
		act.actionstart = 'echo ip start'
		act.actionban = 'echo ip ban <ip>'
		act.actionunban = 'echo ip unban <ip>'
		act.actioncheck = 'echo ip check'
		act.actionflush = 'echo ip flush <family>'
		act.actionstop = 'echo ip stop'
		return act

	def testActionsAddDuplicateName(self):
		self.__actions.add('test')
		self.assertRaises(ValueError, self.__actions.add, 'test')

	def testActionsManipulation(self):
		self.__actions.add('test')
		self.assertTrue(self.__actions['test'])
		self.assertIn('test', self.__actions)
		self.assertNotIn('nonexistant action', self.__actions)
		self.__actions.add('test1')
		del self.__actions['test']
		del self.__actions['test1']
		self.assertNotIn('test', self.__actions)
		self.assertEqual(len(self.__actions), 0)

		self.__actions.setBanTime(127)
		self.assertEqual(self.__actions.getBanTime(),127)
		self.assertRaises(ValueError, self.__actions.removeBannedIP, '127.0.0.1')

	def testAddBannedIP(self):
		self.assertEqual(self.__actions.addBannedIP('192.0.2.1'), 1)
		self.assertLogged('Ban 192.0.2.1')
		self.pruneLog()
		self.assertEqual(self.__actions.addBannedIP(['192.0.2.1', '192.0.2.2', '192.0.2.3']), 2)
		self.assertLogged('192.0.2.1 already banned')
		self.assertNotLogged('Ban 192.0.2.1')
		self.assertLogged('Ban 192.0.2.2')
		self.assertLogged('Ban 192.0.2.3')

	def testActionsOutput(self):
		self.defaultAction()
		self.__actions.start()
		self.assertLogged("stdout: %r" % 'ip start', wait=True)
		self.__actions.stop()
		self.__actions.join()
		self.assertLogged("stdout: %r" % 'ip flush', "stdout: %r" % 'ip stop')
		self.assertEqual(self.__actions.status(),[("Currently banned", 0 ),
               ("Total banned", 0 ), ("Banned IP list", [] )])

	def testAddActionPython(self):
		self.__actions.add(
			"Action", os.path.join(TEST_FILES_DIR, "action.d/action.py"),
			{'opt1': 'value'})

		self.assertLogged("TestAction initialised")

		self.__actions.start()
		self.assertTrue( Utils.wait_for(lambda: self._is_logged("TestAction action start"), 3) )

		self.__actions.stop()
		self.__actions.join()
		self.assertLogged("TestAction action stop")

		self.assertRaises(IOError,
			self.__actions.add, "Action3", "/does/not/exist.py", {})

		# With optional argument
		self.__actions.add(
			"Action4", os.path.join(TEST_FILES_DIR, "action.d/action.py"),
			{'opt1': 'value', 'opt2': 'value2'})
		# With too many arguments
		self.assertRaises(
			TypeError, self.__actions.add, "Action5",
			os.path.join(TEST_FILES_DIR, "action.d/action.py"),
			{'opt1': 'value', 'opt2': 'value2', 'opt3': 'value3'})
		# Missing required argument
		self.assertRaises(
			TypeError, self.__actions.add, "Action5",
			os.path.join(TEST_FILES_DIR, "action.d/action.py"), {})

	def testAddPythonActionNOK(self):
		self.assertRaises(RuntimeError, self.__actions.add,
			"Action", os.path.join(TEST_FILES_DIR,
				"action.d/action_noAction.py"),
			{})
		self.assertRaises(RuntimeError, self.__actions.add,
			"Action", os.path.join(TEST_FILES_DIR,
				"action.d/action_nomethod.py"),
			{})
		self.__actions.add(
			"Action", os.path.join(TEST_FILES_DIR,
				"action.d/action_errors.py"),
			{})
		self.__actions.start()
		self.assertTrue( Utils.wait_for(lambda: self._is_logged("Failed to start"), 3) )
		self.__actions.stop()
		self.__actions.join()
		self.assertLogged("Failed to stop")

	def testBanActionsAInfo(self):
		# Action which deletes IP address from aInfo
		self.__actions.add(
			"action1",
			os.path.join(TEST_FILES_DIR, "action.d/action_modifyainfo.py"),
			{})
		self.__actions.add(
			"action2",
			os.path.join(TEST_FILES_DIR, "action.d/action_modifyainfo.py"),
			{})
		self.__jail.putFailTicket(FailTicket("1.2.3.4", 0))
		self.__actions._Actions__checkBan()
		# Will fail if modification of aInfo from first action propagates
		# to second action, as both delete same key
		self.assertNotLogged("Failed to execute ban")
		self.assertLogged("action1 ban deleted aInfo IP")
		self.assertLogged("action2 ban deleted aInfo IP")

		self.__actions._Actions__flushBan()
		# Will fail if modification of aInfo from first action propagates
		# to second action, as both delete same key
		self.assertNotLogged("Failed to execute unban")
		self.assertLogged("action1 unban deleted aInfo IP")
		self.assertLogged("action2 unban deleted aInfo IP")

	@with_alt_time
	def testUnbanOnBusyBanBombing(self):
		# check unban happens in-between of "ban bombing" despite lower precedence,
		# if it is not work, we'll not see "Unbanned 30" (rather "Unbanned 50")
		# because then all the unbans occur earliest at flushing (after stop)

		# each 3rd ban we should see an unban check (and up to 5 tickets gets unbanned):
		self.__actions.banPrecedence = 3
		self.__actions.unbanMaxCount = 5
		self.__actions.setBanTime(100)

		self.__actions.start()

		MyTime.setTime(0); # avoid "expired bantime" (in 0.11)
		i = 0
		while i < 20:
			ip = "192.0.2.%d" % i
			self.__jail.putFailTicket(FailTicket(ip, 0))
			i += 1

		# wait for last ban (all 20 tickets gets banned):
		self.assertLogged(' / 20,', wait=True)

		MyTime.setTime(200); # unban time for 20 tickets reached

		while i < 50:
			ip = "192.0.2.%d" % i
			self.__jail.putFailTicket(FailTicket(ip, 200))
			i += 1

		# wait for last ban (all 50 tickets gets banned):
		self.assertLogged(' / 50,', wait=True)
		self.__actions.stop()
		self.__actions.join()

		self.assertLogged('Unbanned 30, 0 ticket(s)')
		self.assertNotLogged('Unbanned 50, 0 ticket(s)')

	@with_alt_time
	def testActionsConsistencyCheck(self):
		# flush for inet6 is intentionally "broken" here - test no unhandled except and invariant check:
		act = self.defaultAction()
		act['actionflush?family=inet6'] = 'echo ip flush <family>; exit 1'
		act.actionstart_on_demand = True
		self.__actions.start()
		self.assertNotLogged("stdout: %r" % 'ip start')

		self.assertEqual(self.__actions.addBannedIP('192.0.2.1'), 1)
		self.assertEqual(self.__actions.addBannedIP('2001:db8::1'), 1)
		self.assertLogged('Ban 192.0.2.1', 'Ban 2001:db8::1',
			"stdout: %r" % 'ip start',
			"stdout: %r" % 'ip ban 192.0.2.1',
			"stdout: %r" % 'ip ban 2001:db8::1',
			all=True, wait=True)

		# check should fail (so cause stop/start):
		self.pruneLog('[test-phase 1] simulate inconsistent env')
		act['actioncheck?family=inet6'] = 'echo ip check <family>; exit 1'
		self.__actions._Actions__flushBan()
		self.assertLogged('Failed to flush bans',
			'No flush occured, do consistency check',
			'Invariant check failed. Trying to restore a sane environment',
			"stdout: %r" % 'ip stop',
			"stdout: %r" % 'ip start',
			all=True, wait=True)

		# check succeeds:
		self.pruneLog('[test-phase 2] consistent env')
		act['actioncheck?family=inet6'] = act.actioncheck
		self.__actions._Actions__flushBan()
		self.assertLogged('Failed to flush bans',
			'No flush occured, do consistency check',
			"stdout: %r" % 'ip ban 192.0.2.1',
			all=True, wait=True)

		act['actionflush?family=inet6'] = act.actionflush

		self.__actions.stop()
		self.__actions.join()

