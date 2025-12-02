#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.testCaseUtils import testSuiteFromTCs
from tests.adt.collections.hashTable_test import HashTable_TC

adt_TCs = [
    HashTable_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*adt_TCs), printTopLongest=3)
