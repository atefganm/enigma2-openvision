from copy import copy as shallowcopy
from enigma import getPrevAsciiCode
from os import fsync, rename
from os.path import realpath
from six import PY2
from time import localtime, strftime

from Components.SystemInfo import BoxInfo
from Tools.Directories import SCOPE_CONFIG, fileExists, resolveFilename
from Tools.LoadPixmap import LoadPixmap
from Tools.NumericalTextInput import NumericalTextInput
from Components.Harddisk import harddiskmanager  # This import is order critical!

pyunichr = unichr if PY2 else chr

ACTIONKEY_LEFT = 0
ACTIONKEY_RIGHT = 1
ACTIONKEY_SELECT = 2
ACTIONKEY_DELETE = 3
ACTIONKEY_BACKSPACE = 4
ACTIONKEY_FIRST = 5
ACTIONKEY_LAST = 6
ACTIONKEY_TOGGLE = 7
ACTIONKEY_ASCII = 8
ACTIONKEY_TIMEOUT = 9
ACTIONKEY_NUMBERS = range(12, 12 + 10)
ACTIONKEY_0 = 12
ACTIONKEY_1 = 13
ACTIONKEY_2 = 14
ACTIONKEY_3 = 15
ACTIONKEY_4 = 16
ACTIONKEY_5 = 17
ACTIONKEY_6 = 18
ACTIONKEY_7 = 19
ACTIONKEY_8 = 20
ACTIONKEY_9 = 21
ACTIONKEY_PAGEUP = 22
ACTIONKEY_PAGEDOWN = 23
ACTIONKEY_PREV = 24
ACTIONKEY_NEXT = 25
ACTIONKEY_ERASE = 26

# Deprecated / Legacy action key names...
#
# (These should be removed when all Enigma2 uses the new and less confusing names.)
#
KEY_LEFT = ACTIONKEY_LEFT
KEY_RIGHT = ACTIONKEY_RIGHT
KEY_OK = ACTIONKEY_SELECT
KEY_DELETE = ACTIONKEY_DELETE
KEY_BACKSPACE = ACTIONKEY_BACKSPACE
KEY_HOME = ACTIONKEY_FIRST
KEY_END = ACTIONKEY_LAST
KEY_TOGGLEOW = ACTIONKEY_TOGGLE
KEY_ASCII = ACTIONKEY_ASCII
KEY_TIMEOUT = ACTIONKEY_TIMEOUT
KEY_NUMBERS = ACTIONKEY_NUMBERS
KEY_0 = ACTIONKEY_0
KEY_9 = ACTIONKEY_9


def getKeyNumber(key):
	assert key in ACTIONKEY_NUMBERS
	return key - ACTIONKEY_0


def getConfigListEntry(*args):
	assert len(args) > 1, "[Config] Error: 'getConfigListEntry' needs a minimum of two arguments (description, configElement)!"
	return args


def updateConfigElement(element, newelement):
	newelement.value = element.value
	return newelement


def NoSave(element):
	element.disableSave()
	return element


# ConfigElement, the base class of all ConfigElements.
#
# It stores:
#   value        The current value, usefully encoded.  Usually a property which
#                retrieves _value, and maybe does some reformatting.
#   _value       The value as it's going to be saved in the configfile, though
#                still in non-string form.  This is the object which is actually
#                worked on.
#   default      The initial value. If _value is equal to default, it will not
#                be stored in the config file unless saved_force is True.
#   saved_value  Is a text representation of _value, stored in the config file.
#
# It has (at least) the following methods:
#   load()       Loads _value from saved_value, or loads the default if
#                saved_value is "None" (default) or invalid.
#   save()       Stores _value into saved_value, (or stores "None" if it should
#                not be stored).
#
class ConfigElement(object):
	def __init__(self):
		self.save_disabled = False  # Used externally!
		self.save_forced = False  # Used externally!
		self.lastValue = None
		self.saved_value = None  # Used externally!
		self.extra_args = []  # Used externally!
		self.__notifiers = None
		self.__notifiers_final = None
		self.enabled = True
		self.callNotifiersOnSaveAndCancel = False

	def __call__(self, selected):
		return self.getMulti(selected)

	def load(self):  # You can overide this for fancy default handling.
		self.value = self.default if self.saved_value is None else self.fromstring(self.saved_value)

	def save(self):  # You need to override this if str(self.value) doesn't work.
		if self.save_disabled or (self.value == self.default and not self.save_forced):
			self.saved_value = None
		else:
			self.saved_value = self.tostring(self.value)
		if self.callNotifiersOnSaveAndCancel:
			self.changedFinal()  # Call none immediate_feedback notifiers, immediate_feedback Notifiers are called as they are chanaged, so do not need to be called here.

	def disableSave(self):
		self.save_disabled = True

	def cancel(self):
		self.load()
		if self.callNotifiersOnSaveAndCancel:
			self.changedFinal()  # Call none immediate_feedback notifiers, immediate_feedback Notifiers are called as they are chanaged, so do not need to be called here.

	def getValue(self):
		return self._value

	def setValue(self, value):  # You need to override this to do input validation.
		self._value = value
		self.changed()

	value = property(getValue, setValue)

	def fromstring(self, value):  # You need to override this if self.value is not a string.
		return value

	def tostring(self, value):
		return str(value)

	def toDisplayString(self, value):
		return str(value)

	def isChanged(self):
		# NOTE - self.saved_value should already be stringified!
		#        self.default may be a string or None
		saved = self.saved_value or self.tostring(self.default)
		valueString = self.tostring(self.value)
		return valueString != saved

	def changed(self):
		if self.__notifiers:
			for x in self.notifiers:
				extra_args = self.__getExtraArgs(x)
				if extra_args is not None:
					x(self, extra_args)
				else:
					x(self)

	def changedFinal(self):
		if self.__notifiers_final:
			for x in self.notifiers_final:
				extra_args = self.__getExtraArgs(x)
				if extra_args is not None:
					x(self, extra_args)
				else:
					x(self)

	def onSelect(self, session):
		pass  # Note that self.lastValue is set in each module's __init__ method.

	def onDeselect(self, session):
		if self.lastValue != self.value:
			self.lastValue = self.value
			self.changedFinal()

	def getNotifiers(self):
		if self.__notifiers is None:
			self.__notifiers = []
		return self.__notifiers

	def setNotifiers(self, val):
		self.__notifiers = val

	notifiers = property(getNotifiers, setNotifiers)

	def getNotifiersFinal(self):
		if self.__notifiers_final is None:
			self.__notifiers_final = []
		return self.__notifiers_final

	def setNotifiersFinal(self, val):
		self.__notifiers_final = val

	notifiers_final = property(getNotifiersFinal, setNotifiersFinal)

	def addNotifier(self, notifier, initial_call=True, immediate_feedback=True, extra_args=None):
		assert callable(notifier), "[Config] Error: Notifiers must be callable!"
		if extra_args is not None:
			self.__addExtraArgs(notifier, extra_args)
		if immediate_feedback:
			self.notifiers.append(notifier)
		else:
			self.notifiers_final.append(notifier)
		# CHECKME:
		# do we want to call the notifier
		#  - at all when adding it? (yes, though optional)
		#  - when the default is active? (yes)
		#  - when no value *yet* has been set,
		#    because no config has ever been read (currently yes)
		#    (though that's not so easy to detect.
		#     the entry could just be new.)
		if initial_call:
			if extra_args:
				notifier(self, extra_args)
			else:
				notifier(self)

	def removeNotifier(self, notifier):
		notifier in self.notifiers and self.notifiers.remove(notifier)
		notifier in self.notifiers_final and self.notifiers_final.remove(notifier)
		self.__removeExtraArgs(notifier)
		try:
			del self.__notifiers[str(notifier)]
		except Exception:
			pass
		try:
			del self.__notifiers_final[str(notifier)]
		except Exception:
			pass

	def clearNotifiers(self):
		self.__notifiers = {}
		self.__notifiers_final = {}

	def showHelp(self, session):
		pass

	def hideHelp(self, session):
		pass

	def __addExtraArgs(self, notifier, extra_args):
		self.extra_args.append((notifier, extra_args))

	def __removeExtraArgs(self, notifier):
		for i in range(len(self.extra_args)):
			if self.extra_args[i][0] == notifier:
				del self.extra_args[i]

	def __getExtraArgs(self, notifier):
		for extra_arg in self.extra_args:
			if extra_arg[0] == notifier:
				return extra_arg[1]


class choicesList(object):
	LIST_TYPE_LIST = 1
	LIST_TYPE_DICT = 2

	def __init__(self, choices, type=None):
		if type is None:
			if isinstance(choices, list):
				self.type = choicesList.LIST_TYPE_LIST
			elif isinstance(choices, dict):
				self.type = choicesList.LIST_TYPE_DICT
			else:
				assert False, "[Config] Error: Choices must be dict or list!"
		else:
			self.type = type
		self.choices = choices

	def __list__(self):
		if self.type == choicesList.LIST_TYPE_LIST:
			ret = [not isinstance(x, tuple) and x or x[0] for x in self.choices]
		else:
			if PY2:
				ret = self.choices.keys()
			else:
				list(self.choices.keys())
		return ret or [""]

	def __iter__(self):
		if self.type == choicesList.LIST_TYPE_LIST:
			ret = [not isinstance(x, tuple) and x or x[0] for x in self.choices]
		else:
			ret = self.choices
		return iter(ret or [""])

	def __len__(self):
		return len(self.choices) or 1

	def __getitem__(self, index):
		if index == 0 and not self.choices:
			return ""
		if self.type == choicesList.LIST_TYPE_LIST:
			ret = self.choices[index]
			if isinstance(ret, tuple):
				ret = ret[0]
			return ret
		return list(self.choices.keys())[index]

	def index(self, value):
		if PY2:
			try:
				return list(map(str, self.__list__())).index(str(value))
			except (ValueError, IndexError):  # Occurs, for example, when default is not in list.
				return 0
		else:
			return self.__list__().index(value)

	def __setitem__(self, index, value):
		if index == 0 and not self.choices:
			return
		if self.type == choicesList.LIST_TYPE_LIST:
			orig = self.choices[index]
			if isinstance(orig, tuple):
				self.choices[index] = (value, orig[1])
			else:
				self.choices[index] = value
		else:
			key = list(self.choices.keys())[index]
			orig = self.choices[key]
			del self.choices[key]
			self.choices[value] = orig

	def default(self):
		choices = self.choices
		if not choices:
			return ""
		if self.type is choicesList.LIST_TYPE_LIST:
			default = choices[0]
			if isinstance(default, tuple):
				default = default[0]
		else:
			default = list(choices.keys())[0]
		return default


class descriptionList(choicesList):
	def __list__(self):
		if self.type == choicesList.LIST_TYPE_LIST:
			ret = [not isinstance(x, tuple) and x or x[1] for x in self.choices]
		else:
			ret = list(self.choices.values())
		return ret or [""]

	def __iter__(self):
		return iter(self.__list__())

	def __getitem__(self, index):
		if self.type == choicesList.LIST_TYPE_LIST:
			for x in self.choices:
				if isinstance(x, tuple) and str(x[0]) == str(index):
					return str(x[1])
			return _(str(index))  # If there is no display / translation string then translate the value!
		else:
			return str(self.choices.get(index, ""))

	def __setitem__(self, index, value):
		if not self.choices:
			return
		if self.type == choicesList.LIST_TYPE_LIST:
			i = self.index(index)
			orig = self.choices[i]
			if isinstance(orig, tuple):
				self.choices[i] = (orig[0], value)
			else:
				self.choices[i] = value
		else:
			self.choices[index] = value


# This is the control, and base class, for triggering action settings.
#
# class ConfigAction(ConfigElement):
# 	def __init__(self, action, *args):
# 		ConfigElement.__init__(self)
# 		self.value = "(OK)"
# 		self.action = action
# 		self.actionargs = args
#
# 	def handleKey(self, key):
# 		if (key == ACTIONKEY_SELECT):
# 			self.action(*self.actionargs)
#
# 	def getMulti(self, selected):
# 		return ("text", _("<Press OK to perform action>") if selected else "")


# This is the control, and base class, for binary decision settings.
#
# Several customized versions exist for different descriptions.
#
class ConfigBoolean(ConfigElement):
	def __init__(self, default=False, descriptions={False: _("False"), True: _("True")}, graphic=True):
		ConfigElement.__init__(self)
		self.value = self.lastValue = self.default = default
		self.descriptions = descriptions
		self.graphic = graphic
		self.trueValues = ("1", "enable", "on", "true", "yes")

	def handleKey(self, key):
		if key in (ACTIONKEY_TOGGLE, ACTIONKEY_SELECT, ACTIONKEY_LEFT, ACTIONKEY_RIGHT):
			self.value = not self.value
		elif key == ACTIONKEY_FIRST:
			self.value = False
		elif key == ACTIONKEY_LAST:
			self.value = True

	def fromstring(self, value):
		return str(value).lower() in self.trueValues

	def tostring(self, value):
		return "True" if value and str(value).lower() in self.trueValues else "False"
		# Use the following if settings should be saved using the same values as displayed to the user.
		# self.descriptions[True] if value or str(value).lower() in self.trueValues else self.descriptions[False]

	def toDisplayString(self, value):
		return self.descriptions[True] if value or str(value).lower() in self.trueValues else self.descriptions[False]

	def getText(self):
		return self.descriptions[self.value]

	def getMulti(self, selected):
		from skin import switchPixmap
		from Components.config import config
		if self.graphic and config.usage.boolean_graphic.value and "menu_on" in switchPixmap and "menu_off" in switchPixmap:
			return ("pixmap", switchPixmap["menu_on" if self.value else "menu_off"])
		return ("text", self.descriptions[self.value])

	# For HTML Interface - Is this still used?
	def getHTML(self, id):  # DEBUG: Is this still used?
		return "<input type=\"checkbox\" name=\"%s\" value=\"1\"%s />" % (id, " checked=\"checked\"" if self.value else "")

	# This is FLAWED. and must be fixed!
	def unsafeAssign(self, value):  # DEBUG: Is this still used?
		self.value = value.lower() in self.trueValues


class ConfigEnableDisable(ConfigBoolean):
	def __init__(self, default=False, graphic=True):
		ConfigBoolean.__init__(self, default=default, descriptions={False: _("Disable"), True: _("Enable")}, graphic=graphic)


class ConfigOnOff(ConfigBoolean):
	def __init__(self, default=False, graphic=True):
		ConfigBoolean.__init__(self, default=default, descriptions={False: _("Off"), True: _("On")}, graphic=graphic)


class ConfigYesNo(ConfigBoolean):
	def __init__(self, default=False, graphic=True):
		ConfigBoolean.__init__(self, default=default, descriptions={False: _("No"), True: _("Yes")}, graphic=graphic)


# This is the control, and base class, for date and time settings.
#
class ConfigDateTime(ConfigElement):
	def __init__(self, default, formatstring, increment=86400):
		ConfigElement.__init__(self)
		self.increment = increment
		self.formatstring = formatstring
		self.value = self.lastValue = self.default = int(default)

	def handleKey(self, key):
		if key == ACTIONKEY_LEFT:
			self.value -= self.increment
		elif key == ACTIONKEY_RIGHT:
			self.value += self.increment
		elif key == ACTIONKEY_FIRST or key == ACTIONKEY_LAST:
			self.value = self.default

	def getText(self):
		return strftime(self.formatstring, localtime(self.value))

	def getMulti(self, selected):
		return ("text", strftime(self.formatstring, localtime(self.value)))

	def fromstring(self, val):
		return int(val)


# This is the control, and base class, for dictionary settings.
#
class ConfigDictionarySet(ConfigElement):
	def __init__(self, default={}):
		ConfigElement.__init__(self)
		self.default = default
		self.dirs = {}
		self.value = self.default

	def getKeys(self):
		return self.dir_pathes

	def setValue(self, value):
		if isinstance(value, dict):
			self.dirs = value
			self.changed()

	def getValue(self):
		return self.dirs

	value = property(getValue, setValue)

	def tostring(self, value):
		return str(value)

	def fromstring(self, val):
		return eval(val)

	def load(self):
		sv = self.saved_value
		if sv is None:
			tmp = self.default
		else:
			tmp = self.fromstring(sv)
		self.dirs = tmp

	def changeConfigValue(self, value, config_key, config_value):
		if isinstance(value, str) and isinstance(config_key, str):
			if value in self.dirs:
				self.dirs[value][config_key] = config_value
			else:
				self.dirs[value] = {config_key: config_value}
			self.changed()

	def getConfigValue(self, value, config_key):
		if isinstance(value, str) and isinstance(config_key, str):
			if value in self.dirs and config_key in self.dirs[value]:
				return self.dirs[value][config_key]
		return None

	def removeConfigValue(self, value, config_key):
		if isinstance(value, str) and isinstance(config_key, str):
			if value in self.dirs and config_key in self.dirs[value]:
				try:
					del self.dirs[value][config_key]
				except KeyError:
					pass
				self.changed()

	def save(self):
		del_keys = []
		for key in self.dirs:
			if not len(self.dirs[key]):
				del_keys.append(key)
		for del_key in del_keys:
			try:
				del self.dirs[del_key]
			except KeyError:
				pass
			self.changed()
		self.saved_value = self.tostring(self.dirs)


# This is the control, and base class, for location settings.
#
class ConfigLocations(ConfigElement):
	def __init__(self, default=None, visible_width=False):
		ConfigElement.__init__(self)
		if not default:
			default = []
		self.visible_width = visible_width
		self.pos = -1
		self.default = default
		self.locations = []
		self.mountpoints = []
		self.value = shallowcopy(default)

	def setValue(self, value):
		locations = self.locations
		loc = [x[0] for x in locations if x[3]]
		add = [x for x in value if x not in loc]
		diff = add + [x for x in loc if x not in value]
		locations = [x for x in locations if x[0] not in diff] + [[x, self.getMountpoint(x), True, True] for x in add]
		locations.sort(key=lambda x: x[0])
		self.locations = locations
		self.changed()

	def getValue(self):
		self.checkChangedMountpoints()
		locations = self.locations
		for x in locations:
			x[3] = x[2]
		return [x[0] for x in locations if x[3]]

	value = property(getValue, setValue)

	def tostring(self, value):
		return str(value)

	def fromstring(self, val):
		return eval(val)

	def load(self):
		sv = self.saved_value
		if sv is None:
			tmp = self.default
		else:
			tmp = self.fromstring(sv)
		locations = [[x, None, False, False] for x in tmp]
		self.refreshMountpoints()
		for x in locations:
			if fileExists(x[0]):
				x[1] = self.getMountpoint(x[0])
				x[2] = True
		self.locations = locations

	def save(self):
		locations = self.locations
		if self.save_disabled or not locations:
			self.saved_value = None
		else:
			self.saved_value = self.tostring([x[0] for x in locations])

	def isChanged(self):
		sv = self.saved_value
		locations = self.locations
		if sv is None and not locations:
			return False
		return self.tostring([x[0] for x in locations]) != sv

	def addedMount(self, mp):
		for x in self.locations:
			if x[1] == mp:
				x[2] = True
			elif x[1] is None and fileExists(x[0]):
				x[1] = self.getMountpoint(x[0])
				x[2] = True

	def removedMount(self, mp):
		for x in self.locations:
			if x[1] == mp:
				x[2] = False

	def refreshMountpoints(self):
		self.mountpoints = [p.mountpoint for p in harddiskmanager.getMountedPartitions() if p.mountpoint != "/"]
		self.mountpoints.sort(key=lambda x: -len(x))

	def checkChangedMountpoints(self):
		oldmounts = self.mountpoints
		self.refreshMountpoints()
		newmounts = self.mountpoints
		if oldmounts == newmounts:
			return
		for x in oldmounts:
			if x not in newmounts:
				self.removedMount(x)
		for x in newmounts:
			if x not in oldmounts:
				self.addedMount(x)

	def getMountpoint(self, file):
		file = realpath(file) + "/"
		for m in self.mountpoints:
			if file.startswith(m):
				return m
		return None

	def handleKey(self, key):
		if key == ACTIONKEY_LEFT:
			self.pos -= 1
			if self.pos < -1:
				self.pos = len(self.value) - 1
		elif key == ACTIONKEY_RIGHT:
			self.pos += 1
			if self.pos >= len(self.value):
				self.pos = -1
		elif key in (ACTIONKEY_FIRST, ACTIONKEY_LAST):
			self.pos = -1

	def getText(self):
		return " ".join(self.value)

	def getMulti(self, selected):
		if not selected:
			valstr = " ".join(self.value)
			if self.visible_width and len(valstr) > self.visible_width:
				return ("text", valstr[0:self.visible_width])
			else:
				return ("text", valstr)
		else:
			i = 0
			valstr = ""
			ind1 = 0
			ind2 = 0
			for val in self.value:
				if i == self.pos:
					ind1 = len(valstr)
				valstr += str(val) + " "
				if i == self.pos:
					ind2 = len(valstr)
				i += 1
			if self.visible_width and len(valstr) > self.visible_width:
				if ind1 + 1 < self.visible_width / 2:
					off = 0
				else:
					off = min(ind1 + 1 - self.visible_width / 2, len(valstr) - self.visible_width)
				return ("mtext", valstr[off:off + self.visible_width], range(ind1 - off, ind2 - off))
			else:
				return ("mtext", valstr, range(ind1, ind2))

	def onDeselect(self, session):
		self.pos = -1


# This is the control, and base class, for selection list settings.
#
# ConfigSelection is a "one of.."-type.  It has the "choices", usually
# a list, which contains (id, desc)-tuples (or just only the ids, in
# case str(id) will be used as description).
#
# The ids in "choices" may be of any type, provided that for there
# is a one-to-one mapping between x and str(x) for every x in "choices".
# The ids do not necessarily all have to have the same type, but
# managing that is left to the programmer.  For example:
#  choices=[1, 2, "3", "4"] is permitted, but
#  choices=[1, 2, "1", "2"] is not,
# because str(1) == "1" and str("1") =="1", and because str(2) == "2"
# and str("2") == "2".
#
# This requirement is not enforced by the code.
#
# config.item.value and config.item.getValue always return an object
# of the type of the selected item.
#
# When assigning to config.item.value or using config.item.setValue,
# where x is in the "choices" list, either x or str(x) may be used
# to set the choice. The form of the assignment will not affect the
# choices list or the type returned by the ConfigSelection instance.
#
# This replaces the former requirement that all ids MUST be plain
# strings, but is compatible with that requirement.
#
class ConfigSelection(ConfigElement):
	def __init__(self, choices, default=None):
		ConfigElement.__init__(self)
		self.choices = choicesList(choices)
		if default is None:
			default = self.choices.default()
		self._descr = None
		self._value = self.lastValue = self.default = default

	def setChoices(self, choices, default=None):
		value = self.value
		self.choices = choicesList(choices)
		if default is None:
			default = self.choices.default()
		self.default = default
		if self.value not in self.choices:
			self.value = default
		if self.value != value:
			self.changed()

	def setValue(self, value):
		if str(value) in map(str, self.choices):
			self._value = self.choices[self.choices.index(value)]
		else:
			self._value = self.default
		self._descr = None
		self.changed()

	def tostring(self, val):
		return str(val)

	def toDisplayString(self, val):
		return self.description[val]

	def getValue(self):
		return self._value

	def load(self):
		sv = self.saved_value
		if sv is None:
			self.value = self.default
		else:
			self.value = self.choices[self.choices.index(sv)]

	def setCurrentText(self, text):
		i = self.choices.index(self.value)
		self.choices[i] = text
		self._descr = self.description[text] = text
		self._value = text

	value = property(getValue, setValue)

	def getIndex(self):
		return self.choices.index(self.value)

	index = property(getIndex)

	# GUI
	def handleKey(self, key):
		nchoices = len(self.choices)
		if nchoices > 1:
			i = self.choices.index(self.value)
			if key == ACTIONKEY_LEFT:
				self.value = self.choices[(i + nchoices - 1) % nchoices]
			elif key == ACTIONKEY_RIGHT:
				self.value = self.choices[(i + 1) % nchoices]
			elif key == ACTIONKEY_FIRST:
				self.value = self.choices[0]
			elif key == ACTIONKEY_LAST:
				self.value = self.choices[nchoices - 1]

	def selectNext(self):
		nchoices = len(self.choices)
		i = self.choices.index(self.value)
		self.value = self.choices[(i + 1) % nchoices]

	def getText(self):
		if self._descr is None:
			self._descr = self.description[self.value]
		return self._descr

	def getMulti(self, selected):
		if self._descr is None:
			self._descr = self.description[self.value]
		return ("text", self._descr)

	# HTML - Is this actually used?
	def getHTML(self, id):
		res = ""
		for v in self.choices:
			descr = self.description[v]
			if self.value == v:
				checked = "checked=\"checked\" "
			else:
				checked = ""
			res += "<input type=\"radio\" name=\"" + id + "\" " + checked + "value=\"" + v + "\">" + descr + "</input></br>\n"
		return res

	def unsafeAssign(self, value):
		self.value = value  # setValue does check if value is in choices. This is safe enough.

	description = property(lambda self: descriptionList(self.choices.choices, self.choices.type))


# This is a special control that is a place holder in a settings list that does nothing.
#
class ConfigNothing(ConfigSelection):
	def __init__(self):
		ConfigSelection.__init__(self, choices=[("", "")])


class ConfigSatlist(ConfigSelection):
	def __init__(self, list, default=None):
		if default is not None:
			default = str(default)
		ConfigSelection.__init__(self, choices=[(str(orbpos), desc) for (orbpos, desc, flags) in list], default=default)

	def getOrbitalPosition(self):
		if self.value == "":
			return None
		return int(self.value)

	orbital_position = property(getOrbitalPosition)


# Lets the user select between [min, min + stepwidth, min + (stepwidth * 2)...,
# maxval] with maxval <= max depending on the stepwidth. The min, max, stepwidth,
# and default are int values.
#
# wraparound: Pressing RIGHT key at max value brings you to min value and vice
# versa if set to True.
#
class ConfigSelectionNumber(ConfigSelection):
	def __init__(self, min, max, stepwidth, default=None, wraparound=False):
		self.wraparound = wraparound
		if default is None:
			default = min
		default = str(default)
		choices = []
		step = min
		while step <= max:
			choices.append(str(step))
			step += stepwidth
		ConfigSelection.__init__(self, choices, default)

	def getValue(self):
		return int(ConfigSelection.getValue(self))

	def setValue(self, val):
		ConfigSelection.setValue(self, str(val))

	value = property(getValue, setValue)

	def handleKey(self, key):
		if not self.wraparound:
			if key == ACTIONKEY_RIGHT:
				if len(self.choices) == (self.choices.index(self.value) + 1):
					return
			if key == ACTIONKEY_LEFT:
				if self.choices.index(self.value) == 0:
					return
		ConfigSelection.handleKey(self, key)


# This is the control, and base class, for formatted sequence settings.
#
# *THE* mighty config element class!
#
# Allows you to store/edit a sequence of values.  Can be used for IP-addresses,
# dates, plain integers, several helpers exist to ease this up a bit.
#
class ConfigSequence(ConfigElement):
	def __init__(self, seperator, limits, default, censor=""):
		ConfigElement.__init__(self)
		assert isinstance(limits, list) and len(limits[0]) == 2, "[Config] Error: Limits must be [(min, max),...]-tuple-list!"
		assert censor == "" or len(censor) == 1, "[Config] Error: Censor must be a single char (or \"\")!"
		# assert isinstance(default, list), "[Config] Error: Default must be a list!"
		# assert isinstance(default[0], int), "[Config] Error: List must contain numbers!"
		# assert len(default) == len(limits), "[Config] Error: Length must match!"
		self.marked_pos = 0
		self.seperator = seperator
		self.limits = limits
		self.censor = censor
		self.hidden = censor != ""
		self.lastValue = self.default = default
		self.value = shallowcopy(default)
		self.endNotifier = None

	def validate(self):
		max_pos = 0
		num = 0
		for i in self._value:
			max_pos += len(str(self.limits[num][1]))

			if self._value[num] < self.limits[num][0]:
				self._value[num] = self.limits[num][0]
			if self._value[num] > self.limits[num][1]:
				self._value[num] = self.limits[num][1]
			num += 1
		if self.marked_pos >= max_pos:
			if self.endNotifier:
				for x in self.endNotifier:
					x(self)
			self.marked_pos = max_pos - 1
		if self.marked_pos < 0:
			self.marked_pos = 0

	def validatePos(self):
		if self.marked_pos < 0:
			self.marked_pos = 0
		total_len = sum([len(str(x[1])) for x in self.limits])
		if self.marked_pos >= total_len:
			self.marked_pos = total_len - 1

	def addEndNotifier(self, notifier):
		if self.endNotifier is None:
			self.endNotifier = []
		self.endNotifier.append(notifier)

	def handleKey(self, key):
		if key == ACTIONKEY_FIRST:
			self.marked_pos = 0
			self.validatePos()
		elif key == ACTIONKEY_LEFT:
			self.marked_pos -= 1
			self.validatePos()
		elif key == ACTIONKEY_RIGHT:
			self.marked_pos += 1
			self.validatePos()
		elif key == ACTIONKEY_LAST:
			max_pos = 0
			num = 0
			for i in self._value:
				max_pos += len(str(self.limits[num][1]))
				num += 1
			self.marked_pos = max_pos - 1
			self.validatePos()
		elif key in ACTIONKEY_NUMBERS or key == ACTIONKEY_ASCII:
			if key == ACTIONKEY_ASCII:
				code = getPrevAsciiCode()
				if code < 48 or code > 57:
					return
				number = code - 48
			else:
				number = getKeyNumber(key)
			block_len = [len(str(x[1])) for x in self.limits]
			total_len = sum(block_len)
			pos = 0
			blocknumber = 0
			block_len_total = [0]
			for x in block_len:
				pos += block_len[blocknumber]
				block_len_total.append(pos)
				if pos - 1 >= self.marked_pos:
					pass
				else:
					blocknumber += 1
			number_len = len(str(self.limits[blocknumber][1]))  # Length of number block.
			posinblock = self.marked_pos - block_len_total[blocknumber]  # Position in the block.
			oldvalue = abs(self._value[blocknumber])  # We are using abs() in order to allow change negative values like default -1.
			olddec = oldvalue % 10 ** (number_len - posinblock) - (oldvalue % 10 ** (number_len - posinblock - 1))
			newvalue = oldvalue - olddec + (10 ** (number_len - posinblock - 1) * number)
			self._value[blocknumber] = newvalue
			self.marked_pos += 1
			self.validate()
			self.changed()

	def genText(self):
		value = ""
		mPos = self.marked_pos
		num = 0
		for i in self._value:
			if value:  # Fixme no heading separator possible!
				value += self.seperator
				if mPos >= len(value) - 1:
					mPos += 1
			if self.censor == "" or not self.hidden:
				value += ("%0" + str(len(str(self.limits[num][1]))) + "d") % i
			else:
				value += (self.censor * len(str(self.limits[num][1])))
			num += 1
		return (value, mPos)

	def getText(self):
		(value, mPos) = self.genText()
		return value

	def getMulti(self, selected):
		(value, mPos) = self.genText()
		# Only mark cursor when we are selected.  (This code is heavily ink optimized!)
		if self.enabled:
			return ("mtext"[1 - selected:], value, [mPos])
		else:
			return ("text", value)

	def tostring(self, val):
		return self.seperator.join([self.saveSingle(x) for x in val])

	def saveSingle(self, v):
		return str(v)

	def fromstring(self, value):
		ret = [int(x) for x in value.split(self.seperator)]
		return ret + [int(x[0]) for x in self.limits[len(ret):]]

	def onSelect(self, session):
		self.hidden = False

	def onDeselect(self, session):
		self.hidden = self.censor != ""
		if self.lastValue != self._value:
			self.changedFinal()
			self.lastValue = shallowcopy(self._value)


cec_limits = [(0, 15), (0, 15), (0, 15), (0, 15)]


class ConfigCECAddress(ConfigSequence):
	def __init__(self, default, auto_jump=False):
		ConfigSequence.__init__(self, seperator=".", limits=cec_limits, default=default)
		self.block_len = [len(str(x[1])) for x in self.limits]
		self.marked_block = 0
		self.overwrite = True
		self.auto_jump = auto_jump

	def handleKey(self, key):
		if key == ACTIONKEY_LEFT:
			if self.marked_block > 0:
				self.marked_block -= 1
			self.overwrite = True
		elif key == ACTIONKEY_RIGHT:
			if self.marked_block < len(self.limits) - 1:
				self.marked_block += 1
			self.overwrite = True
		elif key == ACTIONKEY_FIRST:
			self.marked_block = 0
			self.overwrite = True
		elif key == ACTIONKEY_LAST:
			self.marked_block = len(self.limits) - 1
			self.overwrite = True
		elif key in ACTIONKEY_NUMBERS or key == ACTIONKEY_ASCII:
			if key == ACTIONKEY_ASCII:
				code = getPrevAsciiCode()
				if code < 48 or code > 57:
					return
				number = code - 48
			else:
				number = getKeyNumber(key)
			oldvalue = self._value[self.marked_block]
			if self.overwrite:
				self._value[self.marked_block] = number
				self.overwrite = False
			else:
				oldvalue *= 10
				newvalue = oldvalue + number
				if self.auto_jump and newvalue > self.limits[self.marked_block][1] and self.marked_block < len(self.limits) - 1:
					self.handleKey(ACTIONKEY_RIGHT)
					self.handleKey(key)
					return
				else:
					self._value[self.marked_block] = newvalue
			if len(str(self._value[self.marked_block])) >= self.block_len[self.marked_block]:
				self.handleKey(ACTIONKEY_RIGHT)
			self.validate()
			self.changed()

	def genText(self):
		value = ""
		block_strlen = []
		for i in self._value:
			block_strlen.append(len(str(i)))
			if value:
				value += self.seperator
			value += str(i)
		leftPos = sum(block_strlen[:(self.marked_block)]) + self.marked_block
		rightPos = sum(block_strlen[:(self.marked_block + 1)]) + self.marked_block
		mBlock = range(leftPos, rightPos)
		return (value, mBlock)

	def getMulti(self, selected):
		(value, mBlock) = self.genText()
		if self.enabled:
			return ("mtext"[1 - selected:], value, mBlock)
		else:
			return ("text", value)

	def getHTML(self, id):
		return ".".join(["%d" % d for d in self.value])  # We definitely don't want leading zeros.


clock_limits = [(0, 23), (0, 59)]


class ConfigClock(ConfigSequence):
	def __init__(self, default):
		self.time = localtime(default)
		ConfigSequence.__init__(self, seperator=":", limits=clock_limits, default=[self.time.tm_hour, self.time.tm_min])

	def increment(self):
		if self._value[1] == 59:  # Check if Minutes maxed out, increment Hour, reset Minutes.
			if self._value[0] < 23:
				self._value[0] += 1
			else:
				self._value[0] = 0
			self._value[1] = 0
		else:  # Increment Minutes.
			self._value[1] += 1
		self.changed()  # Trigger change.

	def decrement(self):
		if self._value[1] == 0:  # Check if Minutes is minimum, decrement Hour, set Minutes to 59.
			if self._value[0] > 0:
				self._value[0] -= 1
			else:
				self._value[0] = 23
			self._value[1] = 59
		else:  # Decrement Minutes.
			self._value[1] -= 1
		self.changed()  # Trigger change.

	def handleKey(self, key):
		if key == ACTIONKEY_DELETE and config.usage.time.wide.value:
			if self._value[0] < 12:
				self._value[0] += 12
				self.validate()
				self.changed()
		elif key == ACTIONKEY_BACKSPACE and config.usage.time.wide.value:
			if self._value[0] >= 12:
				self._value[0] -= 12
				self.validate()
				self.changed()
		elif key in ACTIONKEY_NUMBERS or key == ACTIONKEY_ASCII:
			if key == ACTIONKEY_ASCII:
				code = getPrevAsciiCode()
				if code < 48 or code > 57:
					return
				digit = code - 48
			else:
				digit = getKeyNumber(key)
			hour = self._value[0]
			pmadjust = 0
			if config.usage.time.wide.value:
				if hour > 11:  # All the PM times.
					hour -= 12
					pmadjust = 12
				if hour == 0:  # 12AM & 12PM map to 12.
					hour = 12
				if self.marked_pos == 0 and digit >= 2:  # Only 0, 1 allowed (12 hour clock).
					return
				if self.marked_pos == 1 and hour > 9 and digit >= 3:  # Only 10, 11, 12 allowed.
					return
				if self.marked_pos == 1 and hour < 10 and digit == 0:  # Only 01, 02, ..., 09 allowed.
					return
			else:
				if self.marked_pos == 0 and digit >= 3:  # Only 0, 1, 2 allowed (24 hour clock).
					return
				if self.marked_pos == 1 and hour > 19 and digit >= 4:  # Only 20, 21, 22, 23 allowed.
					return
			if self.marked_pos == 2 and digit >= 6:  # Only 0, 1, ..., 5 allowed (tens digit of minutes).
				return
			value = bytearray(b"%02d%02d" % (hour, self._value[1]))  # Must be ASCII!
			value[self.marked_pos] = digit + ord(b"0")
			hour = int(value[:2])
			minute = int(value[2:])
			if config.usage.time.wide.value:
				if hour == 12:  # 12AM & 12PM map to back to 00.
					hour = 0
				elif hour > 12:
					hour = 10
				hour += pmadjust
			elif hour > 23:
				hour = 20
			self._value[0] = hour
			self._value[1] = minute
			self.marked_pos += 1
			self.validate()
			self.changed()
		else:
			ConfigSequence.handleKey(self, key)

	def genText(self):
		mPos = self.marked_pos
		if mPos >= 2:
			mPos += 1  # Skip over the separator.
		newtime = list(self.time)
		newtime[3] = self._value[0]
		newtime[4] = self._value[1]
		value = strftime(config.usage.time.short.value.replace("%-I", "%_I").replace("%-H", "%_H"), newtime)
		return value, mPos


date_limits = [(1, 31), (1, 12), (1970, 2050)]


class ConfigDate(ConfigSequence):
	def __init__(self, default):
		date = localtime(default)
		ConfigSequence.__init__(self, seperator=".", limits=date_limits, default=[date.tm_mday, date.tm_mon, date.tm_year])


class ConfigFloat(ConfigSequence):
	def __init__(self, default, limits):
		ConfigSequence.__init__(self, seperator=".", limits=limits, default=default)

	def getFloat(self):
		return float(self.value[1] / float(self.limits[1][1] + 1) + self.value[0])

	float = property(getFloat)

	def getFloatInt(self):
		return int(self.value[0] * float(self.limits[1][1] + 1) + self.value[1])

	def setFloatInt(self, val):
		self.value[0] = val / float(self.limits[1][1] + 1)
		self.value[1] = val % float(self.limits[1][1] + 1)

	floatint = property(getFloatInt, setFloatInt)


integer_limits = (0, 9999999999)


class ConfigInteger(ConfigSequence):
	def __init__(self, default, limits=integer_limits):
		ConfigSequence.__init__(self, seperator=":", limits=[limits], default=default)

	def setValue(self, value):
		self._value = [value]
		self.changed()

	def getValue(self):
		return self._value[0]

	value = property(getValue, setValue)

	def fromstring(self, value):
		return int(value)

	def tostring(self, value):
		return str(value)


class ConfigPIN(ConfigInteger):
	def __init__(self, default, pinLength=4, censor=u"\u2022"):
		assert isinstance(default, int), "[Config] Error: 'ConfigPIN' default must be an integer!"
		assert censor == "" or len(censor) == 1, "[Config] Error: Censor must be a single char (or \"\")!"
		censor = censor.encode("UTF-8", errors="ignore") if PY2 else censor
		ConfigSequence.__init__(self, seperator=":", limits=[(0, (10 ** pinLength) - 1)], censor=censor, default=default)
		self.len = len

	def getLength(self):
		return self.len


ip_limits = [(0, 255), (0, 255), (0, 255), (0, 255)]


class ConfigIP(ConfigSequence):
	def __init__(self, default, auto_jump=False):
		ConfigSequence.__init__(self, seperator=".", limits=ip_limits, default=default)
		self.block_len = [len(str(x[1])) for x in self.limits]
		self.marked_block = 0
		self.overwrite = True
		self.auto_jump = auto_jump

	def handleKey(self, key):
		if key == ACTIONKEY_LEFT:
			if self.marked_block > 0:
				self.marked_block -= 1
			self.overwrite = True
		elif key == ACTIONKEY_RIGHT:
			if self.marked_block < len(self.limits) - 1:
				self.marked_block += 1
			self.overwrite = True
		elif key == ACTIONKEY_FIRST:
			self.marked_block = 0
			self.overwrite = True
		elif key == ACTIONKEY_LAST:
			self.marked_block = len(self.limits) - 1
			self.overwrite = True
		elif key in ACTIONKEY_NUMBERS or key == ACTIONKEY_ASCII:
			if key == ACTIONKEY_ASCII:
				code = getPrevAsciiCode()
				if code < 48 or code > 57:
					return
				number = code - 48
			else:
				number = getKeyNumber(key)
			oldvalue = self._value[self.marked_block]
			if self.overwrite:
				self._value[self.marked_block] = number
				self.overwrite = False
			else:
				oldvalue *= 10
				newvalue = oldvalue + number
				if self.auto_jump and newvalue > self.limits[self.marked_block][1] and self.marked_block < len(self.limits) - 1:
					self.handleKey(ACTIONKEY_RIGHT)
					self.handleKey(key)
					return
				else:
					self._value[self.marked_block] = newvalue
			if len(str(self._value[self.marked_block])) >= self.block_len[self.marked_block]:
				self.handleKey(ACTIONKEY_RIGHT)
			self.validate()
			self.changed()

	def genText(self):
		value = ""
		block_strlen = []
		for i in self._value:
			block_strlen.append(len(str(i)))
			if value:
				value += self.seperator
			value += str(i)
		leftPos = sum(block_strlen[:(self.marked_block)]) + self.marked_block
		rightPos = sum(block_strlen[:(self.marked_block + 1)]) + self.marked_block
		mBlock = range(leftPos, rightPos)
		return (value, mBlock)

	def getMulti(self, selected):
		(value, mBlock) = self.genText()
		if self.enabled:
			return ("mtext"[1 - selected:], value, mBlock)
		else:
			return ("text", value)

	def getHTML(self, id):
		return ".".join(["%d" % d for d in self.value])  # We definitely don't want leading zeros.


mac_limits = [(1, 255), (1, 255), (1, 255), (1, 255), (1, 255), (1, 255)]


class ConfigMAC(ConfigSequence):
	def __init__(self, default):
		ConfigSequence.__init__(self, seperator=":", limits=mac_limits, default=default)


class ConfigPosition(ConfigSequence):
	def __init__(self, default, args):
		ConfigSequence.__init__(self, seperator=",", limits=[(0, args[0]), (0, args[1]), (0, args[2]), (0, args[3])], default=default)


# This is the control, and base class, for a set/list of selection value toggle settings.
#
class ConfigSet(ConfigElement):
	def __init__(self, choices, default=None):
		ConfigElement.__init__(self)
		if isinstance(choices, list):
			choices.sort()
			self.choices = choicesList(choices, choicesList.LIST_TYPE_LIST)
		else:
			assert False, "[Config] Error: 'ConfigSet' choices must be a list!"
		if default is None:
			default = []
		default.sort()
		self.lastValue = self.default = default
		self.value = shallowcopy(default)
		self.pos = 0

	def handleKey(self, key):
		if key in [ACTIONKEY_TOGGLE, ACTIONKEY_SELECT, ACTIONKEY_DELETE, ACTIONKEY_BACKSPACE] + ACTIONKEY_NUMBERS:
			value = self.value
			choice = self.choices[self.pos]
			if choice in value:
				value.remove(choice)
			else:
				value.append(choice)
				value.sort()
			self.changed()
		elif key == ACTIONKEY_LEFT:
			if self.pos > 0:
				self.pos -= 1
			else:
				self.pos = len(self.choices) - 1
		elif key == ACTIONKEY_RIGHT:
			if self.pos < len(self.choices) - 1:
				self.pos += 1
			else:
				self.pos = 0
		elif key == ACTIONKEY_FIRST:
			self.pos = 0
		elif key == ACTIONKEY_LAST:
			self.pos = len(self.choices) - 1

	def load(self):
		ConfigElement.load(self)
		if not self.value:
			self.value = []
		if not isinstance(self.value, list):
			self.value = list(self.value)
		self.value.sort()

	def fromstring(self, val):
		return eval(val)

	def tostring(self, val):
		return str(val)

	def toDisplayString(self, val):
		return ", ".join([self.description[x] for x in val])

	def getText(self):
		return " ".join([self.description[x] for x in self.value])

	def getMulti(self, selected):
		if selected:
			text = []
			pos = 0
			start = 0
			end = 0
			for item in self.choices:
				itemStr = str(item)
				text.append(" %s " % itemStr if item in self.value else "(%s)" % itemStr)
				length = 2 + len(itemStr)
				if item == self.choices[self.pos]:
					start = pos
					end = start + length
				pos += length
			return ("mtext", "".join(text), range(start, end))
		else:
			return ("text", " ".join([self.description[x] for x in self.value]))

	def onDeselect(self, session):
		# self.pos = 0  # Enable this to reset the position marker to the first element.
		if self.lastValue != self.value:
			self.changedFinal()
			self.lastValue = shallowcopy(self.value)

	description = property(lambda self: descriptionList(self.choices.choices, choicesList.LIST_TYPE_LIST))


# This is the control, and base class, for slider settings.
#
class ConfigSlider(ConfigElement):
	def __init__(self, default=0, increment=1, limits=(0, 100)):
		ConfigElement.__init__(self)
		self.value = self.lastValue = self.default = default
		self.min = limits[0]
		self.max = limits[1]
		self.increment = increment

	def checkValues(self, value=None):
		if value is None:
			value = self.value
		if value < self.min:
			value = self.min
		if value > self.max:
			value = self.max
		if self.value != value:  # Avoid call of setter if value not changed.
			self.value = value

	def handleKey(self, key):
		if key == ACTIONKEY_LEFT:
			self.value -= self.increment
		elif key == ACTIONKEY_RIGHT:
			self.value += self.increment
		elif key == ACTIONKEY_FIRST:
			self.value = self.min
		elif key == ACTIONKEY_LAST:
			self.value = self.max
		else:
			return
		self.checkValues()

	def getText(self):
		return "%d / %d" % (self.value, self.max)

	def getMulti(self, selected):
		self.checkValues()
		return ("slider", self.value, self.max)

	def fromstring(self, value):
		return int(value)


# This is the control, and base class, for editable text settings.
#
class ConfigText(ConfigElement, NumericalTextInput):
	def __init__(self, default="", fixed_size=True, visible_width=False):
		ConfigElement.__init__(self)
		NumericalTextInput.__init__(self, nextFunc=self.nextFunc, handleTimeout=False, mode="Default")
		self.marked_pos = 0
		self.allmarked = (default != "")  # This is also used in Input.py!
		self.fixed_size = fixed_size
		self.visible_width = visible_width
		self.offset = 0
		self.overwrite = fixed_size
		self.help_window = None
		self.value = self.lastValue = self.default = default

	def handleKey(self, key):  # This will not change anything on the value itself so we can handle it here in GUI element.
		if key == ACTIONKEY_FIRST:
			self.timeout()
			self.allmarked = False
			self.marked_pos = 0
		elif key == ACTIONKEY_LEFT:
			self.timeout()
			if self.allmarked:
				self.marked_pos = len(self.text)
				self.allmarked = False
			else:
				self.marked_pos -= 1
		elif key == ACTIONKEY_RIGHT:
			self.timeout()
			if self.allmarked:
				self.marked_pos = 0
				self.allmarked = False
			else:
				self.marked_pos += 1
		elif key == ACTIONKEY_LAST:
			self.timeout()
			self.allmarked = False
			self.marked_pos = len(self.text)
		elif key == ACTIONKEY_BACKSPACE:
			self.timeout()
			if self.allmarked:
				self.deleteAllChars()
				self.allmarked = False
			elif self.marked_pos > 0:
				self.deleteChar(self.marked_pos - 1)
				if not self.fixed_size and self.offset > 0:
					self.offset -= 1
				self.marked_pos -= 1
		elif key == ACTIONKEY_DELETE:
			self.timeout()
			if self.allmarked:
				self.deleteAllChars()
				self.allmarked = False
			else:
				self.deleteChar(self.marked_pos)
				if self.fixed_size and self.overwrite:
					self.marked_pos += 1
		elif key == ACTIONKEY_ERASE:
			self.timeout()
			self.deleteAllChars()
		elif key == ACTIONKEY_TOGGLE:
			self.timeout()
			self.overwrite = not self.overwrite
		elif key == ACTIONKEY_ASCII:
			self.timeout()
			newChar = pyunichr(getPrevAsciiCode())
			if not self.useableChars or newChar in self.useableChars:
				if self.allmarked:
					self.deleteAllChars()
					self.allmarked = False
				self.insertChar(newChar, self.marked_pos, False)
				self.marked_pos += 1
		elif key in ACTIONKEY_NUMBERS:
			owr = self.lastKey == getKeyNumber(key)
			newChar = self.getKey(getKeyNumber(key))
			if self.allmarked:
				self.deleteAllChars()
				self.allmarked = False
			self.insertChar(newChar, self.marked_pos, owr)
		elif key == ACTIONKEY_TIMEOUT:
			self.timeout()
			if self.help_window:
				self.help_window.update(self)
			return
		if self.help_window:
			self.help_window.update(self)
		self.validateMarker()
		self.changed()

	def insertChar(self, ch, pos, owr):
		if owr or self.overwrite:
			self.text = self.text[0:pos] + ch + self.text[pos + 1:]
		elif self.fixed_size:
			self.text = self.text[0:pos] + ch + self.text[pos:-1]
		else:
			self.text = self.text[0:pos] + ch + self.text[pos:]

	def deleteChar(self, pos):
		if not self.fixed_size:
			self.text = self.text[0:pos] + self.text[pos + 1:]
		elif self.overwrite:
			self.text = self.text[0:pos] + " " + self.text[pos + 1:]
		else:
			self.text = self.text[0:pos] + self.text[pos + 1:] + " "

	def deleteAllChars(self):
		if self.fixed_size:
			self.text = " " * len(self.text)
		else:
			self.text = ""
		self.marked_pos = 0

	def validateMarker(self):
		textlen = len(self.text)
		if self.fixed_size:
			if self.marked_pos > textlen - 1:
				self.marked_pos = textlen - 1
		else:
			if self.marked_pos > textlen:
				self.marked_pos = textlen
		if self.marked_pos < 0:
			self.marked_pos = 0
		if self.visible_width:
			if self.marked_pos < self.offset:
				self.offset = self.marked_pos
			if self.marked_pos >= self.offset + self.visible_width:
				if self.marked_pos == textlen:
					self.offset = self.marked_pos - self.visible_width
				else:
					self.offset = self.marked_pos - self.visible_width + 1
			if self.offset > 0 and self.offset + self.visible_width > textlen:
				self.offset = max(0, len - self.visible_width)

	def nextFunc(self):
		self.marked_pos += 1
		self.validateMarker()
		self.changed()

	def getText(self):
		return self.text.encode("UTF-8", errors="ignore") if PY2 else self.text

	def getMulti(self, selected):
		if self.visible_width:
			if self.allmarked:
				mark = range(0, min(self.visible_width, len(self.text)))
			else:
				mark = [self.marked_pos - self.offset]
			return ("mtext"[1 - selected:], self.text[self.offset:self.offset + self.visible_width].encode("UTF-8", errors="ignore") + " ", mark)
		else:
			if self.allmarked:
				mark = range(0, len(self.text))
			else:
				mark = [self.marked_pos]
			return ("mtext"[1 - selected:], self.text.encode("UTF-8", errors="ignore") + " ", mark)

	def getValue(self):
		if PY2:
			try:
				return self.text.encode("UTF-8", errors="ignore")
			except UnicodeDecodeError:
				print("[config] Broken UTF8!")
				return self.text
		else:
			return self.text

	def setValue(self, value):
		if PY2:
			try:
				self.text = value.decode("UTF-8", errors="ignore")
			except UnicodeDecodeError:
				self.text = value.decode("UTF-8", error="ignore")
				print("[config] Broken UTF8!")
		else:
			self.text = value

	value = property(getValue, setValue)
	_value = property(getValue, setValue)

	def onSelect(self, session):
		self.allmarked = (self.value != "")
		if session is not None:
			from Screens.NumericalTextInputHelpDialog import NumericalTextInputHelpDialog
			self.help_window = session.instantiateDialog(NumericalTextInputHelpDialog, self)
			if BoxInfo.getItem("OSDAnimation"):
				self.help_window.setAnimationMode(0)
			self.help_window.show()

	def onDeselect(self, session):
		self.marked_pos = 0
		self.offset = 0
		if self.help_window:
			session.deleteDialog(self.help_window)
			self.help_window = None
		if self.lastValue != self.value:
			self.changedFinal()
			self.lastValue = self.value

	def showHelp(self, session):
		if session is not None and self.help_window is not None:
			self.help_window.show()

	def hideHelp(self, session):
		if session is not None and self.help_window is not None:
			self.help_window.hide()

	def getHTML(self, id):  # DEBUG: Is this still used?
		return "<input type=\"text\" name=\"" + id + "\" value=\"" + self.value + "\" /><br>\n"

	def unsafeAssign(self, value):  # DEBUG: Is this still used?
		self.value = str(value)


class ConfigDirectory(ConfigText):
	def __init__(self, default="", visible_width=60):
		ConfigText.__init__(self, default, fixed_size=True, visible_width=visible_width)

	def handleKey(self, key):
		pass

	def getMulti(self, selected):
		if self.text == "":
			return ("mtext"[1 - selected:], _("List of storage devices"), range(0))
		else:
			return ConfigText.getMulti(self, selected)

	def onSelect(self, session):
		self.allmarked = (self.value != "")


class ConfigMACText(ConfigText):
	def __init__(self, default="", visible_width=17):
		ConfigText.__init__(self, default, fixed_size=True, visible_width=visible_width)
		NumericalTextInput.setMode(self, "HexFastLogicalUpper")  # HexFastUpper
		self.allmarked = False

	def handleKey(self, key):
		if key == ACTIONKEY_FIRST:
			self.timeout()
			self.marked_pos = 0
		elif key == ACTIONKEY_LEFT:
			self.timeout()
			if self.text[self.marked_pos - 1] == ":":
				self.marked_pos -= 2
			else:
				self.marked_pos -= 1
		elif key == ACTIONKEY_RIGHT:
			self.timeout()
			if self.marked_pos < self.visible_width - 1 and self.text[self.marked_pos + 1] == ":":
				self.marked_pos += 2
			else:
				self.marked_pos += 1
		elif key == ACTIONKEY_LAST:
			self.timeout()
			self.marked_pos = len(self.text)
		elif key == ACTIONKEY_ERASE:
			self.timeout()
			self.text = self.text[2].join(["00"] * 6)
			self.marked_pos = 0
		elif key in ACTIONKEY_NUMBERS:
			owr = self.lastKey == getKeyNumber(key)
			newChar = self.getKey(getKeyNumber(key))
			self.insertChar(newChar, self.marked_pos, owr)
		elif key == ACTIONKEY_TIMEOUT:
			self.timeout()
			if self.help_window:
				self.help_window.update(self)
			if self.text[self.marked_pos] == ":":
				self.marked_pos += 1
			return
		if self.help_window:
			self.help_window.update(self)
		self.validateMarker()
		self.changed()

	def validateMarker(self):
		textlen = len(self.text)
		if self.marked_pos > textlen - 1:
			self.marked_pos = textlen - 1
		elif self.marked_pos < 0:
			self.marked_pos = 0

	def insertChar(self, ch, pos, owr):
		if self.text[pos] == ":":
			pos += 1
		ConfigText.insertChar(self, ch, pos, owr)

	def onSelect(self, session):
		ConfigText.onSelect(self, session)
		self.allmarked = False


class ConfigMacText(ConfigMACText):  # Deprecated class name.
	def __init__(self, default="", visible_width=17):
		ConfigMACText.__init__(self, default=default, visible_width=visible_width)


class ConfigNumber(ConfigText):
	def __init__(self, default=0):
		ConfigText.__init__(self, str(default), fixed_size=False)
		NumericalTextInput.setMode(self, "Number")

	def handleKey(self, key):
		if key in ACTIONKEY_NUMBERS or key == ACTIONKEY_ASCII:
			if key == ACTIONKEY_ASCII:
				ascii = getPrevAsciiCode()
				if not (48 <= ascii <= 57):
					return
			else:
				ascii = getKeyNumber(key) + 48
			newChar = pyunichr(ascii)
			if self.allmarked:
				self.deleteAllChars()
				self.allmarked = False
			self.insertChar(newChar, self.marked_pos, False)
			self.marked_pos += 1
			self.changed()
		else:
			ConfigText.handleKey(self, key)
		self.validateMarker()

	def validateMarker(self):
		pos = len(self.text) - self.marked_pos
		self.text = self.text.lstrip("0")
		if self.text == "":
			self.text = "0"
		if pos > len(self.text):
			self.marked_pos = 0
		else:
			self.marked_pos = len(self.text) - pos

	def getValue(self):
		try:
			return int(self.text)
		except ValueError:
			self.text = "1" if self.text.lower() == "true" else self.default
			return int(self.text)

	def setValue(self, value):
		self.text = str(value)

	value = property(getValue, setValue)
	_value = property(getValue, setValue)

	def isChanged(self):
		saved = self.saved_value
		valueString = self.tostring(self.value)
		if saved is None and valueString == str(self.default):
			return False
		return valueString != self.tostring(saved)

	# def onSelect(self, session):  # Enable this method to disable the NumericalTextInputHelpDialog window.
	# 	self.allmarked = (self.value != "")


class ConfigPassword(ConfigText):
	def __init__(self, default="", fixed_size=False, visible_width=False, censor=u"\u2022"):
		ConfigText.__init__(self, default=default, fixed_size=fixed_size, visible_width=visible_width)
		assert censor == "" or len(censor) == 1, "[Config] Error: Censor must be a single char (or \"\")!"
		self.censor = censor.encode("UTF-8", errors="ignore") if PY2 else censor
		self.hidden = True

	def getMulti(self, selected):
		mtext, text, mark = ConfigText.getMulti(self, selected)
		if self.hidden:
			text = self.censor * len(text)  # For more security a fixed length string can be used!
		return (mtext, text, mark)

	def onSelect(self, session):
		ConfigText.onSelect(self, session)
		self.hidden = False

	def onDeselect(self, session):
		self.hidden = True
		ConfigText.onDeselect(self, session)


class ConfigSearchText(ConfigText):
	def __init__(self, default="", fixed_size=False, visible_width=False):
		ConfigText.__init__(self, default=default, fixed_size=fixed_size, visible_width=visible_width)
		NumericalTextInput.setMode(self, "Search")


# Until here, "saved_value" always had to be a *string*.  Now, in
# ConfigSubsection, and only there, "saved_value" is a dict, essentially
# forming a tree:
#
# config.foo.bar=True
# config.foobar=False
#
# turns into:
#
# config.saved_value == {"foo": {"bar": "True"}, "foobar": "False"}
#
class ConfigSubsectionContent(object):
	pass


# We store a backup of the loaded configuration data in self.stored_values,
# to be able to deploy them when a new config element will be added, so
# non-default values are instantly available.
#
# A list, for example:
#
# config.dipswitches = ConfigSubList()
# config.dipswitches.append(ConfigYesNo())
# config.dipswitches.append(ConfigYesNo())
# config.dipswitches.append(ConfigYesNo())
#
class ConfigSubList(list, object):
	def __init__(self):
		list.__init__(self)
		self.stored_values = {}

	def load(self):
		for x in self:
			x.load()

	def save(self):
		for x in self:
			x.save()

	def getSavedValue(self):
		res = {}
		for i, val in enumerate(self):
			sv = val.saved_value
			if sv is not None:
				res[str(i)] = sv
		return res

	def setSavedValue(self, values):
		self.stored_values = dict(values)
		for (key, val) in self.stored_values.items():
			if int(key) < len(self):
				self[int(key)].saved_value = val

	saved_value = property(getSavedValue, setSavedValue)

	def append(self, item):
		i = str(len(self))
		list.append(self, item)
		if i in self.stored_values:
			item.saved_value = self.stored_values[i]
			item.load()

	def dict(self):
		return dict([(str(index), value) for index, value in enumerate(self)])


# Same as ConfigSubList, just as a dictionary.  Care must be taken that the
# "key" has a proper str() method, because it will be used in the config file.
#
class ConfigSubDict(dict, object):
	def __init__(self):
		dict.__init__(self)
		self.stored_values = {}

	def __setitem__(self, key, item):
		dict.__setitem__(self, key, item)
		if str(key) in self.stored_values:
			item.saved_value = self.stored_values[str(key)]
			item.load()

	def load(self):
		for x in self.values():
			x.load()

	def save(self):
		for x in self.values():
			x.save()

	def getSavedValue(self):
		res = {}
		for (key, val) in self.items():
			sv = val.saved_value
			if sv is not None:
				res[str(key)] = sv
		return res

	def setSavedValue(self, values):
		self.stored_values = dict(values)
		for (key, val) in self.items():
			if str(key) in self.stored_values:
				val.saved_value = self.stored_values[str(key)]

	saved_value = property(getSavedValue, setSavedValue)

	def dict(self):
		return self


# Like the classes above, just with a more "native" syntax.
#
# Some evil stuff must be done to allow instant loading of added elements.
# This is why this class is so complex.
#
# We need the "content" because we overwrite __setattr__.
#
# If you don't understand this, try adding __setattr__ to a usual exisiting
# class and you will.
#
class ConfigSubsection(object):
	def __init__(self):
		self.__dict__["content"] = ConfigSubsectionContent()
		self.content.items = {}
		self.content.stored_values = {}

	def __getattr__(self, name):
		if name in self.content.items:
			return self.content.items[name]
		raise AttributeError(name)

	def __setattr__(self, name, value):
		if name == "saved_value":
			return self.setSavedValue(value)
		assert isinstance(value, (ConfigSubsection, ConfigElement, ConfigSubList, ConfigSubDict)), "[Config] Error: 'ConfigSubsection' can only store ConfigSubsections, ConfigSubLists, ConfigSubDicts or ConfigElements!"
		content = self.content
		content.items[name] = value
		x = content.stored_values.get(name, None)
		if x is not None:
			# print("[config] Ok, now we have a new item '%s' and have the following value for it '%s'." % (name, str(x)))
			value.saved_value = x
			value.load()

	def load(self):
		for x in self.content.items.values():
			x.load()

	def save(self):
		for x in self.content.items.values():
			x.save()

	def getSavedValue(self):
		res = self.content.stored_values
		for (key, val) in self.content.items.items():
			sv = val.saved_value
			if sv is not None:
				res[key] = sv
			elif key in res:
				del res[key]
		return res

	def setSavedValue(self, values):
		values = dict(values)
		self.content.stored_values = values
		for (key, val) in self.content.items.items():
			value = values.get(key, None)
			if value is not None:
				val.saved_value = value

	saved_value = property(getSavedValue, setSavedValue)

	def dict(self):
		return self.content.items


# The root config object, which also can "pickle" (=serialize) down the whole
# config tree.
#
# We try to keep non-existing config entries, to apply them whenever a new
# config entry is added to a subsection.  Also, non-existing config entries
# will be saved, so they won't be lost when a config entry disappears.
#
class Config(ConfigSubsection):
	def __init__(self):
		ConfigSubsection.__init__(self)

	def pickle_this(self, prefix, topickle, result):
		for (key, val) in sorted(topickle.items(), key=lambda x: str(x[0]) if x[0].isdigit() else x[0].lower()):
			name = ".".join((prefix, key))
			if isinstance(val, dict):
				self.pickle_this(name, val, result)
			elif isinstance(val, tuple):
				result += [name, "=", str(val[0]), "\n"]
			else:
				result += [name, "=", str(val), "\n"]

	def pickle(self):
		result = []
		self.pickle_this("config", self.saved_value, result)
		return "".join(result)

	def unpickle(self, lines, base_file=True):
		tree = {}
		configbase = tree.setdefault("config", {})
		for line in lines:
			if not line or line[0] == "#":
				continue
			result = line.split("=", 1)
			if len(result) != 2:
				continue
			(name, val) = result
			val = val.strip()
			names = name.split(".")
			base = configbase
			for n in names[1:-1]:
				base = base.setdefault(n, {})
			base[names[-1]] = val
			if not base_file:  # Not the initial config file.
				try:  # Update config.x.y.value when exist.
					configEntry = eval(name)
					if configEntry is not None:
						configEntry.value = val
				except (SyntaxError, KeyError):
					pass

		# We inherit from ConfigSubsection, so ...
		# object.__setattr__(self, "saved_value", tree["config"])
		if "config" in tree:
			self.setSavedValue(tree["config"])

	def saveToFile(self, filename):
		text = self.pickle()
		try:
			import os
			f = open(filename + ".writing", "w")
			f.write(text)
			f.flush()
			fsync(f.fileno())
			f.close()
			rename(filename + ".writing", filename)
		except (IOError, OSError) as err:
			print("[config] Error %d: Couldn't write '%s'!  (%s)" % (err.errno, filename, err.strerror))

	def loadFromFile(self, filename, base_file=True):
		self.unpickle(open(filename, "r"), base_file)


class ConfigFile:
	CONFIG_FILE = resolveFilename(SCOPE_CONFIG, "settings")

	def load(self):
		try:
			config.loadFromFile(self.CONFIG_FILE, True)
		except (IOError, OSError) as err:
			print("[config] Error %d: Unable to load config '%s', assuming defaults.  (%s)" % (err.errno, self.CONFIG_FILE, err.strerror))

	def save(self):
		# config.save()
		config.saveToFile(self.CONFIG_FILE)

	def __resolveValue(self, pickles, cmap):
		key = pickles[0]
		if key in cmap:
			if len(pickles) > 1:
				return self.__resolveValue(pickles[1:], cmap[key].dict())
			else:
				return str(cmap[key].value)
		return None

	def getResolvedKey(self, key):
		names = key.split(".")
		if len(names) > 1:
			if names[0] == "config":
				ret = self.__resolveValue(names[1:], config.content.items)
				if ret and len(ret) or ret == "":
					return ret
		print("[config] getResolvedKey '%s' failed !! (Typo??)" % key)
		return ""


config = Config()
config.misc = ConfigSubsection()
configfile = ConfigFile()
configfile.load()

# def _(x):
# 	return x
#
# config.bla = ConfigSubsection()
# config.bla.test = ConfigYesNo()
# config.nim = ConfigSubList()
# config.nim.append(ConfigSubsection())
# config.nim[0].bla = ConfigYesNo()
# config.nim.append(ConfigSubsection())
# config.nim[1].bla = ConfigYesNo()
# config.nim[1].blub = ConfigYesNo()
# config.arg = ConfigSubDict()
# config.arg["Hello"] = ConfigYesNo()
#
# config.arg["Hello"].handleKey(ACTIONKEY_RIGHT)
# config.arg["Hello"].handleKey(ACTIONKEY_RIGHT)
#
# #config.saved_value
#
# #configfile.save()
# config.save()
# print(config.pickle())
