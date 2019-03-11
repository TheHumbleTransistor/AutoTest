import sys
import os
import shutil
import subprocess
import time
import csv
import unittest
from types import *


DRIVE_LOCATION = ""
LOCAL_BACKUP_LOCATION = ""
HEADER_ROW = []
_testName = ""
_mountDrive = True

class CsvReport:
    def __init__(self, dir, filename, headerRow=[], autoMount=False):
        self.dir = dir
        self.headerRow = headerRow
        self.filename = filename
        self.autoMount = autoMount



    def writeEntry(self, row):
        #date = time.strftime("%Y-%m-%d")
        if self.autoMount:
            subprocess.check_output(['mount', self.dir])

        filename = self.filename() if isinstance(self.filename, LambdaType) else self.filename
        filePath = self.dir + '/' + filename + ".csv"
        firstEntry = (os.path.exists(filePath) == False)

        attribute = 'w' if firstEntry else 'a'
        with open(filePath, attribute) as csvfile:
            writer = csv.writer(csvfile)
            if firstEntry:
                writer.writerow(self.headerRow)
            writer.writerow(row)

        if self.autoMount:
            subprocess.check_output(['umount', self.dir])

        return filePath

class TestCsvReport(unittest.TestCase):
    directory = "tempDir"
    def setUp(self):
        if os.path.exists(TestCsvReport.directory):
            shutil.rmtree(TestCsvReport.directory)
        os.mkdir(TestCsvReport.directory)

    def tearDown(self):
        for root, dirs, files in os.walk(TestCsvReport.directory):
            for f in files:
                os.unlink(os.path.join(root, f))
        os.rmdir(TestCsvReport.directory)

    def test_basic(self):
        expectedFilepath = TestCsvReport.directory + "/report.csv"
        self.assertFalse(os.path.exists(expectedFilepath))
        report = CsvReport(TestCsvReport.directory, "report", headerRow=["Column 1", "Column 2", "Column 3"])
        filepath = report.writeEntry(["Result 1", "Result 2", "Result 3",])
        filepath = report.writeEntry(["Result 1", "Result 2", "Result 3",])
        self.assertEqual(filepath, expectedFilepath)
        self.assertTrue(os.path.exists(filepath))
        self.assertTrue(os.path.isfile(filepath))
        contents = ""
        with open(filepath) as f:
            for line in f.readlines():
                contents += line + '\n'

        expectedContents = "Column 1,Column 2,Column 3\r\n\nResult 1,Result 2,Result 3\r\n\nResult 1,Result 2,Result 3\r\n\n"
        self.assertEqual(contents, expectedContents)

    def test_lambdas(self):
        date = lambda : "report_"+time.strftime("%Y-%m-%d")
        report = CsvReport(TestCsvReport.directory, date, headerRow=["Column 1", "Column 2", "Column 3"])
        expectedFilepath = TestCsvReport.directory + "/"+date()+".csv"
        self.assertFalse(os.path.exists(expectedFilepath))
        filepath = report.writeEntry(["Result 1", "Result 2", "Result 3",])
        self.assertEqual(filepath, expectedFilepath)
        self.assertTrue(os.path.exists(filepath))
        self.assertTrue(os.path.isfile(filepath))
        contents = ""
        with open(filepath) as f:
            for line in f.readlines():
                contents += line + '\n'

        expectedContents = "Column 1,Column 2,Column 3\r\n\nResult 1,Result 2,Result 3\r\n\n"
        self.assertEqual(contents, expectedContents)

if __name__ == '__main__':
    unittest.main()
