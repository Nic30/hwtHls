#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.crypto.md5_test import Md5_TC
from tests.testCaseUtils import testSuiteFromTCs


crypto_TCs = [
    Md5_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*crypto_TCs), printTopLongest=3)

