from itertools import islice
from typing import List, Dict


class HlsSchedulerResourceUseList(List[Dict[object, int]]):
    """
    A list of dictionaries with resource usage info which automatically extends itself on both sides.
    The index in this list is an index of the clock period.
    This index can be negative as circuit may be temporally scheduled to negative times (e.g. in ALAP).

    :note: This is used for list scheduling greedy algorithm to track how many resources were used in individual clock cycle windows.
    """

    def __init__(self):
        list.__init__(self)
        self.clkOffset = 0  # always >= 0, used to allow negative indexes on self

    def getUseCount(self, resourceType, clkI: int) -> int:
        assert resourceType is not None
        return self[self.clkOffset + clkI].get(resourceType, 0)

    def addUse(self, resourceType, clkI: int):
        # print("add use ", resourceType, clkI, end="")
        assert resourceType is not None
        cur = self[clkI]  # offset applied in __getitem__
        cur[resourceType] = cur.get(resourceType, 0) + 1
        # print(" v:", cur[resourceType])

    def removeUse(self, resourceType, clkI: int):
        # print("rm use", resourceType, clkI)
        assert resourceType is not None
        i = self.clkOffset + clkI
        assert i >= 0, (i, clkI, resourceType, "Trying to remove from clock where no resource is used")
        cur = list.__getitem__(self, i)
        curCnt = cur[resourceType]
        if curCnt == 1:
            cur.pop(resourceType)
        else:
            assert curCnt > 0, (clkI, resourceType, "Resource must be used in order to remove the use")
            cur[resourceType] = curCnt - 1

    def moveUse(self, resourceType, fromClkI: int, toClkI: int):
        assert resourceType is not None
        assert fromClkI != toClkI, (resourceType, "if this is the case this function should not be called at all", fromClkI)
        # print("mv use ", resourceType, fromClkI, toClkI)
        # accessing directly to raise index error if there is not yet any use in this clk
        _fromClkI = self.clkOffset + fromClkI
        assert _fromClkI >= 0 and _fromClkI < len(self), ("Moving from usage from clock slot which is not present",
                                                          resourceType,
                                                          fromClkI, toClkI,
                                                          " curRange:", self.clkOffset, self.clkOffset + len(self))
        cur = list.__getitem__(self, _fromClkI)
        try:
            curCnt = cur[resourceType]
        except KeyError:
            raise AssertionError("Trying to move usage which is not present", resourceType, fromClkI, toClkI)

        assert curCnt > 0, (resourceType, curCnt)
        if curCnt == 1:
            cur.pop(resourceType)
        else:
            cur[resourceType] = curCnt - 1

        to = self[toClkI]
        toCnt = to.get(resourceType, 0)
        to[resourceType] = toCnt + 1

    def findFirstClkISatisfyingLimit(self, resourceType, beginClkI: int, limit: int) -> int:
        """
        Find the first clock period index where limit on resource usage is satisfied.
        """
        assert resourceType is not None
        assert limit > 0, limit
        clkI = beginClkI
        while True:
            res = self[clkI]  # offset applied in __getitem__
            if res.get(resourceType, 0) < limit:
                return clkI
            clkI += 1

    def findFirstClkISatisfyingLimitEndToStart(self, resourceType, endClkI: int, limit: int) -> int:
        """
        :attention: Limit for first clk period where search is increased because it is expected that the requested
            resource is already allocated there.
        """
        assert resourceType is not None
        assert limit > 0, limit
        clkI = endClkI
        while True:
            res = self[clkI]  # offset applied in __getitem__
            if res.get(resourceType, 0) < (limit + 1 if clkI == endClkI else limit):
                return clkI
            clkI -= 1

    def normalizeOffsetTo0(self):
        off = self.clkOffset
        if off > 0:
            # cut newClkI0 items from start
            for i, items in enumerate(islice(self, 0, off)):
                assert not items, ("When removing time slot in resources it must be empty, clk:", i - off, items)
            del self[0:off]
            self.clkOffset = 0
        else:
            assert off == 0

    def __getitem__(self, i: int):
        _i = i
        i += self.clkOffset
        if i < 0:
            # prepend empty slots
            self[:0] = [{} for _ in range(-i)]
            self.clkOffset += -i
            assert self.clkOffset >= 0, self.clkOffset
            i = 0

        try:
            return list.__getitem__(self, i)
        except IndexError:
            assert i >= 0, i
            # append empty slots
            for _ in range(i + 1 - len(self)):
                self.append({})
            return self[_i]
