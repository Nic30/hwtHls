from itertools import chain, islice
from typing import Set, Generator, Tuple, Literal, Optional, Sequence, List, \
    Union, Dict

from hwt.code import Concat
from hwt.hdl.operatorDefs import AllOps, OpDefinition, COMPARE_OPS, CAST_OPS
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.abc.abcAigToHlsNetlist import AbcAigToHlsNetlist
from hwtHls.netlist.abc.hlsNetlistToAbcAig import HlsNetlistToAbcAig
from hwtHls.netlist.abc.optScripts import abcCmd_resyn2, abcCmd_compress2
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, \
    HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    link_hls_nodes
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from pyMathBitPrecise.bit_utils import get_bit, mask
from hwtHls.architecture.connectionsOfStage import extractControlSigOfInterfaceTuple
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.nodes.loopHeader import HlsLoopGate


def iter1and0sequences(v: BitsVal) -> Generator[Tuple[Literal[1, 0], int], None, None]:
    """
    :note: same as ConstBitPartsAnalysisContext::iter1and0sequences
    :note: lower first
    :returns: generators of tuples in format 0/1, width
    """
    # if the bit in c is 0 the output bit should be also 0 else it is bit from v
    l_1: int = -1  # start of 1 sequence, -1 as invalid value
    l_0: int = -1  # start of 0 sequence, -1 as invalid value
    endIndex = v._dtype.bit_length() - 1
    if not v._is_full_valid():
        raise NotImplementedError(v)
    _v = v.val
    for h in range(endIndex + 1):
        curBit = get_bit(_v, h)
        if l_1 == -1 and curBit:
            l_1 = h  # start of 1 sequence
        elif l_0 == -1 and not curBit:
            l_0 = h  # start of 0 sequence

        last = h == endIndex
        if l_1 != -1 and (last or not get_bit(_v, h + 1)):
            # end of 1 sequence found
            w = h - l_1 + 1
            yield (1, w)
            l_1 = -1  # reset start
        elif l_0 != -1 and (last or get_bit(_v, h + 1)):
            # end of 0 sequence found
            w = h - l_0 + 1
            yield (0, w)
            l_0 = -1  # reset start


def isAll0OrAll1(v: BitsVal):
    vInt = int(v)
    return vInt == 0 or vInt == mask(v._dtype.bit_length())

    
class HlsNetlistPassSimplify(HlsNetlistPass):
    """
    Hls netlist simplification:

    * DCE
    * reduce HlsNetNodeMux with a single input
        * merge HlsNetNodeMux if child mux has parent as only user
    * reduce and/or/xor
    * remove HlsNetNodeExplicitSync (and subclasses like HlsNetNodeRead,HlsNetNodeWrite) skipWhen and extraCond connected to const  
    """
    REST_OF_EVALUABLE_OPS = {AllOps.CONCAT, AllOps.ADD, AllOps.SUB, AllOps.DIV, AllOps.MUL, AllOps.INDEX, *COMPARE_OPS, *CAST_OPS}
    OPS_AND_OR_XOR = (AllOps.AND, AllOps.OR, AllOps.XOR)
    NON_REMOVABLE_CLS = (HlsNetNodeRead, HlsNetNodeWrite, HlsLoopGate, HlsNetNodeExplicitSync)

    def apply(self, hls:"HlsScope", netlist: HlsNetlistCtx):
        threads: HlsNetlistAnalysisPassDataThreads = netlist.getAnalysis(HlsNetlistAnalysisPassDataThreads)
        worklist: UniqList[HlsNetNode] = UniqList(netlist.iterAllNodes())
        removed: Set[HlsNetNode] = set()
        builder = netlist.builder
        firstTime = True
        while True:
            # [todo] it would be more beneficial to use worklist as FIFO because we want to first run DCE and more complex reductions later 
            didModifyExpr = False  # flag which is True if we modified some expression and the ABC should be run
            while worklist:
                n = worklist.pop()
                if n in removed:
                    continue

                if self._isTriviallyDead(n):
                    builder.unregisterNode(n)
                    self._disconnectAllInputs(n, worklist)
                    removed.add(n)
                    continue
                    
                if isinstance(n, HlsNetNodeOperator):
                    n: HlsNetNodeOperator
                    o = n.operator
                    if isinstance(n, HlsNetNodeMux):
                        if self._reduceMux(n, worklist, removed):
                            didModifyExpr = True
                            continue

                    elif o == AllOps.NOT:
                        if self._reduceNot(n, worklist, removed):
                            didModifyExpr = True
                            continue
                
                    elif o in self.OPS_AND_OR_XOR:
                        if self._reduceAndOrXor(n, worklist, removed):
                            didModifyExpr = True
                            continue

                    elif o in self.REST_OF_EVALUABLE_OPS:
                        c0 = self._getConstDriverOf(n._inputs[0])
                        if c0 is None:
                            continue
                        if len(n._inputs) == 1:
                            v = o._evalFn(c0)
                        else:
                            c1 = self._getConstDriverOf(n._inputs[1])
                            if c1 is None:
                                continue
                            
                            if o == AllOps.CONCAT:
                                v = Concat(c1, c0)
                            else:
                                v = o._evalFn(c0, c1)

                        self._replaceOperatorNodeWith(n, builder.buildConst(v), worklist, removed)
                        didModifyExpr = True
                        continue

                elif isinstance(n, HlsNetNodeExplicitSync):
                    n: HlsNetNodeExplicitSync
                    if n.skipWhen is not None:
                        dep = n.dependsOn[n.skipWhen.in_i]
                        if isinstance(dep.obj, HlsNetNodeConst):
                            assert int(dep.obj.val) == 0, ("Constant skipWhen condition must be 0 because otherwise this is should not be used at all", n, dep.obj)
                            dep.obj.usedBy[dep.out_i].remove(n.skipWhen)
                            worklist.append(dep.obj)
                            n._removeInput(n.skipWhen.in_i)
                            n.skipWhen = None
                        
                    if n.extraCond is not None:
                        dep = n.dependsOn[n.extraCond.in_i]
                        if isinstance(dep.obj, HlsNetNodeConst):
                            assert int(dep.obj.val) == 1, ("Constant extraCond must be 1 because otherwise this is should not be used at all", n, dep.obj)
                            dep.obj.usedBy[dep.out_i].remove(n.extraCond)
                            worklist.append(dep.obj)
                            n._removeInput(n.extraCond.in_i)
                            n.extraCond = None
                            
                    # remove ordering if it is redundant information
    #                for orderingI in tuple(n.iterOrderingInputs()):
    #                    orderingI: HlsNetNodeIn
    #                    t0 = threads.threadPerNode[n]
    #                    dep = n.dependsOn[orderingI.in_i]
    #                    t1 = threads.threadPerNode[dep.obj]
    #                    if t0 is t1:
    #                        if isinstance(n, HlsNetNodeRead) and isinstance(dep.obj, HlsNetNodeRead):
    #                            n: HlsNetNodeRead
    #                            if n.src is dep.obj.src:
    #                                # can not ignore order of reads from same volatile source
    #                                continue
    #                        elif isinstance(n, HlsNetNodeWrite) and isinstance(dep.obj, HlsNetNodeWrite):
    #                            n: HlsNetNodeWrite
    #                            if n.dst is dep.obj.dst:
    #                                # can not ignore order of writes to same volatile destination
    #                                continue
    #
    #                        # [todo] instead of simple removal we should transitively check if we should reconnnect to some parent node
    #                        dep.obj.usedBy[dep.out_i].remove(orderingI)
    #                        n._removeInput(orderingI.in_i)
    
                    if n.__class__ is HlsNetNodeExplicitSync:
                        n: HlsNetNodeExplicitSync
                        # remove whole node if not synchronizing anything
                        if not n.usedBy[0]:
                            if self._isHlsNetNodeExplicitSyncFlagsRequred(n):
                                continue
                            for i in n._inputs:
                                dep = n.dependsOn[i.in_i]
                                dep.obj.usedBy[dep.out_i].remove(i)
                                worklist.append(dep.obj)
                            
                            removed.add(n)
                            continue

                        elif self._getConstDriverOf(n._inputs[0]) is not None and all(not use for use in islice(n.usedBy, 1, None)):
                            for _ in range(len(n.usedBy) - 1):
                                n.usedBy.pop()
                                n._outputs.pop()
                            if n._associatedReadSync is not None:
                                raise NotImplementedError(n)

                            self._replaceOperatorNodeWith(n, n.dependsOn[0], worklist, removed)
                            didModifyExpr = True
                            continue

                        elif (n.skipWhen is None or self._getConstDriverOf(n.skipWhen) is not None) and (n.skipWhen is None or self._getConstDriverOf(n.skipWhen) is not None):
                            # synchronization node without any synchronization flag specified
                            _, orderingOutUses = n._outputs.pop(), n.usedBy.pop()
                            if orderingOutUses:
                                for orderingIn in n.iterOrderingInputs():
                                    orderingDep = n.dependsOn[orderingIn.in_i]
                                    for u in orderingOutUses:
                                        u: HlsNetNodeIn
                                        u.replaceDriverInInputOnly(orderingDep)
                                 
                            self._replaceOperatorNodeWith(n, n.dependsOn[0], worklist, removed)
                            didModifyExpr = True
                            continue

                elif isinstance(n, HlsNetNodeReadSync):
                    # rm this if the source data is constant
                    if self._getConstDriverOf(n._inputs[0]):
                        self._replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist, removed)
                        didModifyExpr = True
                        continue
                    # rm this if the source object does not have sync
                    dep = n.dependsOn[0].obj
                    if isinstance(dep, HlsNetNodeRead):
                        dep: HlsNetNodeRead
                        vld, _ = extractControlSigOfInterfaceTuple(dep.src)
                        if isinstance(vld, int):
                            assert vld == 1, (dep, vld)
                            self._replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist, removed)
                            didModifyExpr = True
                            continue
                            
                    elif isinstance(dep, HlsNetNodeRead):
                        _, rd = extractControlSigOfInterfaceTuple(dep.src)
                        if isinstance(rd, int):
                            assert rd == 1, (dep, vld)
                            self._replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist, removed)
                            didModifyExpr = True
                            continue

            if firstTime or didModifyExpr:
                self._runAbcControlpathOpt(netlist.builder, worklist, removed, netlist.iterAllNodes())
                firstTime = False
            
            if not worklist:
                break 
                
        if removed:
            # HlsNetlistPassConsystencyCheck().apply(hls, netlist)
            nodes = netlist.nodes
            netlist.nodes = [n for n in nodes if n not in removed]
            HlsNetlistPassConsystencyCheck().apply(hls, netlist)

    @classmethod
    def _collect1bOpTree(cls, o: HlsNetNodeOut, inputs: UniqList[HlsNetNodeOut], inTreeOutputs: Set[HlsNetNodeOut]):
        """
        Collect tree of 1b operators ending from specified output

        :returns: True if it is a non trivial output (output is trivial if driven by const or non-translated node,
            if the output is trivial it can not be optimized further)
        """
        if o in inTreeOutputs:
            # already discovered
            return True

        obj: HlsNetNode = o.obj
        if isinstance(obj, HlsNetNodeConst):
            return False

        elif isinstance(obj, HlsNetNodeOperator):
            if obj.dependsOn[0]._dtype.bit_length() == 1:
                for i in obj.dependsOn:
                    cls._collect1bOpTree(i, inputs, inTreeOutputs)
                    inTreeOutputs.add(i)
                return True

        inputs.append(o)
        return False
        
    def _runAbcControlpathOpt(self, builder: HlsNetlistBuilder, worklist: UniqList[HlsNetNode],
                              removed: Set[HlsNetNode], allNodeIt: Sequence[HlsNetNode]):
        """
        Run berkeley-ABC to optimize control path.
        """
        inputs: UniqList[HlsNetNodeOut] = []
        inTreeOutputs: Set[HlsNetNodeOut] = set()
        outputs: List[HlsNetNodeOut] = []
        outputsSet: Set[HlsNetNodeOut] = set()
        _collect = self._collect1bOpTree

        def collect(n: HlsNetNode, i: HlsNetNodeIn):
            o = n.dependsOn[i.in_i]
            if o not in outputsSet and _collect(o, inputs, inTreeOutputs):
                # it may be the case that this is just wire and can not be optimized further
                # from this reason we do not add it to collected outputs
                outputsSet.add(o)
                outputs.append(o)
            
        for n in allNodeIt:
            n: HlsNetNode
            if isinstance(n, HlsNetNodeExplicitSync):
                n: HlsNetNodeExplicitSync
                if n.extraCond is not None:
                    collect(n, n.extraCond)
                if n.skipWhen is not None:
                    collect(n, n.skipWhen)
            elif isinstance(n, HlsNetNodeMux):
                for _, c in n._iterValueConditionInputPairs():
                    if c is not None:
                        collect(n, c)
        if outputs:
            toAbcAig = HlsNetlistToAbcAig()
            outputs = [o for o in outputs if o not in inTreeOutputs]
            abcFrame, abcNet, abcAig = toAbcAig.translate(inputs, outputs)
            abcAig.Cleanup()

            abcNet = abcCmd_resyn2(abcNet)
            abcNet = abcCmd_compress2(abcNet)

            toHlsNetlist = AbcAigToHlsNetlist(abcFrame, abcNet, abcAig, builder)
            newOutputs = toHlsNetlist.translate()
            assert len(outputs) == len(newOutputs)
            anyChangeSeen = False
            for o, newO in zip(outputs, newOutputs):
                if o is not newO:
                    if isinstance(newO, HValue):
                        newO = builder.buildConst(newO)
                    builder.replaceOutput(o, newO)
                    # we can remove "o" immediately because its parent node may have multiple outputs
                    worklist.append(newO.obj)
                    anyChangeSeen = True

            if anyChangeSeen:
                worklist.extend(o.obj for o in inTreeOutputs)
                worklist.extend(o.obj for o in outputs)
            abcFrame.DeleteAllNetworks()

    def _isHlsNetNodeExplicitSyncFlagsRequred(self, n: HlsNetNodeExplicitSync) -> bool:
        if n.extraCond is not None:
            c = self._getConstDriverOf(n.extraCond)
            if c is None or int(c) != 1:
                if n.skipWhen is not None:
                    c = self._getConstDriverOf(n.skipWhen)
                    if c is not  None and int(c) == 1:
                        # always skipped extraCond does not matter
                        return False
                    else:
                        # not always skipped with some extraCond, can not remove
                        return True
                else:
                    # not always skipped with some extraCond, can not remove
                    return True
        return False
     
    def _getConstDriverOf(self, inputObj: HlsNetNodeIn) -> Optional[HValue]:
        dep = inputObj.obj.dependsOn[inputObj.in_i]
        if isinstance(dep.obj, HlsNetNodeConst):
            return dep.obj.val
        else:
            return None

    def _disconnectAllInputs(self, n: HlsNetNode, worklist: UniqList[HlsNetNode]):
        for i, dep in zip(n._inputs, n.dependsOn):
            i: HlsNetNodeIn
            dep: HlsNetNodeOut
            # disconnect driver from self
            dep.obj.usedBy[dep.out_i].remove(i)
            worklist.append(dep.obj)

    def _replaceOperatorNodeWith(self, n: HlsNetNodeOperator, newO: HlsNetNodeOut,
                                 worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        assert len(n.usedBy) == 1, (n, "implemented only for single output nodes")
        builder: HlsNetlistBuilder = n.netlist.builder
        self._addAllUsersToWorklist(worklist, n)
        builder.replaceOutput(n._outputs[0], newO)
        self._disconnectAllInputs(n, worklist)
        removed.add(n)

    def _addAllUsersToWorklist(self, worklist: UniqList[HlsNetNode], n: HlsNetNodeOperator):
        for uses in n.usedBy:
            for u in uses:
                worklist.append(u.obj)

    def _isTriviallyDead(self, n: HlsNetNode):
        if isinstance(n, self.NON_REMOVABLE_CLS):
            return False
        else:
            for uses in n.usedBy:
                if uses:
                    return False
            return True

    def _reduceMux(self, n: HlsNetNodeMux, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        if len(n._inputs) == 1:
            # mux x = x
            i: HlsNetNodeOut = n.dependsOn[0]
            self._replaceOperatorNodeWith(n, i, worklist, removed)
            return True

        # resolve constant conditions
        newOps = []
        for (v, c) in n._iterValueConditionDriverPairs():
            if c is not None and isinstance(c.obj, HlsNetNodeConst):
                if c.obj.val:
                    newOps.append(v)
                    break
            else:
                newOps.append(v)
                if c is not None:
                    newOps.append(c)

        if len(newOps) != len(n._inputs):
            if len(newOps) == 1:
                i: HlsNetNodeOut = newOps[0]
            else:
                i = n.netlist.builder.buildMux(n._outputs[0]._dtype, tuple(newOps))

            self._replaceOperatorNodeWith(n, i, worklist, removed)
            return True

        # merge mux to only user which is mux if this is the case and it is possible
        if len(n._inputs) % 2 == 1:
            assert len(n._outputs) == 1, n
            if len(n.usedBy[0]) == 1:
                u: HlsNetNodeIn = n.usedBy[0][0]
                if isinstance(u.obj, HlsNetNodeMux) and len(u.obj._inputs) % 2 == 1:
                    # if u.in_i == 0:
                    #    raise NotImplementedError()
                    # el
                    if u.in_i == len(u.obj._inputs) - 1:
                        newOps = u.obj.dependsOn[:-1] + n.dependsOn
                        res = n.netlist.builder.buildMux(n._outputs[0]._dtype, tuple(newOps))
                        self._replaceOperatorNodeWith(u.obj, res, worklist, removed)
                        self._disconnectAllInputs(n, worklist)
                        removed.add(n)
                        return True
            
        return False

    def _reduceNot(self, n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        builder: HlsNetlistBuilder = n.netlist.builder
        o0, = n.dependsOn
        o0Const = isinstance(o0.obj, HlsNetNodeConst)
        newO = None
        if o0Const:
            newO = builder.buildConst(~o0.obj.val)
        elif isinstance(o0, HlsNetNodeOut) and isinstance(o0.obj, HlsNetNodeOperator) and o0.obj.operator == AllOps.NOT:
            # ~~x = x
            newO = o0.obj.dependsOn[0]
        
        if newO is not None:
            self._replaceOperatorNodeWith(n, newO, worklist, removed)
            return True

        return False

    def _reduceAndOrXor(self, n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        builder: HlsNetlistBuilder = n.netlist.builder
        # search for const in for commutative operator
        o0, o1 = n.dependsOn
        o0Const = isinstance(o0.obj, HlsNetNodeConst)
        o1Const = isinstance(o1.obj, HlsNetNodeConst)
        newO = None

        if o0Const and not o1Const:
            # make sure const is o1 if const is in operands
            o0, o1 = o1, o0
            o0Const = False
            o1Const = True

        if n.operator == AllOps.AND:
            if o0Const and o1Const:
                newO = builder.buildConst(o0.obj.val & o1.obj.val)

            elif o1Const:
                # to concatenation of o0 bits and 0s after const mask is applied 
                if isAll0OrAll1(o1.obj.val):
                    if int(o1.obj.val):
                        # x & 1 = x
                        newO = o0
                    else:
                        # x & 0 = 0
                        newO = builder.buildConstPy(o0._dtype, 9)

                else:
                    concatMembers = []
                    offset = 0
                    for bitVal, width in iter1and0sequences(o1.obj.val):
                        if bitVal:
                            # x & 1 = x
                            v0 = builder.buildIndexConstSlice(Bits(width), o0, offset + width, offset)
                        else:
                            # x & 0 = 0
                            v0 = builder.buildConstPy(Bits(width), 0)

                        concatMembers.append(v0)
                            
                        offset += width
                    newO = builder.buildConcatVariadic(tuple(concatMembers))

            elif o0 == o1:
                # x & x = x
                newO = o0

        elif n.operator == AllOps.OR:
            if o0Const and o1Const:
                newO = builder.buildConst(o0.obj.val | o1.obj.val)

            elif o1Const:
                if isAll0OrAll1(o1.obj.val):
                    if int(o1.obj.val):
                        # x | 1 = 1
                        newO = builder.buildConst(o0._dtype.from_py(mask(o0._dtype.bit_length())))
                    else:
                        # x | 0 = x
                        newO = o0

                else:
                    concatMembers = []
                    offset = 0
                    for bitVal, width in iter1and0sequences(o1.obj.val):
                        if bitVal:
                            # x | 1 = 1
                            v0 = builder.buildConst(Bits(width).from_py(mask(width)))
                        else:
                            # x | 0 = x
                            v0 = builder.buildIndexConstSlice(Bits(width), o0, offset + width, offset)

                        concatMembers.append(v0)
                            
                        offset += width
                    newO = builder.buildConcatVariadic(tuple(concatMembers))

            elif o0 == o1:
                # x | x = x
                newO = o0

        elif n.operator == AllOps.XOR:
            if o0Const and o1Const:
                newO = builder.buildConst(o0.obj.val ^ o1.obj.val)

            elif o1Const:
                # perform reduction by constant
                if isAll0OrAll1(o1.obj.val):
                    if int(o1.obj.val):
                        # x ^ 1 = ~x
                        newO = builder.buildNot(o0)
                    else:
                        # x ^ 0 = x
                        newO = o0
                else:
                    concatMembers = []
                    offset = 0
                    for bitVal, width in iter1and0sequences(o1.obj.val):
                        v0 = builder.buildIndexConstSlice(Bits(width), o0, offset + width, offset)
                        if bitVal:
                            v0 = builder.buildNot(v0)
                        concatMembers.append(v0)
                        offset += width

                    newO = builder.buildConcatVariadic(tuple(concatMembers))
            
            elif o0 == o1:
                # x ^ x = 0
                newO = builder.buildConst(o0._dtype.from_py(0))
            
        if newO is not None:
            self._replaceOperatorNodeWith(n, newO, worklist, removed)
            return True

        return False
