from typing import Generator, Type, Optional

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructVld, HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtLib.types.ctypes import uint64_t


# class PipelinedMultiplier_OPT_GOAL(Enum):
#    THROUGHPUT_LATENCY = 0
#    THROUGHPUT_AREA = 1
#    AREA = 2
def iter_antidiagonal_item_indexes(width:int, height:int) -> Generator[list[tuple[int, int]], None, None]:
    # left side of antidiagonal and antidiagonal
    for col in range(width):
        startcol = col
        startrow = 0
        antidiagonal = []
        while (startcol >= 0 and
               startrow < height):
            antidiagonal.append((startrow, startcol))
            startcol -= 1
            startrow += 1

        yield antidiagonal

    # right side of antidiagonal
    for row in range(1, height):
        startrow = row
        startcol = width - 1
        antidiagonal = []
        while (startrow < height and
               startcol >= 0):
            antidiagonal.append((startrow, startcol))
            startcol -= 1
            startrow += 1

        yield antidiagonal


class PipelinedMultiplier(_BaseALU1HwModule):
    """
    :note: Realization of child multiplers is selected by ComponentGenerator installed in Platform
    
    https://trmm.net/Multiplier/
    https://tomverbeure.github.io/rtl/2018/08/12/Multipliers.html
    https://github.com/temelmertcan/multgen
    https://discourse.llvm.org/t/why-llvm-ir-does-not-distinguish-signed-and-unsigned-multiplication/66113/2
    SMUL_LOHI, UMUL_LOHI,
    G_UMULH, G_SMULH
    """

    def hwConfig(self) -> None:
        self.CLK_FREQ: int = HwParam(int(100e6))
        self.T: HBits = HwParam(uint64_t)
        self.T_LHS: Optional[HBits] = HwParam(None)
        self.T_RHS: Optional[HBits] = HwParam(None)
        self.UNROLL_FACTOR: int = HwParam(1)
        self.MAIN_FN_META: int = HwParam(None)
        self.IN_CHANNEL_TYPE: Type[HwIOStructVld] = HwParam(HwIOStructVld)
        self.OUT_CHANNEL_TYPE: Type[HwIOStructRdVld] = HwParam(HwIOStructRdVld)
        self.MAX_MUL_LHS_WIDTH: int = HwParam(8)
        self.MAX_MUL_RHS_WIDTH: int = HwParam(8)

    def hwDeclr(self) -> None:
        addClkRstn(self)
        t = self.T
        assert t is not None, self
        self._addDataInDataOut(HStruct(
            (t if self.T_LHS is None else self.T_LHS, "a"),
            (t if self.T_RHS is None else self.T_RHS, "b")
            ),
            t)

