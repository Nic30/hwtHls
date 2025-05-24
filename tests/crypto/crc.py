
from math import ceil
from typing import Optional, List

from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.frontend.hardBlock import HardBlockHwModule
from hwtHls.llvm.llvmIr import MachineInstr, Attribute, Function
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from hwtLib.logic.crc import Crc
from hwtLib.logic.crcComb import CrcComb
from hwtLib.logic.crcPoly import CRC_POLY
from pyMathBitPrecise.bit_utils import reverse_bits


def _crcFnDoesNotUseLLVMOperator(*args):
    raise NotImplementedError()


OP_CRC_STEP = HOperatorDef(_crcFnDoesNotUseLLVMOperator, allowsAssignTo=False, idStr="OP_CRC_STEP")


class CrcStepHardblock(HardBlockHwModule):
    """
    Function which takes data and CRC state and computes next CRC state value.
    :note: This is a HLS adapter for HDL implementation :class:`hwtLib.logic.crc.Crc`
    :note: to obtain final CRC value from state use 
    :ivar poly: polynomial to use for crc computation
    :ivar maxBytesProcessedInParallel: Maximum number of bytes of data to process
        in a single step, if specified this parameter limits the width of CRC computation
        circuit and optionally forces to use more CRC units in serial.
        This limits the code size and resource consumption in the cost of longer latency.
    """

    def __init__(self,
        poly: CRC_POLY,
        hwInputT:HBits,
        maxBytesProcessedInParallel:Optional[int]=None,
        name:Optional[str]=None,
        operationRealizationMeta:Optional[OpRealizationMeta]=None):
        self.poly = poly
        hwOutputT = HBits(poly.WIDTH)
        _hwInputT = HStruct(
            (hwOutputT, "state"),
            (hwInputT, "data"),
        )
        self.maxBytesProcessedInParallel = maxBytesProcessedInParallel
        HardBlockHwModule.__init__(self, _hwInputT, hwOutputT=hwOutputT, name=name,
                                   operationRealizationMeta=operationRealizationMeta)

    @override
    def getFnName(self):
        return (f"hwtHls.pyObjectPlaceholder.{self.placeholderObjectId:d}.crc"
                f".{self.poly.__name__:s}.i{self.hwInputT.field_by_name['data'].dtype.bit_length():d}")

    @override
    def _translateExprHConstHardBlockFunctionDef(self, toLlvm:"ToLlvmIrTranslator"):
        F:Function = HardBlockHwModule._translateExprHConstHardBlockFunctionDef(self, toLlvm)
        # F.addFnAttr(Attribute.Speculatable)
        strCtx = toLlvm.strCtx
        F.setMetadata(strCtx.addStringRef("hwtHls.mergableFunction.statePlusMaskedData"),
                      toLlvm.mdGetTuple([toLlvm.mdGetUInt32(1), ], insertSelfAsFirts=True))
        return F

    @override
    def translateMirToNetlist(self,
                               mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
                               mbSync: MachineBasicBlockMeta,
                               instr: MachineInstr,
                               builder: HlsNetlistBuilder,
                               inputs: List[HlsNetNodeOut],
                               dstName: str
                               ):
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        instrDstReg = instr.getOperand(0).getReg()
        argCnt = len(inputs)
        assert argCnt == 2 or argCnt == 3, ("inputs in format state, dataIn, maskIn", inputs)
        stateNext = builder.buildOp(OP_CRC_STEP, (self.poly, self.maxBytesProcessedInParallel), inputs[0]._dtype, *inputs)

        # rhs = builder.buildConcat(HBits(state._dtype.bit_length() - i1._dtype.bit_length()).from_py(0), i1)
        stateNext.name = dstName
        opRealizationMeta = self.operationRealizationMeta
        if opRealizationMeta:
            stateNext.obj.assignRealization(opRealizationMeta)

        valCache.add(mbSync.block, instrDstReg, stateNext, True)
        platform: VirtualHlsPlatform = mirToNetlist.netlist.parentHwModule._target_platform

        if OP_CRC_STEP not in platform._componentGenerators:
            platform._componentGenerators[OP_CRC_STEP] = CrcStepComponentGenerator(platform, "gen", "crc")


class CrcStepComponentGenerator(ComponentGenerator):
    """
    A generator which provides scheduling for CrcStepHardblock and
    provides info about how to translate it from netlist to RTL.
    """

    @override
    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        argCnt = len(node.dependsOn)
        assert argCnt == 2 or argCnt == 3, node
        dataIn = node.dependsOn[1]
        # resolve how many logic layers are there from crc polynome and data width
        poly, maxBytesProcessedInParallel = node.operatorSpecialization
        poly: CRC_POLY
        polyBits, _ = CrcComb.parsePoly(poly.POLY, poly.WIDTH)
        BYTE_SIZE = 8
        inputDataWidth = dataIn._dtype.bit_length()
        if maxBytesProcessedInParallel is None:
            dataWidth = inputDataWidth
        else:
            dataWidth = min(inputDataWidth, maxBytesProcessedInParallel * BYTE_SIZE)
        crcMatrix = CrcComb.buildCrcXorMatrix(dataWidth, polyBits)
        # compute maximum number of xored bits in each bit of result
        maxExprTerm = 0
        for dataInRow, stateRow in zip(crcMatrix[0], crcMatrix[1]):
            maxExprTerm = max(maxExprTerm, sum(dataInRow) + sum(stateRow))

        netlist = node.netlist
        platform: VirtualHlsPlatform = netlist.parentHwModule._target_platform

        r = platform.get_op_realization(HwtOps.XOR, None, 1, maxExprTerm, netlist.realTimeClkPeriod)
        debugTracer = node.netlist.dbgSubmoduleBuidTracer
        debugTracer.log(("expecting maxXorTerms:", maxExprTerm))
        if maxBytesProcessedInParallel is not None and inputDataWidth > dataWidth:
            rounds = inputDataWidth / dataWidth
            r *= ceil(rounds)
            debugTracer.log(("expecting rounds:", rounds))

        if argCnt == 2:
            return r
        else:
            maskBits = node.dependsOn[2]._dtype.bit_length()
            muxR = platform.get_op_realization(HwtOps.TERNARY, None, poly.WIDTH, maskBits, netlist.realTimeClkPeriod)
            return r + muxR

    @override
    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        operands = []
        for (dep, t) in zip(node.dependsOn, node.scheduledIn):
            assert dep is not None, ("All inputs must be connected", node, node.dependsOn)
            _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, t)
            assert isinstance(_o, TimeIndependentRtlResourceItem), (dep, _o)
            operands.append(_o)

        inputCnt = len(node.dependsOn)
        if inputCnt == 2:
            stateIn, dataIn = operands
            maskIn = None
        else:
            assert inputCnt == 3, node
            stateIn, dataIn, maskIn = operands
            maskIn = maskIn.data
        stateIn = stateIn.data
        dataIn = dataIn.data

        DATA_WIDTH = dataIn._dtype.bit_length()
        poly, maxBytesProcessedInParallel = node.operatorSpecialization
        poly: CRC_POLY
        assert stateIn._dtype.bit_length() == poly.WIDTH
        BYTE_WIDTH = 8
        # get number of bits processed by a single computation step
        if maxBytesProcessedInParallel is None:
            STEP_DATA_WIDTH = DATA_WIDTH
        else:
            STEP_DATA_WIDTH = maxBytesProcessedInParallel * BYTE_WIDTH
        if maxBytesProcessedInParallel is None:
            dataWidths = [DATA_WIDTH]
        else:
            DW = DATA_WIDTH
            dataWidths = []
            while DW > 0:
                dataWidths.append(min(DW, STEP_DATA_WIDTH))
                DW -= STEP_DATA_WIDTH

        maskBitOffset = 0
        netlist = node.netlist
        cb = AbstractComponentBuilder(netlist.parentHwModule, None, "gen")
        for DW in dataWidths:
            # create and configure instance of Crc
            m = Crc()
            m.setConfig(poly)
            m.CONTAINS_STATE_REG = False
            m.LATENCY = 0
            m.DATA_WIDTH = DW
            m.MASK_GRANULARITY = BYTE_WIDTH if maskIn else None

            name = cb._findSuitableName("Crc")
            setattr(cb.parent, name, m)

            # connect inputs of Crc instance
            m.stateIn(stateIn)
            m.dataIn.vld(1)
            dataBitOffset = maskBitOffset * BYTE_WIDTH
            m.dataIn.data(dataIn[dataBitOffset + DW:dataBitOffset])
            if maskIn is not None:
                m.dataIn.last(0)
                if DW == BYTE_WIDTH:
                    stateIn = maskIn[maskBitOffset]._ternary(m.dataOut._sig, stateIn)
                else:
                    m.dataIn.mask(maskIn[maskBitOffset + (STEP_DATA_WIDTH // BYTE_WIDTH): maskBitOffset])
                    stateIn = m.dataOut._sig
            else:
                stateIn = m.dataOut._sig

            maskBitOffset += STEP_DATA_WIDTH // BYTE_WIDTH

        # register output of Crc for others to connect
        assert len(node._outputs) == 1
        res = allocator.rtlRegisterOutputRtlSignal(
            node._outputs[0],
            stateIn, False, False, False)

        node._isRtlAllocated = True
        return res


class CrcFinalizeHardblock(HardBlockHwModule):
    """
    Function which converts intermediate state to a final CRC value
    (it applies REFOUT and XOROUT of CRC_POLY)
    """

    def __init__(self,
        poly: CRC_POLY,
        name:Optional[str]=None,
        operationRealizationMeta:Optional[OpRealizationMeta]=None):
        self.poly = poly
        T = HBits(poly.WIDTH)
        HardBlockHwModule.__init__(self, T, T, name=name,
                                   operationRealizationMeta=operationRealizationMeta)

    @override
    def _translateExprHConstHardBlockFunctionDef(self, toLlvm:"ToLlvmIrTranslator"):
        F:Function = HardBlockHwModule._translateExprHConstHardBlockFunctionDef(self, toLlvm)
        F.addFnAttr(Attribute.Speculatable)
        return F

    @override
    def translateMirToNetlist(self,
                               mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
                               mbSync: MachineBasicBlockMeta,
                               instr: MachineInstr,
                               builder: HlsNetlistBuilder,
                               inputs: List[HlsNetNodeOut],
                               dstName: str
                               ):
        """
        :see: based on :meth:`hwtLib.logic.crc.Crc._aply_REFOUT_and_XOROUT`
        """
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        instrDstReg = instr.getOperand(0).getReg()
        assert len(inputs) == 1, inputs
        poly = self.poly
        XOROUT:int = poly.XOROUT
        REFOUT:bool = poly.REFOUT
        res = inputs[0]
        if XOROUT == 0 and REFOUT:
            pass
        else:
            if REFOUT:
                res = builder.buildBitReverse(res)

            if XOROUT != 0:
                # reverse bit order in XOROUT
                XOROUT = reverse_bits(XOROUT, poly.WIDTH)
                res = builder.buildXor(res, builder.buildConstPy(res._dtype, XOROUT), name=dstName)

        valCache.add(mbSync.block, instrDstReg, res, True)

