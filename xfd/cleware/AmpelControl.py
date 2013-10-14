#!/usr/bin/python

import os
import sys
import urllib2
import time
import subprocess
from optparse import OptionParser
from bs4 import BeautifulSoup
from thread import start_new_thread

class ampel_state:
	def __init__(self):
		# modes
		self.off = 0
		self.on = 1
		self.flash = 2
		# state
		self.state = [self.off,self.off,self.off]

	def set_state(self, state):
		self.state = state

	def get_state(self):
		return self.state


def get_jenkins_state(url):
	req = urllib2.urlopen(url)
	res = req.read()

	xml = BeautifulSoup(res)
	xml_colors = xml.find_all("color")

	state = []
	for color in xml_colors:
		state.append(str(color.string))
	if state == []:
		raise Exception("Received empty state. There is no color tag, check URL manually: " + url)
	return state

# color: (0=red, 1=yellow, 2=blue/green)
# mode: (0=off, 1=on, 2=flash)
def extract_ampel_state(state):
	message = "Ampel is "
	state_out = [0,0,0]
	if "red_anime" in state:
		message += "flashing red"
		state_out[0] = 2
	elif "red" in state:
		message += "red"
		state_out[0] = 1
	else:
		message += "no red"
		state_out[0] = 0

	message += ", "
	if "yellow_anime" in state:
		message += "flashing yellow"
		state_out[1] = 2
	elif "yellow" in state:
		message += "yellow"
		state_out[1] = 1
	else:
		message += "no yellow"
		state_out[1] = 0

	message += " and "
	if "blue_anime" in state or "grey_anime" in state:
		message += "flashing green"
		state_out[2] = 2
	elif "blue" in state:
		message += "green"
		state_out[2] = 1
	else:
		message += "no green"
		state_out[2] = 0

	if state_out == [0, 0, 0]:
		message = "Error: invalid state. state = " + str(state)
		state_out = [2,2,2]
	return state_out, message

def run_ampel():
	global ampel
	on = [False, False, False]
	default_options = ["-c", "1"]
	if options.device != None:
		default_options += ["-d", str(options.device)]
	while True:
		state = ampel.get_state()
		for color in [0,1,2]:
			if state[color] == 2 and not on[color]:
				p = subprocess.Popen(["clewarecontrol"] + default_options + ["-as", str(color), "1"], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
				on[color] = True
			elif state[color] == 2 and on[color]:
				p = subprocess.Popen(["clewarecontrol"] + default_options + [ "-as", str(color), "0"], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
				on[color] = False
			else:
				p = subprocess.Popen(["clewarecontrol"] + default_options + [ "-as", str(color), str(state[color])], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
			p.wait()
		time.sleep(1)

if __name__ == "__main__":
	global ampel
	ampel = ampel_state()

	_usage = """%prog [options]
	type %prog -h for more info."""
	parser = OptionParser(usage=_usage, prog=os.path.basename(sys.argv[0]))
	parser.add_option("-u", "--url",
		dest="url",
		default="http://build.care-o-bot.org:8080/view/All",
		help="Jenkins server to monitor. Default: http://build.care-o-bot.org:8080")
	parser.add_option("-d", "--device",
		dest="device",
		default=None,
		help="use device with serial number 'x' for the next operations")
	(options, args) = parser.parse_args()
	if len(args) != 0:
		parser.error("no arguments supported.")

	start_new_thread(run_ampel,())

	while True:
		try:
			jenkins_state = get_jenkins_state(options.url + "/api/xml")
			ampel_state, message = extract_ampel_state(jenkins_state)
			print message + " for " + options.url
			ampel.set_state(ampel_state)
		except Exception, e:
			print e
			ampel.set_state([2, 2, 2])
			pass
		time.sleep(3)
