#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.testCaseUtils import testSuiteFromTCs
from tests.threads.ThreadExtractPass_test import ThreadExtractPassTC
from tests.threads.ThreadHwtComponent_test import ThreadHwtComponentReg_rtl_TC
from tests.threads.channelThreadCommunication_test import ChannelThreadCommunicationTC


threads_TCs = [
    ThreadHwtComponentReg_rtl_TC,
    ChannelThreadCommunicationTC,
    ThreadExtractPassTC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*threads_TCs), printTopLongest=3)
