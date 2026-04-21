from collections import deque
from itertools import chain
from typing import Optional, Union, Callable, Sequence, Generator

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.setDeque import SetDeque
from hwt.pyUtils.setList import SetList
from hwt.simulator.rtlSimulator import BasicRtlSimulatorWithSignalRegisterMethods
from hwtHls.frontend.ioProxy import IoProxy
from hwtHls.frontend.ioProxyScalarHlsNetlistAgent import HlsNetlistSimAgent
from hwtHls.netlist.analysis.hlsNetlistSimHandler import HlsNetlistSimHandler
from hwtHls.netlist.analysis.hlsNetlistSimulatorTypes import HlsNetlistSimScalarInputOrOutputWords, \
    HlsNetlistSimStateT
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.aggregatePorts import HlsNetNodeAggregatePortOut, \
    HlsNetNodeAggregatePortIn
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator, OP_INDEX_CONST
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, \
    HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.analysis.llvmMirInterpretUtils import DictWithSetitemListener
from pyDigitalWaveTools.vcd.writer import VcdWriter, VcdVarWritingScope


class HlsNetlistSimulator():
    """
    Simulator for HlsNetlist which can run scheduled or unscheduled circutio
    and behaves like RTL simulation.
    :ivar stageOfNode: dictionary used for scheduled netlists where each node must
                       check if the stage where node is scheduled is enabled by parent ArchElement controll2
    """

    def __init__(self, netlist: HlsNetlistCtx, args: tuple[HlsNetlistSimScalarInputOrOutputWords, ...]):
        self.netlist = netlist
        self.topIoArgs = args
        self.topIoOrder = netlist.topIoOrder
        self.state: dict[HlsNetNodeOutAny, HBitsConst] = {}
        self.ioNodes: list[tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], IoProxy]] = []
        assert len(netlist.topIoOrder) == len(args), (len(args), netlist.topIoOrder)
        self.simHandlerForNode: dict[Union[HlsNetNodeRead, HlsNetNodeWrite], HlsNetlistSimHandler] = {}
        self.clockDependentNodes: list[tuple[HlsNetNode, Callable[["HlsNetlistSimulator",
                                                                   HlsNetlistSimStateT,
                                                                   SetDeque[HlsNetNode],
                                                                   HlsNetNode], None]]] = []
        self.simAgentForIoProxy: dict[IoProxy, HlsNetlistSimAgent] = {}
        self.dataForChannel: dict[HlsNetNodeWrite, deque[HBitsConst]] = {}
        self.waveLog: Optional[VcdWriter] = None
        self.args = args
        self.timeStep = netlist.normalizedClkPeriod
        self.nowTime = 0
        self.stageOfNode: dict[HlsNetNode, tuple[ArchElement, int]] = {}
        self.flagHasStageControlLowered = netlist.flagHasStageControlLowered
        self.flagIsScheduled = netlist.flagIsScheduled

    @staticmethod
    def _sanitizeNameForWave(name: str) -> str:
        return name.replace(".", "_")

    def installWaveLog(self, waveLog: VcdWriter):
        # print("installWaveLog", waveLog)
        self.waveLog = waveLog
        assert not self.state

        def logToWave(_:dict[HlsNetNodeOut, HConst], o: HlsNetNodeOut, v: HConst):
            if o in waveLog._idScope:
                waveLog.logChange(self.nowTime, o, v, None)

        self.state = DictWithSetitemListener(self.state, logToWave)

    @staticmethod
    def _iterPrimaryInputs(netlist: HlsNetlistCtx, aggregates: SetList[HlsNetNodeAggregate]):
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
            if n._isMarkedRemoved:
                continue

            if isinstance(n, HlsNetNodeAggregate):
                aggregates.append(n)
            elif not n._inputs:
                yield n

    @classmethod
    def HlsNetNode_iterUsersFlat(cls, users: Sequence[HlsNetNodeIn]) -> Generator[[HlsNetNode], None]:
        """
        :returns: iter users and follow HlsNetNodeAggregatePortIn/HlsNetNodeAggregatePortOut and ommit HlsNetNodeAggregate
        """
        for u in users:
            uNode = u.obj
            if isinstance(uNode, HlsNetNodeAggregate):
                inputInside: HlsNetNodeAggregatePortIn = uNode._inputsInside[u.in_i]
                yield inputInside
                yield from cls.HlsNetNode_iterUsersFlat(inputInside.usedBy[0])
            elif isinstance(uNode, HlsNetNodeAggregatePortOut):
                yield uNode
                outerUsers = uNode.dependsOn[u.parentOut.out_i]
                yield from cls.HlsNetNode_iterUsersFlat(outerUsers)
            else:
                yield uNode

    @classmethod
    def _iterHlsNetlistNodesOrdered(cls, netlist: HlsNetlistCtx, aggregates: SetList[HlsNetNodeAggregate], seen: set[HlsNetNode]):
        """
        BFS over netlist from primary inputs
        :attention: ignores
        """
        worklist: SetDeque[HlsNetNode] = SetDeque(cls._iterPrimaryInputs(netlist, aggregates))
        while worklist:
            n: HlsNetNode = worklist.popleft()
            if not all(n2 in seen or n2 is n for n2 in n.iterInDepNodes()):
                continue  # if all predecessors were not seen yet, we have to wait with this node
                # (the predecessor will add this node to worklist again)
                # [todo] use in degree count so we do not need to probe, the problem is that the netlist is multigraph and the node
                #        may have self edge if the ports have compatible schedule
            assert not isinstance(n, (HlsNetNodeAggregate, HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut)), n
            yield n
            seen.add(n)
            for users in n.usedBy:
                worklist.extend(n2 for n2 in cls.HlsNetNode_iterUsersFlat(users) if n2 not in seen)

    def _runReset(self, worklist: SetDeque[HlsNetNode]):
        """
        Collect supplemetary information about netlist and initialize simulator and node states.
        """
        netlist = self.netlist
        state = self.state
        simHandlerForNode = self.simHandlerForNode
        clockDependentNodes = self.clockDependentNodes

        if self.waveLog is not None:
            with self.waveLog.varScope(self._sanitizeNameForWave(netlist.label)) as scope:
                for n in netlist.subNodes:
                    if n._isMarkedRemoved:
                        continue
                    self._registerSignalsInWaveLogger(scope, n)

        if netlist.flagIsScheduled:
            nodes = netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.POSTORDER)
        else:
            aggregates: SetList[HlsNetNodeAggregate] = SetList()
            nodes = self._iterHlsNetlistNodesOrdered(netlist, aggregates, set())
            nodes = chain(nodes, aggregates)

        for n in nodes:
            n: HlsNetNode
            if n._isMarkedRemoved:
                continue
            if n in simHandlerForNode:
                continue

            handler = n.hlsNetlistSimGetHandler(self)
            handler.simInit(self, state, worklist, n)
            simHandlerForNode[n] = handler
            if handler.simSeqStep.__func__ is not HlsNetlistSimHandler.simSeqStep:
                # :attention: if netlist is not scheduled the nodes must be visited
                #             with the order given by partial order from ordering ports defined in netlist
                # :note: HlsNetlistSimHandler.simSeqStep is default implementation which is empty,
                #        that is why it is skipped
                clockDependentNodes.append((n, handler.simSeqStep))

        if self.flagHasStageControlLowered:
            stageOfNode = self.stageOfNode
            for elm in netlist.subNodes:
                elm: ArchElement
                assert isinstance(elm, ArchElement), elm
                for stageI, nodes in elm.iterStages():
                    for n in nodes:
                        stageOfNode[n] = (elm, stageI)

    def _registerSignalsInWaveLogger(self, scope: VcdVarWritingScope, n: HlsNetNode):
        for o in n._outputs:
            t = o._dtype
            if not isinstance(t, HBits):
                continue
            tName, width, formatter = BasicRtlSimulatorWithSignalRegisterMethods.get_trace_formatter(t)
            scope.addVar(o, self._sanitizeNameForWave(o.getPrettyName(addParentId=True)), tName, width, formatter)

        if isinstance(n, HlsNetNodeAggregate) and n.subNodes:
            name = f"n{n._id:d}" if n.name is None else f"n{n._id:d}_{self._sanitizeNameForWave(n.name):s}"
            with scope.varScope(name) as scope1:
                for n1 in n.subNodes:
                    if n1._isMarkedRemoved:
                        continue
                    self._registerSignalsInWaveLogger(scope1, n1)

    def run(self, wallTime: Optional[int]=None):
        worklist: SetDeque[HlsNetNode] = SetDeque()
        self._runReset(worklist)
        state = self.state

        clockDependentNodes = self.clockDependentNodes
        simHandlerForNode = self.simHandlerForNode
        # :note: HlsNetlist is DAG and state dependent on clock
        #     edge is stagged inside of nodes/agents so that is why
        #     there is no stateNext as in typical circuit simulator
        while wallTime is None or self.nowTime < wallTime:
            # print("nowTime: ", self.nowTime, [n._id for n in worklist])

            # Evaluate logic which does not depend on clock signal edge (combinational logic)
            while worklist:
                n = worklist.popleft()
                if n._isMarkedRemoved:
                    continue
                simHandlerForNode[n].simCombStep(self, state, worklist, n)

            # call IO agents to update its outputs
            for n, handler in clockDependentNodes:
                n: Union[HlsNetNodeRead, HlsNetNodeWrite]
                # :attention: simSeqStep should never update values of outputs, it should update only internal state of node
                #   and add node to worklist if state changed to update values of outputs
                handler(self, state, worklist, n)

            # call IO agents to capture its inputs or produce clk depenent state updates
            self.nowTime += self.timeStep

    def evalExpr(self):
        state = self.state
        worklist = SetList()
        for o in self.state.keys():
            worklist.extend(o.obj.iterOutUserNodes())
        worklist: deque[HlsNetNode] = deque(worklist)
        while worklist:
            n = worklist.popleft()
            if not isinstance(n, HlsNetNodeOperator):
                continue  # not the node of interest
            n: HlsNetNodeOperator
            assert len(n._outputs) == 1
            o = n._outputs[0]
            if o in state:
                continue  # already resolved

            deps = []
            allInKnown = True
            for dep in n.dependsOn:
                v = state.get(dep)
                if v is None:
                    if isinstance(dep.obj, HlsNetNodeConst):
                        v = dep.obj.val
                        state[dep] = v
                    else:
                        worklist.append(dep.obj)
                        allInKnown = False
                        break
                deps.append(v)

            if not allInKnown:
                # all inputs not known yet, will be put in worklist again once some input is resolved
                continue
            op = n.operator
            if op == OP_INDEX_CONST:
                assert len(deps) == 1
                res = deps[0][n.operatorSpecialization]
            else:
                if op == HwtOps.CONCAT:
                    deps = reversed(deps)
                assert n.operator._evalFn is not None, n.operator
                res = n.operator._evalFn(*deps)
            state[o] = res
            # print(o, res)
            worklist.extend(n.iterOutUserNodes())

    def getStateOf(self, v: HlsNetNodeOut) -> HConst:
        if isinstance(v.obj, HlsNetNodeConst):
            return v.obj.val
        else:
            return self.state[v]
