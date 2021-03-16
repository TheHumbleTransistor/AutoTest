import sys
import os
import shutil
import subprocess
import time
import csv, io
import unittest
from types import *
import binascii

# https://nitratine.net/blog/post/asymmetric-encryption-and-decryption-in-python/
# https://nitratine.net/blog/post/encryption-and-decryption-in-python/
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.fernet import Fernet


DRIVE_LOCATION = ""
LOCAL_BACKUP_LOCATION = ""
HEADER_ROW = []
_testName = ""
_mountDrive = True

class CsvReport:
    def __init__(self, dir, filename, headerRow=[], autoMount=False, encryptionKeyPath=None):
        self.dir = dir
        self.headerRow = headerRow
        self.filename = filename
        self.autoMount = autoMount
        self.encryptionKeyPath = encryptionKeyPath
        self.encryptionKey = None
        if self.encryptionKeyPath:
            with open(encryptionKeyPath, "rb") as key_file:
                self.encryptionKey = serialization.load_pem_public_key(
                    key_file.read(),
                    backend=default_backend()
                )

    @staticmethod
    def _csvRowToBinaryData(row):
        s = io.StringIO()
        csv.writer(s, lineterminator=os.linesep).writerow(row)
        s.seek(0)
        return s.getvalue().encode()

    @staticmethod
    def _encryptData(binaryData, key_rsa):
        # To encrypt lots of data, we need to encrypt with a symmetrical scheme,
        # then encrypt and store that symmetrical key using an asymmetrical scheme.

        # generate a session key that's a symmetric key used to encrypt large messages.
        sessionKey = Fernet.generate_key()
        # encrypt the data
        encryptedData = Fernet(sessionKey).encrypt(binaryData)
        # asymmetrically encrypt the session key
        encryptedSessionKey = key_rsa.encrypt(
            sessionKey,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return (encryptedSessionKey, encryptedData)

    @staticmethod
    def _hexEncodeData(binaryData):
        hexEncodedBinaryData = binaryData.hex()
        return hexEncodedBinaryData

    def writeEntry(self, row):
        #date = time.strftime("%Y-%m-%d")
        if self.autoMount:
            subprocess.check_output(['mount', self.dir])

        filename = self.filename() if isinstance(self.filename, LambdaType) else self.filename
        filePath = self.dir + '/' + filename + ".csv"
        firstEntry = (os.path.exists(filePath) == False)

        # queue up the rows that should be written to the file
        rowsToWrite = [row]
        if firstEntry:
            rowsToWrite.insert(0, self.headerRow)

        # write the rows
        for r in rowsToWrite:
            accessMode = 'w' if firstEntry else 'a'
            firstEntry = False

            # encrypt the data if necessary
            rowOutput = r
            if self.encryptionKey:
                rowOutput = tuple(map(CsvReport._hexEncodeData, CsvReport._encryptData(CsvReport._csvRowToBinaryData(rowOutput), self.encryptionKey)))

            # write the row to the file
            with open(filePath, accessMode) as csvfile:
                writer = csv.writer(csvfile, lineterminator=os.linesep)
                writer.writerow(rowOutput)

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
                contents += line

        expectedContents = "Column 1,Column 2,Column 3{0}Result 1,Result 2,Result 3{0}Result 1,Result 2,Result 3{0}".format(os.linesep)
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
                contents += line

        expectedContents = "Column 1,Column 2,Column 3{0}Result 1,Result 2,Result 3{0}".format(os.linesep)
        self.assertEqual(contents, expectedContents)


    def test_encryption(self):
        publicKeyFilename = 'public_key.pem'
        publicKeyFilepath = os.path.join(TestCsvReport.directory, publicKeyFilename)

        # Generating asymmetric keys (RSA)
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        with open(publicKeyFilepath, 'wb') as f:
            f.write(pem)


        report = CsvReport(TestCsvReport.directory, "encryptedReport", headerRow=["Column 1", "Column 2", "Column 3"], encryptionKeyPath=publicKeyFilepath)
        filepath = report.writeEntry(["Result 1", "Result 2", "Result 3",])

        def decryptData(key, sessionKey_encrypted, data_encrypted):
            # decrypt the symmetric session key using an asymmetric key (RSA)
            sessionKey = key.decrypt(
                sessionKey_encrypted,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )

            # Decrypt the main payload
            f = Fernet(sessionKey)
            data = f.decrypt(data_encrypted)
            return data

        contents = ""
        # read the file back and try and decrypt
        with open(filepath) as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                # convert from hex-encoded data to binary
                sessionKey_encrypted = binascii.unhexlify(row[0])
                data_encrypted =  binascii.unhexlify(row[1])
                data = decryptData(private_key, sessionKey_encrypted, data_encrypted)
                data = data.decode('ascii')
                contents += data

        expectedContents = "Column 1,Column 2,Column 3{0}Result 1,Result 2,Result 3{0}".format(os.linesep)
        self.assertEqual(contents, expectedContents)


if __name__ == '__main__':
    unittest.main()
