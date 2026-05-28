from io import StringIO
import math

from hwtHls.llvm.llvmIr import Function, BasicBlock, Instruction, LLVMStringContext, Argument, \
    HwtHlsIoMetadata_get, HwtHlsIoMetadata
from hwtHls.ssa.analysis.llvmIrInterpretUtils import RE_NON_ID, \
    _findLoadOrStoreWidthForValue
from pyDigitalWaveTools.vcd.common import VCD_SIG_TYPE
from pyDigitalWaveTools.vcd.value_format import VcdBitsFormatter, \
    LogValueFormatter
from pyDigitalWaveTools.vcd.writer import VcdWriter

# STRICT_VCD_ONLY gtkwave lib/libgtkwave/src/gw-vcd-loader.c
class VcdLlvmIrBBFormatter(LogValueFormatter):

    def bind_var_info(self, varInfo: "VcdVarWritingInfo"):
        self.vcdId = varInfo.vcdId

    def format(self, newVal: BasicBlock, updater, t: int, out: StringIO):
        # val = newVal.getName().str()
        name = newVal.printAsOperand()[len("label "):]
        name = RE_NON_ID.sub("_", name)
        out.write(f"s{name:s} {self.vcdId:s}\n")


class VcdLlvmIrCodelineFormatter(LogValueFormatter):

    def __init__(self, instrCodeline: dict[Instruction, int]):
        self.instrCodeline = instrCodeline

    def bind_var_info(self, varInfo: "VcdVarWritingInfo"):
        self.vcdId = varInfo.vcdId

    def format(self, newVal: Instruction, updater, t: int, out: StringIO):
        codeline = self.instrCodeline[newVal]
        out.write(f"b{codeline:b} {self.vcdId:s}\n")


class VcdLlvmIrSimTimeFormatter(LogValueFormatter):

    def __init__(self, step: int):
        self.step = step

    def bind_var_info(self, varInfo: "VcdVarWritingInfo"):
        self.vcdId = varInfo.vcdId

    def format(self, newVal: int, updater, t: int, out: StringIO):
        # val = newVal.getName().str()
        out.write(f"b{newVal//self.step:b} {self.vcdId:s}\n")


class VcdFloatFormatter(LogValueFormatter):
    """
    VcdRealFormatter
    """

    def bind_var_info(self, varInfo: "VcdVarWritingInfo"):
        self.vcdId = varInfo.vcdId

    def format(self, newVal: "HFloatTmpConst", updater, t: int, out: StringIO):
        if newVal._is_full_valid():
            out.write(f"r{float(newVal.val):.16g} {self.vcdId:s}\n")
        else:
            out.write(f"{math.nan:.16g} {self.vcdId:s}\n")


def _prepareWaveWriterTopIo(waveLog: VcdWriter, strCtx: LLVMStringContext, fn: Function):
    with waveLog.varScope("args") as argScope:
        ioMetadatas = HwtHlsIoMetadata_get(fn)
        assert fn.arg_size() == len(ioMetadatas)
        for arg, ioMetadata in zip(fn.args(), ioMetadatas):
            arg: Argument
            ioMetadata: HwtHlsIoMetadata
            if ioMetadata.addrWidth != 0:
                continue  # :note: not implementd
                # raise NotImplementedError(arg, ioMetadata.addrWidth)
            name = RE_NON_ID.sub("_", arg.getName().str())
            assert name, arg
            argWidth = _findLoadOrStoreWidthForValue(strCtx, arg)
            argScope.addVar(arg, name, VCD_SIG_TYPE.WIRE, argWidth, VcdBitsFormatter())
