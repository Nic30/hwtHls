from collections import deque

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator, OP_INDEX_CONST
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, \
    HlsNetNodeOut


class HlsNetlistSimulator():

    def __init__(self):
        self.state: dict[HlsNetNodeOutAny, HBitsConst] = {}

    def evalOps(self):
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

    def getStateOf(self, v: HlsNetNodeOut):
        if isinstance(v.obj, HlsNetNodeConst):
            return v.obj.val
        else:
            return self.state[v]
