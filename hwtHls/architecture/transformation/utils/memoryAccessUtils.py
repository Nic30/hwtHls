from hwt.constants import READ, WRITE
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic
from hwtHls.architecture.transformation.utils.syncUtils import insertDummyWriteToImplementSync
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchElementTermPropagationCtx
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.io.bram import HlsNetNodeWriteBramCmd
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementNoImplicitSync import ArchElementNoImplicitSync
from hwtHls.netlist.nodes.readIndexed import HlsNetNodeReadIndexed
from hwtHls.netlist.nodes.writeIndexed import HlsNetNodeWriteIndexed


def detectReadModifyWrite(alu: ArchElement, ram: IoProxyAddressed):
    """
    :note: in rClkI the data read just started, it may finish later
    :note: in wClkI the data write just started, it may finish later
    """
    # detect read modify write
    r = None
    rClkI = None
    w = None
    wClkI = None
    for clkI, nodes in alu.iterStages():
        for n in nodes:
            if isinstance(n, HlsNetNodeWriteBramCmd):
                if n.dst in ram.interface:
                    if n.cmd == READ:
                        assert r is None or r is n, (r, n)
                        if r is None:
                            r = n
                            rClkI = clkI
                    else:
                        assert n.cmd == WRITE, n
                        assert w is None or w is n, (w, n)
                        if w is None:
                            w = n
                            wClkI = clkI

    assert r is not None
    assert w is not None
    r: HlsNetNodeReadIndexed
    w: HlsNetNodeWriteIndexed
    # discover stages which may contain loaded data
    # implement stall if data is loaded in stage and address matches the address in first stage with read
    assert len(r.indexes) == 1, r
    assert len(w.indexes) == 1, w
    rAddr = r.dependsOn[r.indexes[0].in_i]
    wAddr = w.dependsOn[w.indexes[0].in_i]
    assert rAddr is wAddr, ("This was supposed to be read-modify-write")
    return rClkI, r, wClkI, w, rAddr


def ArchImplementStaling(netlist: HlsNetlistCtx, ram: IoProxyAddressed):
    assert len(netlist.nodes) == 1, "Expected just 1 pipeline with ReadModifyWrite"
    alu: ArchElement = netlist.nodes[0]
    rClkI, _, wClkI, _, rAddr = detectReadModifyWrite(alu, ram)
    # create an element to store stalling logic
    stallLogicElm = ArchElementNoImplicitSync.createEmptyScheduledInstance(netlist, "stallingForRam")
    tpc = ArchElementTermPropagationCtx({}, stallLogicElm, {})
    builder: HlsNetlistBuilder = stallLogicElm.builder
    # the schedule may be different

    hasNoAddrColision = None
    newReadAddres = tpc.propagate((alu, rClkI), rAddr, "ramNewAdr")
    for clkI in range(rClkI + 1, wClkI + 1):
        # propagate addr to stallLogicElm, if this is not first stage propagate also stageRegValid
        vld = tpc.getStageEn((alu, clkI))
        addr = tpc.propagate((alu, clkI), rAddr, f"ramAddrPrev{clkI - rClkI - 1:d}")
        _hasNoAddrColision = builder.buildOr(builder.buildNot(vld), builder.buildNe(newReadAddres, addr))
        hasNoAddrColision = builder.buildAndOptional(hasNoAddrColision, _hasNoAddrColision)

    scheduleUnscheduledControlLogic((stallLogicElm, rClkI), hasNoAddrColision)
    syncTime = netlist.normalizedClkPeriod * (rClkI + 1) - netlist.scheduler.epsilon
    sync, dummyVal = insertDummyWriteToImplementSync(alu, syncTime, "addrColisionStall")
    sync._rtlUseReady = sync._rtlUseValid = False
    _hasNoAddrColision = tpc.propagateFromDstElm((alu, rClkI), hasNoAddrColision, "hasNoAddrColision")
    sync.addControlSerialExtraCond(_hasNoAddrColision, addDefaultScheduling=True)


def ArchImplementWriteForwarding(netlist: HlsNetlistCtx, ram: IoProxyAddressed):
    assert len(netlist.nodes) == 1, "Expected just 1 pipeline with ReadModifyWrite"
    alu: ArchElement = netlist.nodes[0]
    rClkI, r, wClkI, w, rAddr = detectReadModifyWrite(alu, ram)
    # create an element to store write forwarding logic
    stallLogicElm = ArchElementNoImplicitSync.createEmptyScheduledInstance(netlist, "writeForwardingForRam")
    tpc = ArchElementTermPropagationCtx({}, stallLogicElm, {})
    builder: HlsNetlistBuilder = stallLogicElm.builder
    # the schedule may be different

    # if same data is loaded while previous version is not stored yet
    # we have to propagate not yet stored version as a new read data

    # if the latency of operation is longer than 1 cycle, we have to generate more ALUs which compute multiple inputs at once
    if wClkI - rClkI > 1:
        raise NotImplementedError()

