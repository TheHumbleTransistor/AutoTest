from inspect import getargspec
import logging
import click
import time
import re
import random
from uuid import getnode as get_mac
from datetime import datetime
import os
import traceback
from AutoTest import DeviceUnderTest, Test, TestStep, testStep, TestResult, testResult, CsvReport

report = CsvReport(os.path.dirname(os.path.realpath(__file__)) + "/", lambda:"EXAMPLE_REPORT_"+time.strftime("%Y-%m-%d"))

if __name__ == '__main__':
    dut = DeviceUnderTest()

    test = Test(targets=[dut], name="Example Test", version="1.0.0", identifier=get_mac()%10000, reports=[report])

    @testResult("Serial Number")
    def serialNumber_result(value):
        if len(value) > 5:
            return True
        else:
            return False

    @testStep(test, "Scan Barcode", results=(serialNumber_result))
    def step(self, target):
        input = self.prompt("Scan the DUT\'s barcode".format(scanIdx))
        target.name = input
        target.resultValues[serialNumber_result] = input


    result_batteryVoltage = TestResult("Battery Voltage", units="volts")
    @testStep(test, "Apply Battery Power", results=(result_batteryVoltage))
    def step(self, target):
        time.sleep(.9)
        target.resultValues[result_batteryVoltage] = 3.703

    result_vccVoltage = TestResult("VCC Voltage", units="volts")
    @testStep(test, "Measure VCC", results=(result_vccVoltage))
    def step(self, target):
        time.sleep(.4)
        target.resultValues[result_vccVoltage] = 3.312

    result_hexFile = TestResult("Firmware", units="volts")
    @testStep(test, "Load Firmware", results=(result_hexFile))
    def step(self, target):
        with click.progressbar(range(20), label="Programming Firmware") as bar:
            for step in bar:
                time.sleep(.1)
        target.resultValues[result_hexFile] = "customerFirmware.hex"

    result_currentConsumption = TestResult("Current Consumption", units="microAmps")
    @testStep(test, "Measure Current Consumption", results=(result_currentConsumption))
    def step(self, target):
        time.sleep(.4)
        target.resultValues[result_currentConsumption] = 721.18

    result_locale = TestResult("Locale")
    result_brightness = TestResult("Brightness", units="%")
    @testStep(test, "Configure Settings", results=(result_locale, result_brightness))
    def step(self, target):
        time.sleep(.6)
        target.resultValues[result_locale] = "English (UK)"
        target.resultValues[result_brightness] = 80

    @testStep(test, "Enter \"Ship Mode\"")
    def step(self, target):
        time.sleep(.5)

    result_shipModeCurrentConsumption = TestResult("Ship Mode Current", units="microAmps")
    @testStep(test, "Measure Current Consumption", results=(result_shipModeCurrentConsumption))
    def step(self, target):
        time.sleep(.4)
        target.resultValues[result_shipModeCurrentConsumption] = 11.27


    click.clear()
    while True:
        scanIdx = 0
        test.reset()
        test.run()
        click.echo("Next Test. ", nl=True)
        # click.pause(info=click.style("\nPress button to restart the test sequence...", blink=True))
