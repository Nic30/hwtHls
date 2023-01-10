from hwtHls.netlist.dagQueries.dagQueries import ReachabilityIndexTOLButterfly

import unittest


class ReachabilityIndexTOLButterfly_TC(unittest.TestCase):

    def testLinear(self):
        db = ReachabilityIndexTOLButterfly()
        db.loadGraph(3, [(0, 1), (1, 2)])
        # db.computeIndexR1()
        db.computeIndex(True)
        db.computeBacklink()
        db.computeOrder()
        
        self.assertTrue(db.isReachable(0, 2))
        self.assertTrue(db.isReachable(0, 1))
        self.assertTrue(db.isReachable(2, 2))
        self.assertTrue(db.isReachable(2, 0))
        self.assertTrue(db.isReachable(2, 1))

    def testLinear_deleteNode(self):
        db = ReachabilityIndexTOLButterfly()
        db.loadGraph(3, [(0, 1), (1, 2)])

        db.computeIndex(True)
        db.computeBacklink()
        db.computeOrder()
        db.deleteNode(1)
        
        self.assertFalse(db.isReachable(0, 2))
        self.assertTrue(db.isReachable(2, 2))
        self.assertFalse(db.isReachable(2, 0))

    def testLinear_deleteNode_addNode(self):
        db = ReachabilityIndexTOLButterfly()
        db.loadGraph(3, [(0, 1), (1, 2)])

        db.computeIndex(True)
        db.computeBacklink()
        db.computeOrder()
        db.deleteNode(1)
        
        db.addNode(3, [0, ], [2], True)
        self.assertTrue(db.isReachable(0, 2))
        self.assertTrue(db.isReachable(0, 3))
        self.assertTrue(db.isReachable(2, 2))
        self.assertTrue(db.isReachable(2, 0))
        self.assertTrue(db.isReachable(2, 3))


if __name__ == '__main__':
    unittest.main()

