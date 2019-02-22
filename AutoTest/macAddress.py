import subprocess
import os
import re
import platform
import unittest

# Gets a unique Mac Address identifier for a specified network interface
def get_mac(interface):
    commands = ("ifconfig %s" % interface).split(' ')
    output = subprocess.check_output(commands)
    operatingSystem = platform.system()
    if operatingSystem == "Linux":
        searchPrefix = "HWaddr "
    elif operatingSystem == "Darwin":
        searchPrefix = "ether "
    m = re.search(searchPrefix+'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', output)
    if m is None:
        raise Exception('Couldn\'t find this mac address')
    address = m.group(0).replace(searchPrefix,'')

    address = address.replace('"', '').replace(':', '').rstrip()
    macInt = int(address,16)
    return macInt

if __name__ == '__main__':
    # unittest.main()
    print get_mac("en0")
    # print get_mac("wlan0")
