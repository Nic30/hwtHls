import os
from pathlib import Path
import sqlite3
from typing import Union, Callable, Optional

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps
from hwt.serializer.resourceAnalyzer.resourceTypes import RtlResourceType, \
    ResourceFF, ResourceRAM
from hwtHls.code import OP_ASHR, OP_LSHR, OP_SHL, OP_ROL, OP_ROR, OP_FSHL, \
    OP_FSHR
from hwtHls.platform.debugBundle import HlsDebugBundle, DebugId
from hwtHls.platform.debugBundleTypes import LlvmCliArgTuple
from hwtHls.platform.interpolations import Spline, \
    ResourceSplineBundleArgCntDependent, ResourceSplineBundleBitwidthDependent
from hwtHls.platform.xilinx.abstract import AbstractXilinxPlatform


# Vitis platform.db is passes to Vitis LLVM trough the hls-platform-db-name CLI option
# * https://github.com/Xilinx/hls-llvm-project/blob/a152ee63edaf75f0a4aa3312bd8d6dcf5441dffd/llvm/tools/opt/opt.cpp#L285
# This option is then used to xilinx platform object
# * https://github.com/Xilinx/hls-llvm-project/blob/a152ee63edaf75f0a4aa3312bd8d6dcf5441dffd/llvm/include/llvm/Support/XILINXFPGAPlatformBasic.h
# https://github.com/Xilinx/hls-llvm-project/blob/a152ee63edaf75f0a4aa3312bd8d6dcf5441dffd/llvm/lib/Support/XilinxPlat/CoreQuerier.cpp#L711
# The platform contains QuerierFactory which contains several query types
# * https://github.com/Xilinx/hls-llvm-project/blob/a152ee63edaf75f0a4aa3312bd8d6dcf5441dffd/llvm/lib/Support/XilinxPlat/CoreQuerier.cpp#L124
# The query is selected based on core type in CoreQuerier* QuerierFactory::getCoreQuerier(CoreInst* core)
# * https://github.com/Xilinx/hls-llvm-project/blob/a152ee63edaf75f0a4aa3312bd8d6dcf5441dffd/llvm/lib/Support/XilinxPlat/CoreQuerier.cpp#L448
# * although it seems that each table has same format of records it is not the case as there
#   are many exceptions as defined in QuerierFactory::getCoreQuerier()
class HlsPlatformFromVitisDB(AbstractXilinxPlatform):
    """
    :ivar _targetName: name of target in database e.g. artix7_slow, versal_fast (corresponds to a prefix in table name) 
    """
    _DEFAULT_VITIS_DIR_LINUX = "/opt/Xilinx/Vitis/"

    @classmethod
    def _getVitisHome(cls):
        try:
            vivadoHomes = os.listdir(cls._DEFAULT_VITIS_DIR_LINUX)
        except Exception:
            raise Exception("Can not find AMD/Xilinx Vitis installation automatically, you have to specify it manually")

        if len(vivadoHomes) != 1:
            raise Exception('Can not resolve default Vivado available are %s' % (str(vivadoHomes)))

        return os.path.join(cls._DEFAULT_VITIS_DIR_LINUX, vivadoHomes[0])

    def __init__(self, targetName:str, debugDir:Optional[Union[str, Path]]=HlsDebugBundle.DEFAULT_DEBUG_DIR,
                 debugFilter: Optional[set[DebugId]]=HlsDebugBundle.DEFAULT,
                 llvmCliArgs:list[LlvmCliArgTuple]=[],
                 vitisHome:Optional[str]=None,
                 vitisDbFile:Optional[str]=None):
        self._targetName = targetName
        if vitisDbFile:
            vitisDbFile = Path(vitisDbFile)
        else:
            if vitisHome:
                vitisHome = Path(vitisHome)
            else:
                vitisHome = self._getVitisHome()
            vitisDbFile = vitisHome / Path("common/technology/xilinx/common/platform.db")

        self._vitisDbFile = vitisDbFile

        self._DSP_MUL_GEOMETRIES = []  # :note: will be loaded in _init_coefs()

        super().__init__(debugDir=debugDir, debugFilter=debugFilter, llvmCliArgs=llvmCliArgs)

    def _getFromDBArithmeticDelay(self, dbCursor:sqlite3.Cursor, coreName: str):
        queryStr = \
        f'SELECT OPERANDS, DELAY0 FROM {self._targetName:s}_Arithmetic'\
        ' WHERE CORE_NAME == ? AND LATENCY == 0'\
        ' ORDER BY OPERANDS ASC;'
        operandWidths = []
        delays = []
        for (opWidth, delay) in dbCursor.execute(queryStr, (coreName,)):
            operandWidths.append(int(opWidth))
            delays.append(float(delay) * 10 ** -9)

        assert delays, queryStr
        return ResourceSplineBundleBitwidthDependent(Spline(operandWidths, delays))

    # def _getFromDBRegsliceDelay(self, dbCursor:sqlite3.Cursor):
    #    operandWidths = []
    #    delays = []
    #    for (opWidth, delay) in dbCursor.execute(
    #        'SELECT BITWIDTH, DELAY0, DELAY2 FROM artix7_fast_RegSlice '
    #        'WHERE LATENCY == 1'
    #        ' ORDER BY BITWIDTH ASC;'):
    #        operandWidths.append(int(opWidth))
    #        delays.append(float(delay) * 10 ** -9)
    #    return ResourceSplineBundleBitwidthDependent(Spline(operandWidths, delays))

    def _getFromDBSparseMuxDelay(self, dbCursor:sqlite3.Cursor, splineTy=ResourceSplineBundleArgCntDependent):
        operandWidths = []
        delays = []
        queryStr = \
        f'SELECT INPUT_NUMBER, DELAY0 FROM {self._targetName:s}_SparseMux'\
        ' WHERE core_name == "OneHotSparseMux_HasDef" AND LATENCY == 0'\
        ' ORDER BY INPUT_NUMBER ASC;'
        for (opWidth, delay) in dbCursor.execute(queryStr):
            operandWidths.append(int(opWidth))
            delays.append(float(delay) * 10 ** -9)
        assert delays, queryStr
        return splineTy(Spline(operandWidths, delays))

    def _getFromDBBramDelay(self, dbCursor:sqlite3.Cursor):
        # :attention: "BRAM" has some invisible char or something == operator does not work, DB Browser for SQLite Version 3.12.2 crashes
        queryStr = \
        f'SELECT BITWIDTH, DELAY0 FROM {self._targetName:s}_Memory'\
        ' WHERE LATENCY == 1 AND CORE_NAME like "%BRAM%"'\
        ' ORDER BY BITWIDTH ASC;'
        operandWidths = []
        delays = []
        for (opWidth, delay) in dbCursor.execute(queryStr):
            operandWidths.append(int(opWidth))
            delays.append(float(delay) * 10 ** -9)
        assert delays, queryStr
        return ResourceSplineBundleBitwidthDependent(Spline(operandWidths, delays))

    def _getFromDBDspGeometries(self, dbCursor:sqlite3.Cursor, archName: str):
        mulGeometries = []
        queryStr = \
        'SELECT a, b FROM DSP_ports'\
        f' WHERE core_name == {archName:s}'\
        ' ORDER BY a ASC;'
        for (a, b) in dbCursor.execute(queryStr):
            mulGeometries.append((int(a), int(b)))
        return mulGeometries

    def _init_coefs(self):
        with sqlite3.connect(f"file:{self._vitisDbFile.as_posix():s}?mode=ro", uri=True) as db:
            c = db.cursor()
            Sel = self._getFromDBArithmeticDelay(c, "Sel")
            # the multiplier uses dsp (for wide multipliers) with no register,
            # thus delay of whole dsp is added to delay of multiplier itself
            Multiplier = self._getFromDBArithmeticDelay(c, "Multiplier")
            Adder = self._getFromDBArithmeticDelay(c, "Adder")
            Cmp = self._getFromDBArithmeticDelay(c, "Cmp")
            LogicGate = self._getFromDBArithmeticDelay(c, "Cmp")
            Mux = self._getFromDBSparseMuxDelay(c)
            Shift = self._getFromDBSparseMuxDelay(c, splineTy=ResourceSplineBundleBitwidthDependent)
            BRAM = self._getFromDBBramDelay(c)
            self._DSP_MUL_GEOMETRIES = self._getFromDBDspGeometries(c, self._targetName.split("_")[0])

        self._OP_DELAYS: dict[Union[HOperatorNode, RtlResourceType], Callable[[int, int, int, float], tuple[int, float]]] = {
            HwtOps.ADD: Adder,
            HwtOps.SUB: Adder,
            HwtOps.MINUS_UNARY: Adder,
            HwtOps.EQ: Cmp,
            HwtOps.NE: Cmp,
            HwtOps.UGE: Cmp,
            HwtOps.UGT: Cmp,
            HwtOps.ULE: Cmp,
            HwtOps.ULT: Cmp,
            HwtOps.SGE: Cmp,
            HwtOps.SGT: Cmp,
            HwtOps.SLE: Cmp,
            HwtOps.SLT: Cmp,
            HwtOps.AND: LogicGate,
            HwtOps.OR: LogicGate,
            HwtOps.XOR: LogicGate,
            HwtOps.NOT: LogicGate,
            HwtOps.MUL: Multiplier,
            HwtOps.TERNARY: Mux,
            OP_ASHR: Shift,
            OP_LSHR: Shift,
            OP_SHL: Shift,
            OP_ROL: Shift,
            OP_ROR: Shift,
            OP_FSHL: Shift,
            OP_FSHR: Shift,
            ResourceFF: Sel,
            ResourceRAM: BRAM,
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__:s} {self._targetName:s} at 0x{id(self):x}>"


if __name__ == "__main__":
    p = HlsPlatformFromVitisDB("artix7_slow")
    print(p)

