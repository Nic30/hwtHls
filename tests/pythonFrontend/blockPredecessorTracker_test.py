
import unittest
from hwtHls.ssa.translation.fromPython.blockPredecessorTracker import BlockPredecessorTracker
from networkx.classes.digraph import DiGraph


def gen3LinearBlocks():
    cfg = DiGraph()
    for i in range(3):
        cfg.add_node(i)
    cfg.add_edge(0, 1)
    cfg.add_edge(1, 2)
    return cfg


class BlockPredecessorTrackerTC(unittest.TestCase):

    def test3LinearBlocks(self):
        bpt = BlockPredecessorTracker(gen3LinearBlocks())
        self.assertTrue(bpt.addGenerated(0))
        self.assertFalse(bpt.addGenerated(2))
        self.assertFalse(bpt.addGenerated(1))


if __name__ == '__main__':
    unittest.main()
