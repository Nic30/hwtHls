from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwIOs.agents.bramPort import storeToRamMaskedByIndex
from hwtLib.abstract.sim_ram import SimRam
from pyMathBitPrecise.bit_utils import ValidityError, byte_mask_to_bit_mask


class BramSimRam(SimRam):

    def __init__(self, cellSize:int, itemCnt:int, hasWeMask=False, parent=None):
        SimRam.__init__(self, cellSize, parent=parent)
        self.itemCnt = itemCnt
        self.hasWeMask = hasWeMask

    def getWriteWordWidth(self) -> int:
        return self.cellSize + (self.cellSize // 8 if self.hasWeMask else 0)

    def write(self, addr: HBitsConst, dataAndMask: HBitsConst):
        try:
            addr = int(addr)
        except ValidityError:
            # write with invalid address potentially invalidates everything
            self.data.clear()
            return

        if self.hasWeMask:
            assert dataAndMask._dtype.bit_length() == (self.cellSize + self.cellSize // 8)
            data = dataAndMask[self.cellSize:]
            byteMask = dataAndMask[:self.cellSize]
            # print("BramSimRam", addr, byteMask, data)
            isInHBits = True
            bitmask = byte_mask_to_bit_mask(byteMask, 8)
            storeToRamMaskedByIndex(self.data, addr, data, bitmask, isInHBits)
        else:
            data = dataAndMask
            assert data._dtype.bit_length() == self.cellSize, (data._dtype.bit_length(), self.cellSize)
            self.data[addr] = data

