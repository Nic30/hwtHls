
from hwt.hdl.commonConstants import b0, b1
from hwt.hdl.const import HConst
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.setDeque import SetDeque
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.hlsNetlistSimAgent import HlsNetlistSimAgent
from hwtHls.netlist.analysis.hlsNetlistSimulatorTypes import HlsNetlistSimStateT
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.pyUtils.peekableIterator import PeekableIterator, \
    PeekableIterator_HANDLE, PeekableDeque
from hwtHls.ssa.analysis.llvmIrInterpretUtils import SimIoUnderflowErr
from hwtSimApi.agents.base import NOP
from hwtSimApi.triggers import StopSimumulation


class HlsNetlistSimAgentScalarDriver(HlsNetlistSimAgent):
    """
    HlsNetlist simulation agent (UVM-like) for simple HlsNetNodeRead nodes which
    are reading the data from outside of circuit.
    """

    def _getEnableFlags(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT,
                        n: HlsNetNodeExplicitSync, allowInvalid:bool) -> tuple[bool, bool]:
        sw = n.skipWhen
        if sw is not None:
            sw: HBitsConst = state[n.dependsOn[sw.in_i]]
            if sw._is_full_valid():
                sw = bool(sw)
            else:
                if allowInvalid:
                    sw = None
                else:
                    raise NotImplementedError(sim.nowTime, "skipWhen can not have undefined value", n,)
        else:
            sw = False

        ec = n.extraCond
        if ec is not None:
            ec: HBitsConst = state[n.dependsOn[ec.in_i]]
            if ec._is_full_valid():
                ec = bool(ec)
            else:
                if allowInvalid:
                    pass
                elif n.skipWhen is None:
                    raise NotImplementedError(sim.nowTime, "extraCond can not have undefined value if there is no skipWhen", n)
                elif sw:
                    raise NotImplementedError(sim.nowTime, "extraCond can not have undefined value when skipWhen=1", n)
                ec = None
        else:
            ec = True

        return sw, ec

    @override
    def simInit(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque[HlsNetNode], node: HlsNetNodeExplicitSync):
        HlsNetlistSimAgent.simInit(self, sim, state, worklist, node)
        self._checkNodePortsSupported(node,
                                      (node.skipWhen, node.extraCond),
                                      (node._portDataOut, node._valid, node._validNB)
                                      )

        ioProxy = self.ioProxy
        self.wordTy = ioProxy.getDataTypeOfNativeRead()
        self.DATA_INVALID = self.wordTy.from_py(None)
        self.data = PeekableIterator(self.data)

        for o in (node._valid, node._validNB):
            if o is None:
                continue
            state[o] = b0

    def simCombStepDataSet(self, sim: "HlsNetlistSimulator",
                           state: HlsNetlistSimStateT,
                           worklist: SetDeque[HlsNetNode],
                           node: "HlsNetNodeRead", data: HConst):
        self._updatePortValue(node._portDataOut, data, state, worklist)

    @override
    def simCombStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque[HlsNetNode], n: "HlsNetNodeRead"):
        """
        Update combinational outputs from inputs and current data
        """
        # sw, ec = self._getEnableFlags(sim, state, n, True)
        if self._enabled:
            d = self.data.peek()
            vld = d is not NOP and d is not PeekableIterator_HANDLE
            # vld = not sw and ec and d is not NOP and d is not PeekableIterator_HANDLE
            # if sw is None or ec is None:
            #    vld = bInvalid
            # else:
            vld = b1 if vld else b0
        else:
            d = NOP
            vld = b0

        self._updatePortValue(n._valid, vld, state, worklist)
        self._updatePortValue(n._validNB, vld, state, worklist)
        d = self.DATA_INVALID if d is NOP or d is PeekableIterator_HANDLE else d
        self.simCombStepDataSet(sim, state, worklist, n, d)

    @override
    def simSeqStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque[HlsNetNode], n: "HlsNetNodeRead", endSimOnUnderflow=True):
        """
        If the node is enabled by input signals pop next data
        """
        if not self._enabled:
            return

        sw, ec = self._getEnableFlags(sim, state, n, False)
        data = self.data
        if sw:
            if ec:
                # non-blocking read
                d = data.peek()
                if d is not NOP and d is not PeekableIterator_HANDLE:
                    try:
                        next(data)
                    except StopIteration:
                        raise SimIoUnderflowErr()
                    worklist.append(n)
            else:
                # port dissabled
                return

        else:
            if ec:
                # blocking read
                try:
                    next(data)
                except StopIteration:
                    if endSimOnUnderflow:
                        raise SimIoUnderflowErr()

                worklist.append(n)
            else:
                # peek, stall if data not available, but not consume it
                if endSimOnUnderflow and data.peek() is PeekableIterator_HANDLE:
                    raise StopSimumulation()


class HlsNetlistSimAgentScalarMonitor(HlsNetlistSimAgent):
    """
    HlsNetlist simulation agent (UVM-like) for simple HlsNetNodeWrite nodes which
    are sending the data from the circuit (running in simulation) to outside of simulation.
    """

    @override
    def simInit(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque[HlsNetNode], node: "HlsNetNodeWrite", checkPorts:bool=True):
        HlsNetlistSimAgent.simInit(self, sim, state, worklist, node)
        if checkPorts:
            self._checkNodePortsSupported(node,
                                          (node.skipWhen, node.extraCond, node._portSrc),
                                          (node._ready, node._readyNB, node._fullPort))

        if self._enabled:
            en = b1
            full = b0
        else:
            en = b0
            full = b1

        self._updatePortValue(node._ready, en, state, worklist)
        self._updatePortValue(node._readyNB, en, state, worklist)
        self._updatePortValue(node._fullPort, full, state, worklist)

    def simCombStepDataGet(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, n: "HlsNetNodeWrite"):
        assert n._portSrc is not None, n
        return state[n.dependsOn[n._portSrc.in_i]]

    @override
    def simCombStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque[HlsNetNode], n: "HlsNetNodeWrite"):
        """
        Update combinational outputs from inputs and current data
        """
        if self._enabled:
            en = b1
        else:
            en = b0

        self._updatePortValue(n._ready, en, state, worklist)
        self._updatePortValue(n._readyNB, en, state, worklist)

    _getEnableFlags = HlsNetlistSimAgentScalarDriver._getEnableFlags

    @override
    def simSeqStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque[HlsNetNode], n: "HlsNetNodeWrite"):
        """
        If the node is enabled by input signals store input data.
        """
        if not self._enabled:
            return

        sw, ec = self._getEnableFlags(sim, state, n, False)
        if sw:
            if ec:
                # non-blocking write
                d = self.simCombStepDataGet(sim, state, n)
                self.data.append(d)
            else:
                # port dissabled
                pass
        else:
            if ec:
                # blocking write
                d = self.simCombStepDataGet(sim, state, n)
                self.data.append(d)
            else:
                # stall if no space in buffer
                pass


class HlsNetlistSimAgentScalarChannelDriver(HlsNetlistSimAgentScalarDriver):

    @override
    def simInit(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque[HlsNetNode], node: "HlsNetNodeRead"):
        HlsNetlistSimAgent.simInit(self, sim, state, worklist, node)
        self._checkNodePortsSupported(node,
                                      (node.skipWhen, node.extraCond),
                                      (node._portDataOut, node._valid, node._validNB)
                                      )

        self.wordTy = node._portDataOut._dtype
        self.DATA_INVALID = self.wordTy.from_py(None)
        self.data = PeekableDeque(self.data, emptyVal=NOP)

        for o in (node._valid, node._validNB):
            if o is None:
                continue
            state[o] = b0

    @override
    def simSeqStep(self, sim:"HlsNetlistSimulator", state:HlsNetlistSimStateT, worklist:SetDeque[HlsNetNode], n:"HlsNetNodeRead"):
        super().simSeqStep(sim, state, worklist, n, endSimOnUnderflow=False)
        worklist.append(n.associatedWrite)


class HlsNetlistSimAgentScalarChannelMonitor(HlsNetlistSimAgentScalarMonitor):

    @override
    def simInit(self, sim:"HlsNetlistSimulator", state:HlsNetlistSimStateT, worklist:SetDeque[HlsNetNode], node:"HlsNetNodeWrite", checkPorts:bool=True):
        if node.associatedRead not in sim.simHandlerForNode:
            rn = node.associatedRead
            handler = rn.hlsNetlistSimGetHandler(sim)
            handler.simInit(self, state, worklist, rn)
            sim.simHandlerForNode[rn] = handler
            sim.clockDependentNodes.append((rn, handler.simSeqStep))
        super().simInit(sim, state, worklist, node, checkPorts=checkPorts)

    def _getAssociatedReadEn(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, n: "HlsNetNodeWrite"):
        rn = n.associatedRead
        rHandler: HlsNetlistSimAgentScalarChannelDriver = sim.simHandlerForNode[rn]
        rSw, rEc = rHandler._getEnableFlags(sim, state, rn, True)
        return (not rSw and rEc)

    @override
    def simCombStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque[HlsNetNode], n: "HlsNetNodeWrite"):
        """
        Update combinational outputs from inputs and current data
        """
        hasSpace = n._getBufferCapacity() > len(self.data) or self._getAssociatedReadEn(sim, state, n)
        if self._enabled and hasSpace:
            en = b1
            full = b0
        else:
            en = b0
            full = b1

        self._updatePortValue(n._ready, en, state, worklist)
        self._updatePortValue(n._readyNB, en, state, worklist)
        self._updatePortValue(n._fullPort, full, state, worklist)

    _getEnableFlags = HlsNetlistSimAgentScalarDriver._getEnableFlags

    @override
    def simSeqStep(self, sim: "HlsNetlistSimulator", state: HlsNetlistSimStateT, worklist: SetDeque[HlsNetNode], n: "HlsNetNodeWrite"):
        """
        :note: HlsNetlistSimAgentScalarChannelDriver.simSeqStep (read) is always scheduled first
        """
        en = self._enabled
        hasSpace = n._getBufferCapacity() > len(self.data)
        try:
            self._enabled = hasSpace
            HlsNetlistSimAgentScalarMonitor.simSeqStep(self, sim, state, worklist, n)
        finally:
            self._enabled = en
        worklist.append(n.associatedRead)

