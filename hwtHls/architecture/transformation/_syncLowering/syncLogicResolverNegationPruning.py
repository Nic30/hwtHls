from hwt.hdl.operatorDefs import HwtOps
from hwtHls.architecture.transformation._syncLowering.syncLogicHlsNetlistToAbc import SyncLogicHlsNetlistToAbc
from hwtHls.architecture.transformation._syncLowering.syncLogicSearcher import SyncLogicSearcher
from hwtHls.netlist.abc.abcCpp import Abc_Aig_t
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


@staticmethod
def _tryPopNegation(out: HlsNetNodeOut):
    outObj: HlsNetNode = out.obj
    # :note: must not cross clock windows
    # while isinstance(outObj, HlsNetNodeAggregatePortIn):
    #    out = outObj.depOnOtherSide()
    #    outObj = out.obj

    if isinstance(outObj, HlsNetNodeOperator):
        outObj: HlsNetNodeOperator
        if outObj.operator == HwtOps.NOT:
            out = outObj.dependsOn[0]
            outObj = out.obj
            # while isinstance(outObj, HlsNetNodeAggregatePortIn):
            #    out = outObj.depOnOtherSide()
            #    outObj = out.obj
            return out

    return None


def abcPruneNegatedPrimaryInputs(toAbc: SyncLogicHlsNetlistToAbc, syncLogicSearch: SyncLogicSearcher):
    """
    Replace negated primary inputs with a negation (in abc) of original signal
    if it is also a primary input to abc
    """
    net = toAbc.net
    aig: Abc_Aig_t = net.pManFunc

    translationCache = toAbc.translationCache
    primaryInputsReplacedByNegationOf = syncLogicSearch.primaryInputsReplacedByNegationOf
    for outPort, syncNode in syncLogicSearch.primaryInputs:
        if not isinstance(outPort, HlsNetNodeOut):
            # case for flush related forward declared ports
            assert isinstance(outPort, tuple) and len(outPort) == 2 and isinstance(outPort[0], HlsNetNodeWrite), outPort
            continue

        outPortUnNegated = _tryPopNegation(outPort)
        if outPortUnNegated:
            # check if un negated value is primary input
            clkIndex = syncNode[1]
            unNegatedKey = (outPortUnNegated, clkIndex)
            v = translationCache.get(unNegatedKey, None)
            if v is not None:
                # replace primary input for outPort with negation of un negated port
                curKey = (outPort, clkIndex)
                translationCache[curKey] = aig.Not(v)
                primaryInputsReplacedByNegationOf[curKey] = unNegatedKey
