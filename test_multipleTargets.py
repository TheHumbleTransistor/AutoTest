from inspect import getargspec
import logging
import click
import time
import re
import random
from uuid import getnode as get_mac
from datetime import datetime
import os
from csvReport import CsvReport
import traceback
from AutoTest import DeviceUnderTest, Test, TestStep, testStep, TestResult, testResult

if __name__ == '__main__':
    dut1 = DeviceUnderTest()
    dut2 = DeviceUnderTest()

    test = Test(targets=[dut1, dut2], name="Demo Test", version="0.0.1", identifier=get_mac()%10000)

    @testResult("Serial Number")
    def serialNumber_result(value):
        if len(value) > 5:
            return True
        else:
            return False

    randomResult = TestResult("Random Result", units="randoUnits")

    scanIdx = 0
    @testStep(test, "Scan Barcode", results=(serialNumber_result, randomResult))
    def step(self, target):
        target = target
        global scanIdx
        input = self.prompt("Scan the DUT # {}\'s barcode".format(scanIdx))
        scanIdx += 1
        target.name = input
        target.resultValues[serialNumber_result] = input
        target.resultValues[randomResult] = random.random()

    randomResult2 = TestResult("Random Result 2", units="randoUnits")
    @testStep(test, "Connect to the DUT", results=(randomResult2), groupExecution = True)
    def step(self, targets):
        time.sleep(1)
        for idx, target in enumerate(targets):
            target.resultValues[randomResult2] = idx


    click.clear()
    while True:
        scanIdx = 0
        test.reset()
        test.run()
        click.echo("Next Test. ", nl=True)
        # click.pause(info=click.style("\nPress button to restart the test sequence...", blink=True))
