from unittest import TestLoader, TestSuite


def testSuiteFromTCs(*tcs):
    for tc in tcs:
        tc._multiprocess_can_split_ = True
    loader = TestLoader()
    loadedTcs = [loader.loadTestsFromTestCase(tc) for tc in tcs]
    suite = TestSuite(loadedTcs)
    return suite
