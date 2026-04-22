from typing import Optional, Union, Self

from hwt.code import If
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.setDeque import SetDeque
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic
from hwtHls.netlist.analysis.hlsNetlistSimHandler import HlsNetlistSimHandler
from hwtHls.netlist.analysis.hlsNetlistSimulatorTypes import HlsNetlistSimStateT
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    HlsNetNodeOutLazy
from hwtHls.netlist.nodes.schedulableNode import HlsNetNodeOut_getMaxUseTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import clkWindowIndex, SchedTime, \
    clkWindowBegin
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION
from pyMathBitPrecise.bit_utils import ValidityError


# [todo] maybe use MemoryAllocationMeta instead
class RtlRegisterMeta():
    """
    Info for HlsNetNodeWriteRegister/HlsNetNodeReadRegister association
    """

    @staticmethod
    def resolveName(w: HlsNetNodeWrite, r: HlsNetNodeWrite):
        if w.name.endswith("_src"):
            name = w.name[:-len("_src")]
        elif r.name.endswith("_dst"):
            name = r.name[:-len("_dst")]
        else:
            name = None
        if name:
            return f"ch{w._id}_{r._id}_{name}"
        else:
            return f"ch{w._id}_{r._id}"

    def __init__(self, name: str, wasBackedge: bool, dtype: HBits, initValue: Union[int, HBitsConst, None]):
        self.name = name
        self._dtype = dtype
        self.wasBackedge = wasBackedge  # else was forwardedge
        self.initValue = initValue
        self.loads: list[HlsNetNodeExplicitRegisterLoad] = []
        self.stores: list[HlsNetNodeExplicitRegisterStore] = []

    def __repr__(self):
        return (f"<{self.__class__.__name__:s} {self.name}, {self._dtype},"
                f" wasBackedge={int(self.wasBackedge)}, init={self.initValue}>")


class HlsNetNodeExplicitRegisterLoad(HlsNetNode):
    """
    Similar to :class:`HlsNetNodeWrite` but operates on register 
    """

    def __init__(self, netlist:"HlsNetlistCtx", regMeta: RtlRegisterMeta,
                 dtype: HBits, name:Optional[str]=None):
        if name is None:
            name = regMeta.name

        HlsNetNode.__init__(self, netlist, name)
        self.regMeta = regMeta
        self._addOutput(dtype, None)
        regMeta.loads.append(self)

    @classmethod
    def createInTime(cls, netlist:"HlsNetlistCtx",
                     regMeta: RtlRegisterMeta, parentElm: ArchElement, t: SchedTime) -> Self:
        ld = cls(netlist, regMeta, regMeta._dtype)
        ld.resolveRealization()
        assert t % netlist.normalizedClkPeriod == 0, ("Load from reg should be always scheduled to clk window begin",
                                                      regMeta, t, netlist.normalizedClkPeriod)
        ld._setScheduleZeroTimeSingleClock(t)
        parentClkI: int = clkWindowIndex(t, netlist.normalizedClkPeriod)
        parentElm._addNodeIntoScheduled(parentClkI, ld, allowNewClockWindow=False)

        return ld

    @classmethod
    def createAsOutSubstitution(cls, netlist:"HlsNetlistCtx", builder: HlsNetlistBuilder,
                                regMeta: RtlRegisterMeta, o: HlsNetNodeOut,
                                onlyInThisClk:bool=False) -> Self:
        assert regMeta._dtype == o._dtype, (regMeta, o._dtype, o)
        parentElm: ArchElement = o.obj.parent
        t = o.obj.scheduledOut[o.out_i]
        clkPeriod = netlist.normalizedClkPeriod
        parentClkI: int = clkWindowIndex(t, clkPeriod)

        ld = cls.createInTime(netlist, regMeta, parentElm, clkWindowBegin(parentClkI, clkPeriod))

        if onlyInThisClk:
            builder.replaceOutputIf(o, ld._outputs[0], lambda i: i.obj.scheduledIn[i.in_i] // clkPeriod == parentClkI)
        else:
            builder.replaceOutput(o, ld._outputs[0], True)
        return ld

    def resolveRealization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)

    def hlsNetlistSimGetHandler(self, sim: "HlsNetlistSimulator") -> HlsNetlistSimHandler:
        return HlsNetlistSimHandlerExplicitRegisterLoad()

    def rtlAlloc(self, allocator: "ArchElement"):
        assert not self._isRtlAllocated, self
        r = self.regMeta
        reg = allocator.netNodeToRtl.get(r)
        if reg is None:
            reg = allocator._reg(r.name, r._dtype, def_val=r.initValue)
            allocator.netNodeToRtl[r] = reg

        tir = allocator.rtlRegisterOutputRtlSignal(self._outputs[0], reg, True, False, False)
        clkPeriod = self.netlist.normalizedClkPeriod
        clkI = clkWindowIndex(self.scheduledZero, clkPeriod)
        endClkI = clkWindowIndex(HlsNetNodeOut_getMaxUseTime(self._outputs[0]), clkPeriod)
        tir.markPersistent(clkI, endClkI)

        self._isRtlAllocated = True
        return tir

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} {self.regMeta}>"


class HlsNetlistSimHandlerExplicitRegisterLoad(HlsNetlistSimHandler):

    def simInit(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque[HlsNetNode], node: HlsNetNodeExplicitRegisterLoad):
        assert len(node._outputs) == 1, node
        r = node.regMeta
        state[node._outputs[0]] = state[r] = r._dtype.from_py(r.initValue)
        worklist.extend(u.obj for u in node.usedBy[0])

    def simCombStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque["HlsNetNode"], node: "HlsNetNode"):
        r = node.regMeta
        curR = state[r]
        state[node._outputs[0]] = curR
        worklist.extend(u.obj for u in node.usedBy[0])

    def simSeqStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque["HlsNetNode"], node: "HlsNetNode"):
        r = node.regMeta
        curR = state[r]
        curO = state[node._outputs[0]]
        if not (curR == curO):
            worklist.append(node)


class HlsNetNodeExplicitRegisterStore(HlsNetNode):

    def __init__(self, netlist:"HlsNetlistCtx", regMeta: RtlRegisterMeta, name:Optional[str]=None):
        if name is None:
            name = regMeta.name
        HlsNetNode.__init__(self, netlist, name)
        self.regMeta = regMeta
        self._addInput(None)
        regMeta.stores.append(self)
        self.extraCond: Optional[HlsNetNodeIn] = None
        self._isWorkingOutOfParentState = False

    @classmethod
    def createAsInSubstitution(cls, netlist:"HlsNetlistCtx",
                               builder: HlsNetlistBuilder,
                               regMeta: RtlRegisterMeta,
                               i: HlsNetNodeIn,
                               en: Optional[HlsNetNodeOut]) -> Self:
        st: HlsNetNodeExplicitRegisterStore = cls(netlist, regMeta, name=i.getPrettyName())
        st.resolveRealization()
        parentElm: ArchElement = i.obj.parent
        t = i.obj.scheduledIn[i.in_i]
        st._setScheduleZeroTimeSingleClock(t)
        parentClkI: int = clkWindowIndex(t, netlist.normalizedClkPeriod)
        parentElm._addNodeIntoScheduled(parentClkI, st, allowNewClockWindow=False)
        if en is not None:
            st.addControlSerialExtraCond(en, addDefaultScheduling=True)
            scheduleUnscheduledControlLogic((parentElm, parentClkI), st.dependsOn[st.extraCond.in_i])

        builder.replaceInput(i, st._inputs[0])
        return st

    @classmethod
    def createAsCondSet(cls, netlist:"HlsNetlistCtx",
                        regMeta: RtlRegisterMeta,
                        parentElm: ArchElement,
                        t: SchedTime,
                        v: HlsNetNodeOut,
                        en: Optional[HlsNetNodeOut],
                        name:Optional[str]=None) -> Self:
        st: HlsNetNodeExplicitRegisterStore = cls(netlist, regMeta, name=name)
        st.resolveRealization()
        st._setScheduleZeroTimeSingleClock(t)
        parentClkI: int = clkWindowIndex(t, netlist.normalizedClkPeriod)
        parentElm._addNodeIntoScheduled(parentClkI, st, allowNewClockWindow=False)
        if en is not None:
            st.addControlSerialExtraCond(en, addDefaultScheduling=True)
            scheduleUnscheduledControlLogic((parentElm, parentClkI), st.dependsOn[st.extraCond.in_i])

        scheduleUnscheduledControlLogic((parentElm, parentClkI), v)
        v.connectHlsIn(st._inputs[0], False, False)

        return st

    @classmethod
    def createAsCondConstSet(cls, netlist:"HlsNetlistCtx",
                             builder: HlsNetlistBuilder,
                             regMeta: RtlRegisterMeta,
                             parentElm: ArchElement,
                             t: SchedTime,
                             v: HBitsConst,
                             en: Optional[HlsNetNodeOut],
                             name:Optional[str]=None) -> Self:
        parentClkI: int = clkWindowIndex(t, netlist.normalizedClkPeriod)
        c = builder.buildConst(v)
        c.obj.resolveRealization()
        c.obj._setScheduleZeroTimeSingleClock(t)
        parentElm._addNodeIntoScheduled(parentClkI, c.obj, allowNewClockWindow=False)
        return cls.createAsCondSet(netlist, regMeta, parentElm, t, c, en, name=name)

    def resolveRealization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)

    def addControlSerialExtraCond(self, en: Union[HlsNetNodeOut, HlsNetNodeOutLazy],
                                  addDefaultScheduling:bool=False, checkCycleFree:bool=True):
        return HlsNetNodeExplicitSync.addControlSerialExtraCond(self, en, addDefaultScheduling, checkCycleFree)

    @override
    def _removeInput(self, index:int):
        iObj = self._inputs[index]
        if self.extraCond is iObj:
            self.extraCond = None

        return HlsNetNode._removeInput(self, index)

    def hlsNetlistSimGetHandler(self, sim: "HlsNetlistSimulator") -> HlsNetlistSimHandler:
        return HlsNetlistSimHandlerExplicitRegisterStore()

    def rtlAlloc(self, allocator: "ArchElement"):
        assert not self._isRtlAllocated, self
        r = self.regMeta
        reg = allocator.netNodeToRtl.get(r)
        if reg is None:
            reg = allocator._reg(r.name, r._dtype, def_val=r.initValue)
            allocator.netNodeToRtl[r] = reg

        din = allocator.rtlAllocHlsNetNodeInDriverIfExists(self._inputs[0])
        ec = allocator.rtlAllocHlsNetNodeInDriverIfExists(self.extraCond)
        if ec is not None:
            ec = ec.data
        ecIsFalse = False
        if isinstance(ec, HBitsConst):
            try:
                ec = int(ec)
            except ValidityError:
                raise AssertionError("extraCond value is an undifined constant", self)
            if ec:
                ec = None
            else:
                ecIsFalse = True

        if not ecIsFalse:
            if ec is None:
                res = [
                    reg(din.data)
                ]
            else:
                res = [
                    If(ec, reg(din.data))
                ]
            con = allocator.connections[self.getSchedResourceClkI()]
            allocator._rtlAllocDatapathIo(r, self, None, con, res)

        self._isRtlAllocated = True
        return []

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__:s} {self._id:d} {self.regMeta} {self.dependsOn[0]}>"


class HlsNetlistSimHandlerExplicitRegisterStore(HlsNetlistSimHandler):

    def _getExtraCond(self, state: HlsNetlistSimStateT, n: HlsNetNodeExplicitRegisterLoad):
        ec = n.extraCond
        if ec is not None:
            ec: HBitsConst = state[n.dependsOn[ec.in_i]]
            if ec._is_full_valid():
                ec = bool(ec)
            else:
                ec = None
        else:
            ec = True

    def simSeqStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque["HlsNetNode"], node: "HlsNetNode"):
        ec = self._getExtraCond(state, node)
        r = node.regMeta
        if ec is None:
            state[r] = r._dtype.from_py(None)
        else:
            din = state[node.dependsOn[0]]
            state[r] = din
