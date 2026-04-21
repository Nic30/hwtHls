import unittest
from hwtHls.pyUtils.mergeRanges import mergeInRange


class MergeInRangeTC(unittest.TestCase):

    def test_empty_list(self):
        self.assertEqual(mergeInRange([], 1, 3),
                         [(1, 3)])

    def test_no_overlap_after(self):
        self.assertEqual(mergeInRange([(1, 2)], 4, 6),
                          [(1, 2), (4, 6)])

    def test_overlap_directly_after(self):
        self.assertEqual(mergeInRange([(1, 2)], 3, 4),
                          [(1, 4)])

    def test_overlap_extend(self):
        self.assertEqual(mergeInRange([(1, 3)], 2, 5),
                          [(1, 5)])

    def test_fill_gap(self):
        self.assertEqual(mergeInRange([(1, 2), (4, 5)], 3, 3),
                         [(1, 5)])

    def test_fill_gap_overlapleft(self):
        self.assertEqual(mergeInRange([(1, 2), (4, 5)], 2, 3),
                         [(1, 5)])

    def test_fill_gap_overlaprigh(self):
        self.assertEqual(mergeInRange([(1, 2), (4, 5)], 3, 6),
                         [(1, 5)])

    def test_merge_multiple(self):
        self.assertEqual(mergeInRange([(1, 2), (4, 5), (7, 8)], 3, 6),
                          [(1, 8)])

    def test_completely_inside(self):
        self.assertEqual(mergeInRange([(1, 5)], 2, 4),
                          [(1, 5)])

    def test_extend_before(self):
        self.assertEqual(mergeInRange([(2, 3)], 1, 4),
                         [(1, 4)])

    def test_extend_after(self):
        self.assertEqual(mergeInRange([(1, 2)], 0, 3),
                          [(0, 3)])

    def test_new_before_all(self):
        self.assertEqual(mergeInRange([(2, 5), (7, 8)], 0, 1),
                          [(0, 5), (7, 8)])

    def test_new_after_all(self):
        self.assertEqual(mergeInRange([(1, 2), (4, 5)], 7, 9),
                          [(1, 2), (4, 5), (7, 9)])

    def test_invalid_range_begin_gt_end(self):
        with self.assertRaises(AssertionError):
            self.assertEqual(mergeInRange([(1, 3)], 5, 2),
                          [(1, 3)])


if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([MergeInRangeTC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(MergeInRangeTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
