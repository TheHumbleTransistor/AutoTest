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

class TestState:
    PENDING = "Pending"
    SUCCESS = "Pass"
    WARNING = "Warning"
    FAILURE = "Fail"
    ERROR = "ERROR"
    ABORTED = "Aborted"
    color = {ABORTED:"black", PENDING:"black", SUCCESS:"green", WARNING:"yellow", FAILURE:"red", ERROR:"red"}
    textColor = {ABORTED:"white", PENDING:"white", SUCCESS:"black", WARNING:"black", FAILURE:"black", ERROR:"black"}
    abortingStatuses = [FAILURE, ERROR]
    validStatuses = [PENDING, SUCCESS, WARNING, FAILURE, ERROR]

class DeviceUnderTest(object):
    def __init__(self, name=""):
        self.name = name
        self.resultValues = {}
        self._errors = {}
        self._trace = {}
        self._activeStep = 0

    def reset(self):
        self.resultValues = {}
        self._errors = {}
        self._trace = {}
        self._activeStep = 0

    def _state(self, test):
        outcome = TestState.SUCCESS
        for step_idx, step in enumerate(test.steps):
            stepOutcome = step._outcome(self)
            if stepOutcome in TestState.abortingStatuses:
                return stepOutcome
            if stepOutcome == TestState.PENDING:
                return stepOutcome
            if stepOutcome == TestState.WARNING:
                outcome = stepOutcome
        return outcome

    # Call this only when the test is incomplete
    def _failingStep(self, test):
        for step_idx, step in enumerate(test.steps):
            if step_idx >= self._activeStep:
                return None
            stepOutcome = step._outcome(self)
            if stepOutcome in TestState.abortingStatuses:
                return step
        # No failure
        return None


class Test:
    class State:
        PENDING = "Pending"
        COMPLETE = "Complete"
        ERROR = "ERROR"

    def __init__(self, targets=[DeviceUnderTest()], name=None, version=None, identifier=None, successStateOverride=None, reports=None):
        self.steps = []
        self.name = name
        self.version = version
        self.identifier = identifier
        self.targets = targets # devices under test
        if successStateOverride is not None:
            TestState.SUCCESS = successStateOverride
            TestState.color[TestState.SUCCESS] = 'white'

        if reports == None:
            self.reports = []
        elif type(reports) == CsvReport:
            self.reports = [reports]
        elif type(reports) == list:
            self.reports = reports
        else:
            raise ValueError("Reports needs to be a CsvReport or a list of them")

        for report in self.reports:
            report.headerRow = self.exportResultsHeader()

        self._activeTargets = []
        self.reset()

    def addStep(self, step):
        if step.identifier == None:
            step.identifier = len(self.steps)+1
        step._test = self
        self.steps.append(step)
        for report in self.reports:
            report.headerRow = self.exportResultsHeader()

    def reset(self):
        for target in self.targets:
            target.reset()
        self._activeTargets = self.targets[:]

    def state(self):
        targetStates = [target._state(self) for target in self.targets]
        if TestState.PENDING in targetStates:
            return Test.State.PENDING
        if all(targetState == TestState.ERROR for targetState in targetStates):
            return Test.State.ERROR
        return Test.State.COMPLETE

    def run(self):
        self.reset()
        for step in self.steps:
            if step.groupExecution:
                targetGroups = [self._activeTargets[:]] # run all targets at once
            else:
                targetGroups = [[target] for target in self._activeTargets[:]]  # run the test step for each individual target
            for targetGroup in targetGroups:
                try:
                    step._run(targetGroup)
                except Exception as e:
                    for target in targetGroup:
                        target._errors[step] = e
                        target._trace[step] = traceback.format_exc()

                for target in targetGroup:
                    target._activeStep += 1

                self._print()
                for target in self._activeTargets:
                    if step not in target._errors.keys():
                        continue
                    e = target._errors[step]
                    if step in target._trace.keys():
                        print(target._trace[step])
                    logging.error(e.__class__.__name__)
                    logging.error(e)

            # eliminate target if it's failed
            for target in self._activeTargets[:]:
                if target._state(self) != TestState.PENDING:
                    self._activeTargets.remove(target)

            if self.state() == Test.State.COMPLETE or self.state() == Test.State.ERROR:
                break

        # Write to the CSV
        for target in self.targets:
            for report in self.reports:
                report.writeEntry(self.exportResults(target))
        # TODO: Cleanup Step

    def _print(self):
        # returns a results row of data for a given test step and target
        def _stepRows(step, target, firstTarget):
            stepOutcome = step._outcome(target)
            rows=[]
            rows.append([])
            rows[0].append("%s" % step.identifier if firstTarget else "")
            if len(self.targets)>1:
                # If there's multiple DUTs, print a column with their names
                rows[0].append("%s" % target.name)
            rows[0].append(click.style("%s" % stepOutcome ,bg=TestState.color[stepOutcome], fg=TestState.textColor[stepOutcome]))
            rows[0].append("%s" % step.description if firstTarget else "")

            if stepOutcome == TestState.PENDING or stepOutcome == TestState.ABORTED:
                return rows
            stepOutcome = step._outcome(target)
            dispayedResults = list(filter(lambda result: result.displayed == True, step.results))
            for result_idx, result in enumerate(dispayedResults):
                # Check if this is not the first row
                if result_idx > 0:
                    if len(self.targets)>1:
                        # If there's multiple DUTs, there's an added name column
                        rows.append(["","","",""])
                    else:
                        rows.append(["","",""])
                if result in target.resultValues.keys():
                    value = target.resultValues[result]
                else:
                    value = None

                # Only print units if they have been defined
                unitsString = " (%s)"%result.units if result.units is not None else ""
                if isinstance(value, float):
                    if value == 0:
                        value = "0"
                    elif value >= 0.001:
                        value = "%.3f" % value
                    else:
                        value = "{:.3E}".format(value)
                elif isinstance(value, basestring) and len(value) > 50:
                    value = value[0:50] + "..."
                else:
                    value = value
                rows[-1].append("%s: %s%s" % (result.description, click.style("%s" % value, bold=True), unitsString))
            return rows


        # Format Test Results
        rows = [[]]
        rows[0].append("Step #")
        if len(self.targets)>1:
            rows[0].append("DUT")
        rows[0].append("Status")
        rows[0].append("Step")
        rows[0].append("Results".ljust(40))

        for step in self.steps:
            for target_idx, target in enumerate(self.targets):
                rows.extend(_stepRows(step, target, target_idx==0))
                stepOutcome = step._outcome(target)
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

        # Test Result Table
        for row_idx, row in enumerate(rows):
            rowString = ""
            for field in row:
                rowString += field
            if row_idx is 0:
                rowString = click.style(rowString, fg='black', bg='white', bold=True) # Color the Header Row
            click.echo(rowString)

        click.echo("\n") # New Line

        # Footer
        if len(self.targets) == 1:
            state = target._state(self)
            footerPadding = "".center(width) + '\n' + "".center(width) + '\n' + "".center(width)
            footer = (state).center(width)
            footer = footerPadding +'\n'+ footer +'\n'+ footerPadding
            click.echo(click.style(footer, fg='black', bg=TestState.color[state], bold=True))
        else:
            maxTargetNameLen = max([len(target.name) for target in self.targets])
            nameWidth = maxTargetNameLen + 10
            for target_idx, target in enumerate(self.targets):
                state = target._state(self)
                label = "{} result: ".format(click.style(target.name, bold=True))
                footerPadding = "".center(nameWidth) + click.style("".center(width-nameWidth), fg='black', bg=TestState.color[state], bold=True)
                footer =  label.center(nameWidth + lenOfAsciiEscapeChars(label)) + click.style(state.center(width-nameWidth), fg='black', bg=TestState.color[state], bold=True)
                footer = footerPadding +'\n'+ footer +'\n'+ footerPadding
                click.echo(footer)

        click.echo("\n") # New Line


        # Notes & Failure Description
        # for step in self.steps:
        #     if step.outcome and step.outcome.description:
        #         print step.outcome.description
        #         print '\n'

    def exportResultsHeader(self):
        row = []
        row.append("Test Name")
        row.append("Version")
        row.append("Station ID")
        row.append("Date (UTC)")
        row.append("Time (UTC)")
        row.append("Target Name")
        row.append("Pass/Fail")
        row.append("Failing Step")
        row.append("Failing Step Outcome")
        for step in self.steps:
            for result in step.results:
                units = "({})".format(result.units) if (result.units is not None) else ""
                row.append("{} {}".format(result.description, units))
        return row

    def exportResults(self, target):
        row = []
        row.append(self.name)
        row.append(self.version)
        row.append(self.identifier)

        date = datetime.now()
        row.append(date.strftime('%Y/%m/%d'))
        row.append(date.strftime('%H:%M:%S'))
        row.append(target.name)
        row.append(target._state(self))

        failingStep = target._failingStep(self)
        if failingStep is None:
            row.append("")
            row.append("")
        else:
            row.append("#%s - %s" % (failingStep.identifier, failingStep.description))
            error = ""
            if failingStep in target._errors.keys():
                error = str(target._errors[failingStep])
            row.append(error)


        for step in self.steps:
            for result in step.results:
                value = None
                if result in target.resultValues.keys():
                    value = target.resultValues[result]
                row.append("%s"%str(value))
        return row



@parametrizedDecorator
def testResult(func, description, units=None, displayed=True):
    result = TestResult(description=description, criteria=func, units=units, displayed=displayed)
    return result

class TestResult(object):
    class Outcome:
        PASS = "Pass"
        FAIL = "Fail"
        WARNING = "Warning"
    def __init__(self, description, criteria= lambda x : True if x != None else False , units=None, displayed=True):
        self.description = description
        self.units = units
        self.displayed = displayed
        if not callable(criteria):
            raise ValueError("criteria must be callable: a function or lambda")

        # Decorator
        def convertedOutcome(function):
            def wrapped(x):
                retval = function(x)
                if type(retval) == type(True):
                    return TestResult.Outcome.PASS if retval else TestResult.Outcome.FAIL
                elif type(retval) == TestResult.Outcome:
                    return retval
                else:
                    raise ValueError("Criteria function must return a valid outcome")
            return wrapped
        self.criteria = convertedOutcome(criteria)

@parametrizedDecorator
def testStep(func, test, description, results=(), identifier=None, groupExecution=False):
    step = TestStep(test, identifier, description, results, func, groupExecution)
    test.addStep(step)
    return step

class TestStep(object):
    def __init__(self, test, identifier, description, results, function, groupExecution=False):
        self._test = test
        self.identifier = identifier
        self.description = description
        # create a tuple if it's not one
        self.results = results if isinstance(results, tuple) else (results,)
        self._function = function
        self.groupExecution = groupExecution

    def prompt(self, message):
        return promptFunc(message)

    def _outcome(self, target):
        # Check if this test is aborted
        stepIdx = self._test.steps.index(self)
        if stepIdx > 0:
            previousStepState = self._test.steps[stepIdx-1]._outcome(target)
            if (previousStepState in TestState.abortingStatuses) or (previousStepState == TestState.ABORTED):
                return TestState.ABORTED

        # Check if this test is pending
        if target._activeStep <= self._test.steps.index(self):
            return TestState.PENDING

        # Check if an Error had been produced
        if self in target._errors.keys() and target._errors[self] != None:
                return TestState.ERROR

        # If any results are missing, populate them with None
        for result in self.results:
            if result not in target.resultValues.keys():
                target.resultValues[result] = None

        # Check if any results have failed
        for result in self.results:
            resultValue = target.resultValues[result]
            if result.criteria(resultValue) == TestState.FAILURE:
                return TestState.FAILURE

        # Check if any results have warnings
        for result in self.results:
            resultValue = target.resultValues[result]
            if result.criteria(resultValue) == TestState.WARNING:
                return TestState.WARNING

        return TestState.SUCCESS

    def _run(self, targets):
        if self.groupExecution:
            self._function(self, targets)
        else:
            self._function(self, targets[0])


#  Demo Test
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
    def step(self, targets):
        target = targets[0]
        global scanIdx
        input = self.prompt("Scan the DUT # {}\'s barcode".format(scanIdx))
        scanIdx += 1
        target.name = input
        target.resultValues[serialNumber_result] = input
        target.resultValues[randomResult] = random.random()

    randomResult2 = TestResult("Random Result 2", units="randoUnits")
    @testStep(test, "Connect to the DUT", results=(randomResult2), groupExecution = True)
    def step(self, targets):
        input = self.prompt("Type jibberish")
        for idx, target in enumerate(targets):
            target.resultValues[randomResult2] = idx


    click.clear()
    while True:
        test.reset()
        test.run()
        click.echo("Next Test. ", nl=True)
        # click.pause(info=click.style("\nPress button to restart the test sequence...", blink=True))
