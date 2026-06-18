#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque
from io import StringIO
import sys
from typing import Union, Optional, Callable, Any, Self

from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b1
from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.function import HFunction
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hwIO import HwIO
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.frame import PyBytecodeFrame
from hwtHls.frontend.fromPython import PyBytecodeToSsa
from hwtHls.frontend.hardBlock import HardBlockHwModule, \
    ComponentGeneratorForHardBlock
from hwtHls.frontend.pragma import _PyBytecodeIntrinsic
from hwtHls.frontend.pyBytecode import hlsBytecode, hlsLowLevel
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.llvm.llvmIr import Function, Type, \
    FunctionCallee, CallInst, IRBuilder, Value, Attribute, \
    MachineInstr, Register, Instruction, MachineRegisterInfo, InstructionToCallInst, \
    MemoryEffects, BasicBlock
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.platform.opRealizationMeta import OpRealizationMeta, \
    EMPTY_OP_REALIZATION
from hwtHls.scope import HlsScope
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from pyDigitalWaveTools.vcd.writer import VcdWriter
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule


class HwSimCallbackHwArgDescriptor(int):
    """
    Index for HwSimCallback.hwArgs
    """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__:s} {int(self)}>"


def _OP_HWSIMCALLBACKDoesNotUseLLVMOperator(*args):
    raise NotImplementedError()


OP_HWSIMCALLBACK = HOperatorDef(_OP_HWSIMCALLBACKDoesNotUseLLVMOperator, idStr="OP_HWSIMCALLBACK")


class HwSimCallback(_PyBytecodeIntrinsic):
    """
    A container for call of the callback in simulator/interpret.
    Supports HW arguments which are resolved during simulation and python argumets
    which are captured during call construction.

    :note: This object is represented in llvm/HlsNetlist as a call which
        is associated with custom ComponentGenerator. ComponentGenerator implement behavior of this.
        This implies that any function implementation is possible and it is possible to convert this
        for example into "print" or "assert" on HDL level. 

    :see: :class:`hwtHls.frontend.hardBlock.HardBlockHwModule`    
    :ivar placeholderObjectId: index of this in :attr:`ToLlvmIrTranslator.placeholderObjectSlots` list
    
    :note: This object intended use is a container of call of python function mainly for debugging purposes.
    """

    __hlsIsLowLevelFn = True
    _dtype = HFunction()

    def __init__(self,
                 hwInputT: HdlType,
                 hwOutputT: HdlType,
                 pyArgs: tuple[Union[Any, HwSimCallbackHwArgDescriptor]],
                 pyFunction: Callable,
                 name: Optional[str]=None,
                 defaultKwargs={},
                 operationRealizationMeta: Optional[OpRealizationMeta]=None):
        super().__init__(hwInputT, hwOutputT=hwOutputT, defaultKwargs=defaultKwargs,
                         name=name, operationRealizationMeta=operationRealizationMeta)
        self.pyArgs = pyArgs
        self.pyFunction = pyFunction
        self.placeholderObjectId: Optional[int] = None
        self._llvmFunction:Optional[Function] = None

    def __copy__(self) -> Self:
        return self.__class__(self.hwInputT, self.hwOutputT, self.pyArgs,
                              self.pyFunction, name=self.val,
                              defaultKwargs=self.defaultKwargs,
                              operationRealizationMeta=self.operationRealizationMeta)

    def getFnName(self):
        return f"hwtHls.pyObjectPlaceholder.{self.placeholderObjectId:d}.{self.__class__.__name__:s}.i{self.hwInputT.bit_length():d}"

    def _translateExprHConstHardBlockFunctionDef(self, toLlvm:ToLlvmIrTranslator):
        F:Function = HardBlockHwModule._translateExprHConstHardBlockFunctionDef(self, toLlvm)
        # F.addFnAttr(Attribute.AttrKind.Speculatable)
        F.addFnAttr(Attribute.AttrKind.Memory)
        F.setMemoryEffects(MemoryEffects.unknown())
        platform = toLlvm.parentHwModule._target_platform
        if OP_HWSIMCALLBACK not in platform._componentGenerators:
            platform._componentGenerators[OP_HWSIMCALLBACK] = HwSimCallbackComponentGenerator(platform, "gen", "hwSimCallback")
        return F

    @override
    def translateToLlvm(self, toLlvm: "ToLlvmIrTranslator", b: IRBuilder, args: tuple[Value]) -> CallInst:
        # F = self._llvmFunction
        # if F is None:
        #    F = self.F = self._createLlvmFunctionDef(toLlvm)
        _, F = toLlvm.placeholderObjectSlots[self.placeholderObjectId]
        _args = [toLlvm._translateExprInt(self.placeholderObjectId, Type.getIntNTy(toLlvm.ctx, 32))]
        _args.extend(args)
        calle = FunctionCallee(F)
        res: CallInst = b.CreateCall(calle, _args)
        # fn = res.getCalledFunction()
        # AddDefaultFunctionAttributes(fn)
        # res.setOnlyAccessesArgMemory()
        # res.setDoesNotAccessMemory()
        return res

    @staticmethod
    def _llvmMirToHlsNetlist_cutOfIdAndWidthFromOps(ops: tuple):
        # ops are in foramt $objId id, $resultWidth, inputs,  inputWidths, enCond
        # extract inputs and enCond
        return ops[1 + 1:2 + (len(ops) - 2) // 2], ops[-1]

    @override
    def getComponentGeneratorKey(self):
        return OP_HWSIMCALLBACK


class HwSimCallbackComponentGenerator(ComponentGeneratorForHardBlock):

    @override
    def llvmIrInterpretDecode(self, interpret: LlvmIrInterpret, instr: Instruction,
                              pyObjectPlaceholder: HwSimCallback) -> LlvmIrInstrFunction:
        instr: CallInst = InstructionToCallInst(instr)
        assert instr
        # placeholderId, arg0, args1, ....
        hwArgs = interpret._decodeInstArguments(u.get() for u in tuple(instr.args())[1:])

        def _hwSimCallback(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]) -> LlvmIrInstrFunction:
            hwArgValues = interpret._prepareInstrArguments(hwArgs, regs)
            res = pyObjectPlaceholder.pyFunction(*hwArgValues)
            if res is not None:
                interpret._storeInstrResult(waveLog, nowTime, regs, instr, res)

        return _hwSimCallback

    @override
    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI: MachineRegisterInfo, instr: MachineInstr,
                               pyObjectPlaceholder: HwSimCallback) -> LlvmMirInstrFunction:
        dst = interpret._decodeInstArguments(MRI, instr, (instr.getOperand(0),))
        hwArgs, _ = HwSimCallback._llvmMirToHlsNetlist_cutOfIdAndWidthFromOps(tuple(instr.operands()))
        hwArgs = interpret._decodeInstArguments(MRI, instr, hwArgs)
        dstWidth = hwArgs[0]
        hwArgs = hwArgs[1:]
        # HWTFPGA_PYOBJECT_PLACEHOLDER_ $dst , $objId, $dstWidth, $src[n], $srcWidth[n], $enCond

        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)

        argIsConst = [isinstance(a, HConst) for a in hwArgs]
        if dstWidth:
            resTy = HBits(dstWidth)
            resUndefVal = resTy.from_py(None)
        else:
            resTy = None
            resUndefVal = None

        def _intrinsic_crc_finalize(nowTime: int, regs: list[HConst]):
            if hasRuntimeCond and not regs[cond]:
                res = resUndefVal
            else:
                hwArgValues = tuple(a if aIsConst else regs[a] for aIsConst, a in zip(argIsConst, hwArgs))
                res = pyObjectPlaceholder.pyFunction(*hwArgValues)

            if resTy is not None:
                regs[dst] = res

        return _intrinsic_crc_finalize

    @override
    def llvmMirToHlsNetlist(self,
                            mirToNetlist: HlsNetlistAnalysisPassMirToNetlist,
                            builder: HlsNetlistBuilder,
                            mbMeta: MachineBasicBlockMeta,
                            allBlockingLoadAck: Optional[HlsNetNodeOutAny],
                            name: Optional[str],
                            instr: MachineInstr,
                            dst: Union[Register, tuple[Register]],
                            ops: MirToHlsNetlistTranslatedInstrOpsT,
                            pyObjectPlaceholder: HwSimCallback) -> Optional[HlsNetNodeOutAny]:
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        inputs, _ = HardBlockHwModule._llvmMirToHlsNetlist_cutOfIdAndWidthFromOps(ops)
        resWidth = HardBlockHwModule._llvmMirToHlsNetlist_getResultWidth(ops)
        netlist = builder.netlist
        n = HlsNetNodeHwSimCallback(netlist, pyObjectPlaceholder, name=name)
        builder._addNode(n)
        for a in inputs:
            aIn = n._addInput(None)
            a.connectHlsIn(aIn)

        if allBlockingLoadAck is not None:
            en = n._addInput("en")
            allBlockingLoadAck.connectHlsIn(en)

        if resWidth:
            res = n._addOutput(HBits(resWidth))
            valCache.add(mbMeta.block, dst, res, True)

        return allBlockingLoadAck


class HlsNetNodeHwSimCallback(HlsNetNode):

    def __init__(self, netlist:HlsNetlistCtx, hwSimCallback: HwSimCallback, name:str=None):
        super().__init__(netlist, name=name)
        self.hwSimCallback = hwSimCallback

    def resolveRealization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)

    def hasSideeffect(self):
        return True

    # [todo]
    # bind to BasicRtlSimulator/BasicRtlSimIo/BasicRtlSimModel
    # support in hwt.serializer.simModel
    def rtlAlloc(self, allocator: ArchElement):
        self._isRtlAllocated = True


@hlsLowLevel
@hwt_expr_producer
def hwSimPrint(*args, file=sys.stdout):
    for a in args:
        if isinstance(a, str):
            file.write(a)
        else:
            file.write(str(a))
    file.write("\n")


def hwSimPrint_hlsCallOverride(toSsa: PyBytecodeToSsa, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction, _self, fn, args, kwargs):
    file = kwargs.get("file", sys.stdout)
    assert file is not None, file
    hwArgs: list[RtlSignalBase] = []
    pyArgs: list[Union[Any, HwSimCallbackHwArgDescriptor]] = []
    for a in args:
        if isinstance(a, HwIO):
            hwArgs.append(a._sig)
            a = HwSimCallbackHwArgDescriptor(len(hwArgs) - 1)
        elif isinstance(a, RtlSignalBase):
            hwArgs.append(a)
            a = HwSimCallbackHwArgDescriptor(len(hwArgs) - 1)
        pyArgs.append(a)

    if not hwArgs:
        hwInputT = HVoidOrdering
    elif len(hwArgs) == 0:
        hwInputT = hwArgs[0]._dtype
    else:
        hwInputT = HStruct(
            *((a._dtype, f"a{i}") for i, a in enumerate(hwArgs))
        )
    hwOutputT = HVoidOrdering

    def hwSimPrintCallback(*hwArgsValues):
        try:
            args = [hwArgsValues[a] if isinstance(a, HwSimCallbackHwArgDescriptor) else a for a in pyArgs]
        except:
            raise
        for a in args:
            if isinstance(a, str):
                file.write(a)
            else:
                file.write(str(a))
        file.write("\n")

    return HwSimCallback(hwInputT, hwOutputT, pyArgs, hwSimPrintCallback)(*hwArgs)


hwSimPrint.hlsCallOverride = hwSimPrint_hlsCallOverride


class TestHwSimCallback(HwModule):

    @override
    def hwConfig(self) -> None:
        self.PRINT_FILE = HwParam(sys.stdout)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.i = HwIODataRdVld()
        self.i.DATA_WIDTH = 8

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            v = hls.read(self.i, blocking=False).data
            hwSimPrint("hwSimPrint ", v, file=self.PRINT_FILE)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class PassTestInjectorForTestHwSimCallback(PassTestInjectorForDInDOutHwModule):

    def checkIrAndMirArgs(self, args: tuple[deque]):
        file = self._topToRunTestsOn.PRINT_FILE
        s = file.getvalue()
        file.truncate(0)
        file.seek(0)
        self.assertEqual(s, self.OUT_DATA_REF[0])


class TestHwSimCallbackTC(BaseIrMirRtl_TC):

    def _test(self, dut: TestHwSimCallback,
                TEST_DATA: list[int],
                REF_DATA: str,
                freq=int(1e6)):
        """
        :param model: a function which process all inputs and generate all outputs
        For meaning of params check :meth:`~._testOneOut`
        """
        dataTy = HBits(8)
        IN_DATA = tuple(dataTy.from_py(d) for d in TEST_DATA)
        file = StringIO()
        dut.PRINT_FILE = file
        dut.CLK_FREQ = freq
        wallTime = len(REF_DATA) * 10
        passTests = PassTestInjectorForTestHwSimCallback(dut, self)
        passTests.setTimeLimits(wallTimeIr=wallTime, wallTimeMir=wallTime, wallTimeRtl=len(REF_DATA))
        passTests.bindDataByInOut((IN_DATA,), (), PORT_NAMES=("i",))
        passTests.test_allInOne()
        # [todo] see HlsNetNodeHwSimCallback.rtlAlloc
        # s = file.getvalue()
        # file.truncate(0)
        # file.seek(0)
        # self.assertEqual(s, REF_DATA)

    def test_10(self, N=10):
        file = StringIO()
        TEST_DATA = [v for v in range(N)]
        for v in TEST_DATA:
            file.write("hwSimPrint <HBitsConst b8 ")
            file.write(str(v))
            file.write(">\n")
        REF_DATA = file.getvalue()
        dut = TestHwSimCallback()
        self._test(dut, TEST_DATA, REF_DATA)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    # m = TestHwSimCallback()
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE,
    #                                                       llvmCliArgs=[
    #                                                           # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED
    #                                                       ])))

    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(TestHwSimCallbackTC)
    # suite = unittest.TestSuite([TestHwSimCallbackTC("test_ShifterLeftUsingHwLoopWithBreakIf0_unrol2")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
