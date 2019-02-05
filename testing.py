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

def parametrizedDecorator(dec):
    def layer(*args, **kwargs):
        def repl(f):
            return dec(f, *args, **kwargs)
        return repl
    return layer

# default function for printing input prompts to the terminal.
# override this by setting "promptFunc" to a new function
def __defaultPromptFunc(prompt):
    input = click.prompt(click.style(prompt, blink=False), default="")
    return input.rstrip("\n\r")

promptFunc = __defaultPromptFunc

def lenWithoutANSI(string):
    ansi_escape = re.compile("\033\[[0-9;]+m")
    return len(ansi_escape.sub('', string))

def lenOfAsciiEscapeChars(string):
    return len(string) - lenWithoutANSI(string)

def alignColumnWidth(rows, padding=4, ignoreAnsiEsc=True):
    # Calulate max column widths
    colWidths = []
    for i in range(len(max(rows,key=len))): # Iterate through columns of row with the most columns
        colWidths.append(0)
        for row in rows:
            if len(row) > i:
                cellSize = lenWithoutANSI(row[i]) if ignoreAnsiEsc else len(row[i])
                colWidths[i] = cellSize if cellSize > colWidths[i] else colWidths[i]
        colWidths[i] += padding

    for row in rows:
        for x,field in enumerate(row):
            ansiCharWidth = lenOfAsciiEscapeChars(field) if ignoreAnsiEsc else len(field)
            row[x] = field.ljust(colWidths[x] + ansiCharWidth)

    return sum(lenWithoutANSI(field) for field in rows[0])

# Enum
class TestStatus:
  PENDING = "Pending"
  SUCCESS = "Pass"
  WARNING = "Warning"
  FAILURE = "Fail"
  ERROR = "ERROR"
  color = {PENDING:"black", SUCCESS:"green", WARNING:"yellow", FAILURE:"red", ERROR:"red"}
  abortingStatuses = [FAILURE, ERROR]
  validStatuses = [PENDING, SUCCESS, WARNING, FAILURE, ERROR]

class Test:
    def __init__(self, testSteps, name=None, version=None, identifier=None, successStateOverride=None, reports=None):
        self.testSteps = testSteps # List
        self.name = name
        self.version = version
        self.identifier = identifier
        if successStateOverride is not None:
            TestStatus.SUCCESS = successStateOverride
            TestStatus.color[TestStatus.SUCCESS] = 'white'

        if reports == None:
            self.reports = []
        elif type(reports) == CsvReport:
            self.reports = [C]
        elif type(reports) == list:
            self.reports = reports
        else:
            raise ValueError("Reports needs to be a CsvReport or a list of them")

        for report in self.reports:
            report.headerRow = self.exportResultsHeader()

    def reset(self):
        for testStep in self.testSteps:
            testStep.reset()

    def state(self):
        stepStates = [testStep.state for testStep in self.testSteps]
        if TestStatus.ERROR in stepStates:
            # The test was aborted due to error
            return TestStatus.ERROR
        if TestStatus.FAILURE in stepStates:
            # The test was aborted due to failure
            return TestStatus.FAILURE
        if TestStatus.PENDING in stepStates:
            # Some test steps are still pending
            return TestStatus.PENDING
        if TestStatus.WARNING in stepStates:
            # One of the test steps resulted in a warning
            return TestStatus.WARNING
        # All steps were a success
        return TestStatus.SUCCESS

    def failingStep(self):
        # Return the first testStep state that isn't success
        for testStep in self.testSteps:
            if testStep.state in TestStatus.abortingStatuses:
                return testStep
        # No failure
        return None

    def run(self):
        for testStep in self.testSteps:
            testStep.collectInput()
            self.__print()
            try:
                testStep.run()
                self.__print()
            except Exception as e:
                self.__print()
                logging.error(e.__class__.__name__)
                logging.error(e)

            if testStep.state in TestStatus.abortingStatuses:
                break
        # Write to the CSV
        for report in self.reports:
            report.writeEntry(self.exportResults())
        # TODO: Cleanup Step

    def __stepRow(self, step):
        rows=[]
        rows.append([])
        rows[0].append("%s" % step.identifier)
        rows[0].append(click.style("%s" % step.state ,bg=TestStatus.color[step.state], fg='white' if step.state == TestStatus.PENDING else 'black'))
        rows[0].append("%s" % step.description)
        if step.state != TestStatus.PENDING:
            for result in step.results:
                if result.displayed is not True:
                    continue
                if len(rows[-1]) >= 4:
                    rows.append(["","",""])
                # Only print units if they have been defined
                unitsString = " (%s)"%result.units if result.units is not None else ""
                if isinstance(result.value, float):
                    if result.value == 0:
                        value = "0"
                    elif result.value >= 0.001:
                        value = "%.3f" % result.value
                    else:
                        value = "{:.3E}".format(result.value)
                elif isinstance(result.value, basestring) and len(result.value) > 50:
                    value = result.value[0:50] + "..."
                else:
                    value = result.value
                rows[-1].append("%s: %s%s" % (result.description, click.style("%s" % value, bold=True), unitsString))

        return rows

    def __print(self):
        # Format Test Results
        rows = []
        rows.append(["Step #", "Status", "Step", "Results".ljust(40)])
        for step in self.testSteps:
            rows.extend(self.__stepRow(step))
        width = alignColumnWidth(rows)

        # Clear screen
        click.clear()

        # Header
        version = str(self.version) if self.version is not None else ""
        if self.name is not None:
            headerline = "%s  %s" % ( str(self.name), click.style(version, bold=True))
            headerline = headerline.center(width + lenOfAsciiEscapeChars(headerline))
            click.echo( headerline )
        if self.identifier is not None:
            headerline = "Station ID:  %s" % click.style(str(self.identifier), bold=True)
            headerline = headerline.center(width + lenOfAsciiEscapeChars(headerline))
            click.echo( headerline )
        click.echo("") # New Line

        # Test Results
        for y,row in enumerate(rows):
            rowString = ""
            for field in row:
                rowString += field
            if y is 0:
                rowString = click.style(rowString, fg='black', bg='white', bold=True) # Color the Header Row
            click.echo(rowString)

        click.echo("") # New Line

        # Footer
        footerPadding = "".center(width) + '\n' + "".center(width) + '\n' + "".center(width)
        footer = (self.state()).center(width)
        footer = footerPadding +'\n'+ footer +'\n'+ footerPadding +'\n'
        click.echo(click.style(footer, fg='black', bg=TestStatus.color[self.state()], bold=True))


    def exportResultsHeader(self):
        row = []
        row.append("Test Name")
        row.append("Version")
        row.append("Station ID")
        row.append("Date (UTC)")
        row.append("Time (UTC)")
        row.append("Pass/Fail")
        row.append("Failing Step")
        for step in self.testSteps:
            for result in step.results:
                row.append("%s %s"%(result.description, "(%s)"%result.units if (result.units is not None) else ""))
        return row

    def exportResults(self):
        row = []
        row.append(self.name)
        row.append(self.version)
        row.append(self.identifier)

        date = datetime.now()
        row.append(date.strftime('%Y/%m/%d'))
        row.append(date.strftime('%H:%M:%S'))
        row.append(self.state())

        failingStep = self.failingStep()
        if failingStep is None:
            row.append("")
        else:
            row.append("#%s - %s" % (failingStep.identifier, failingStep.description))

        for step in self.testSteps:
            for result in step.results:
                row.append("%s"%str(result.value))
        return row

class TestResult:
    def __init__(self, description, units=None, displayed=True):
        self.description = description
        self.units = units
        self.displayed = displayed
        self.value = None

@parametrizedDecorator
def testStep(func, identifier, description, results=(), inputPrompt=None):
    return TestStep(identifier, description, results, func, inputPrompt)

class TestStep:
    def __init__(self, identifier, description, results, function, inputPrompt):
        self.inputPrompt = inputPrompt
        self.identifier = identifier
        self.description = description
        # create a tuple if it's not one
        self.results = results if isinstance(results, tuple) else (results,)
        self.reset()

        # Decorator
        def optionalInput(f):
            def wrapped(input=None):
                numberOfArgs = len(getargspec(f)[0])
                if numberOfArgs is 1:
                    return f(input)
                return f()
            return wrapped
        self.function = optionalInput(function)

    def reset(self):
        self.state = TestStatus.PENDING
        self.input = None
        for result in self.results:
            result.value = None

    def collectInput(self):
        # Input Prompt
        if self.inputPrompt is not None:
            # getargspec returns a tuple. The first element is the argument names.
            self.input = promptFunc(self.inputPrompt)

    def run(self):
        # Call test function
        try:
            returnedValue = self.function(self.input)
            status, results = (returnedValue, None) if isinstance(returnedValue, bool) else returnedValue
            results = results if results is not None else ()
            results = results if isinstance(results, tuple) else (results,)
            for i,result in enumerate(results):
                self.results[i].value = result
            # Test complete
            if type(status) == type(True):
                self.state = TestStatus.SUCCESS if (status == True) else TestStatus.FAILURE
            elif status in TestStatus.validStatuses :
                self.state = status
            else:
                raise ValueError("Invalid test status returned")
        except:
            self.state = TestStatus.ERROR
            raise

#  Demo Test
if __name__ == '__main__':
    steps = []

    @testStep(1, "Scan Barcode", TestResult("Serial Number"), "Scan the DUT's barcode")
    def step(input):
        return (True, input)
    steps.append(step)

    @testStep(2, "Connect to the DUT")
    def step():
        time.sleep(1)
        return (True, ())
    steps.append(step)

    @testStep(3, "Programming the DUT")
    def step():
        time.sleep(2)
        return (True, ())
    steps.append(step)

    @testStep(4, "Calibration", TestResult("Calibration Coefficient"))
    def step():
        time.sleep(2)
        randomInt = random.randrange(0,100)
        return (randomInt > 20, random.randrange(0,20000)/10.0)
    steps.append(step)

    @testStep(5, "Measuring Power Consumption", TestResult("Current Consumption", "uA"))
    def step():
        time.sleep(2)
        randomInt = random.randrange(0,100)
        returnCode = True if (randomInt > 40) else TestStatus.WARNING
        return (returnCode, random.randrange(0,100000)/100.0)
    steps.append(step)

    @testStep(5, "Setting NV Parameters")
    def step():
        time.sleep(1)
        return (True, ())
    steps.append(step)

    test = Test(steps, "Demo Test", version="0.0.1", identifier=get_mac()%10000)

    csvHeader = test.exportResultsHeader()

    click.clear()
    while True:
        test.reset()
        test.run()
        click.echo("Next Test. ", nl=False)
    # click.pause(info=click.style("\nPress button to restart the test sequence...", blink=True))
