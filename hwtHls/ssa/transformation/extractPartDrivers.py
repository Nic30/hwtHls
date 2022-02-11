from itertools import chain
from typing import List, Tuple, Set, Sequence, Union, Dict, Callable, Optional

from hwt.hdl.operatorDefs import AllOps, CAST_OPS, BITWISE_OPS
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import SLICE
from hwt.hdl.types.slice import HSlice
from hwt.hdl.value import HValue
from hwt.pyUtils.arrayQuery import balanced_reduce
from hwt.pyUtils.uniqList import UniqList
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.exprBuilder import SsaExprBuilder
from hwtHls.ssa.instr import SsaInstr, OP_ASSIGN, SsaInstrBranch
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtHls.ssa.transformation.utils.concatOfSlices import ConcatOfSlices
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.value import SsaValue


class VarBitSegmentDriverInfo():
    """
    :ivar range_to_self, range_from_src: in the format of high,low
    """
    __slots__ = ["src_var", "ranges_to_self", "range_from_src"]

    def __init__(self, src_var: SsaValue, range_to_self: Tuple[int, int], range_from_src: Tuple[int, int]):

        self.src_var = src_var
        self.ranges_to_self = range_to_self
        self.range_from_src = range_from_src

    def __repr__(self):
        return (
            f"<{self.__class__.__name__:s} [{self.ranges_to_self[0]}:{self.ranges_to_self[1]}] ="
            f" {self.src_var}[{self.range_from_src[0]}:{self.range_from_src[1]}]>"
        )


class VarBitSegmentEndpointInfo():
    """
    :ivar range_to_self, range_from_src: in the format of high,low
    """
    __slots__ = ["dst_var", "range_from_self", "range_to_dst"]

    def __init__(self, dst_var: SsaValue, range_in_self: Tuple[int, int], range_to_dst: Tuple[int, int]):
        self.dst_var = dst_var
        self.range_from_self = range_in_self
        self.range_to_dst = range_to_dst

    def __repr__(self):
        return (
            f"<{self.__class__.__name__:s} {self.dst_var}[{self.range_to_dst[0]}:{self.range_to_dst[1]}] ="
            f" [{self.range_from_self[0]}:{self.range_from_self[1]}]>"
        )


class VarBitSegments():
    __slots__ = ["var", "driver_ranges", "endpoint_ranges"]

    def __init__(self, var: SsaValue):
        self.var = var
        self.driver_ranges: List[VarBitSegmentDriverInfo] = []
        self.endpoint_ranges: List[VarBitSegmentEndpointInfo] = []


class SsaPassExtractPartDrivers(SsaPass):
    """
    Split parts of bit vectors so each segment has an unique variable.

    :note: equivalent of :class:`hwt.synthesizer.rtlLevel.extract_part_drivers.RtlNetlistPassExtractPartDrivers`

    .. code-block::

        s = 0b00
        s[0] = x
        s[1] = y

        # ssa
        sv0 = 0b00
        sv1 = Concat(sv0[1], x)
        sv2 = Concat(y, sv0[0])

        # ssa after this transformation applied
        sv0 = Concat(y, x)


    The input code.

    .. code-block:: python

        s <= 0b00
        if c0:
            s[0] = x
        if c1:
            s[1] = y


    Approximate SSA representation of previous input code.

    .. code-block:: text

        sv0 = 0b00
        br c0, ifc0.then, ifc0.end
        @if0.then:
            sv1 = Concat(sv0[1], x)
        @ifc0.end:

        sv2 = phi sv1 @if0.then, sv0 @ifc0.end
        br c1 ifc1.then, ifc1.end
        @ifc1.then:
            sv3 = Concat(y, sv2[0])
        @ifc1.end:
        sv4 = phi sv3 @if1.then, sv2 @ifc1.end


    The code after this transformation was applied.

    .. code-block:: python

        s_0_tmp = 0;
        s_1_tmp = 0;
        if c0:
            s_0_tmp = x
        if c1:
            s_1_tmp = y
        s = Concat(s_1_tmp, s_0_tmp)

    Approximate SSA representation of previous output code.
    :note: In reality all variables from original code do remain but they are unused
    as the variables were transitively replaced for each user.

    .. code-block:: text

        s_0_tmp_0 = 0
        s_1_tmp_0 = 1
        br c0, ifc0.then, ifc0.end
        @if0.then:
        @ifc0.end:
        s_0_tmp_1 = phi x @if0.then, s_0_tmp_0 @ifc0.end

        br c1 ifc1.then, ifc1.end
        @ifc1.then:
        @ifc1.end:
        s_1_tmp_1 = phi y @if1.then, s_1_tmp_0 @ifc1.end

        s = Concat(s_1_tmp_1, s_0_tmp_1)

    """

    def _register_var_load(self, dst: SsaValue, src: Union[SsaValue, HValue]):
        dst_segments, dst = self._get_var_segments(dst)
        dst_range = (dst._dtype.bit_length(), 0)
        src_segments, src = self._get_var_segments(src)
        src_range = (src._dtype.bit_length(), 0)
        if not isinstance(src, HValue):
            src_segments.endpoint_ranges.append(VarBitSegmentEndpointInfo(dst, src_range, dst_range))
        dst_segments.driver_ranges.append(VarBitSegmentDriverInfo(src, dst_range, src_range))

    def _get_var_segments(self, var: SsaValue):
        if not isinstance(var, SsaValue):
            return None, var

        segments = self.var_segments.get(var, None)
        if segments is None:
            segments = VarBitSegments(var)
            self.var_segments[var] = segments

        return segments, var

    def _register_var_load_from_concat(self, dst: SsaValue, srcs: List[Union[SsaValue, HValue]]):
        dst_segments, dst = self._get_var_segments(dst)
        dst_offset = 0
        for src in srcs:
            src_segments, src = self._get_var_segments(src)
            src_width = src._dtype.bit_length()
            src_range = (src_width, 0)
            dst_range = (src_width + dst_offset, dst_offset)
            if isinstance(src, SsaValue):
                src_segments.endpoint_ranges.append(VarBitSegmentEndpointInfo(dst, src_range, dst_range))
            dst_segments.driver_ranges.append(VarBitSegmentDriverInfo(src, dst_range, src_range))
            dst_offset += src_width

        assert dst_offset == dst._dtype.bit_length(), (dst, dst_offset, dst._dtype.bit_length())

    def _register_var_load_from_slice(self,
                                      dst: SsaValue, src: Union[SsaValue, HValue],
                                      indexes: Sequence[Union[SsaValue, HValue], ]):
        dst_segments, dst = self._get_var_segments(dst)
        dst_range = dst._dtype.bit_length(), 0
        src_segments, src = self._get_var_segments(src)
        if len(indexes) != 1:
            raise NotImplementedError("This is intended to use for bit vectors only")
        i = indexes[0]
        if isinstance(i, HValue):
            if isinstance(i._dtype, Bits):
                src_low = int(i)
                src_range = src_low + 1, src_low
            else:
                assert isinstance(i._dtype, HSlice), i
                assert int(i.val.step) == -1, i
                src_range = int(i.val.start), int(i.val.stop)
            if not isinstance(src, HValue):
                src_segments.endpoint_ranges.append(VarBitSegmentEndpointInfo(dst, src_range, dst_range))
            dst_segments.driver_ranges.append(VarBitSegmentDriverInfo(src, dst_range, src_range))
        else:
            raise NotImplementedError("Mux described by indexing on bit vector")

    def _collect_indexes_on_variables(self, blocks: List[SsaBasicBlock]):
        for block in blocks:
            for phi in block.phis:
                phi: SsaPhi
                for (src, _) in phi.operands:
                    self._register_var_load(phi, src)

            for stm in block.body:
                if isinstance(stm, SsaInstr):
                    stm: SsaInstr
                    op, args = stm.operator, stm.operands
                    if op in CAST_OPS:
                        assert len(args) == 1
                        a = args[0]
                        if isinstance(a, HlsStreamProcRead):
                            continue
                        assert isinstance(a, (SsaValue, HValue)), (a, a.__class__, stm)
                        self._register_var_load(stm, a)
                    elif op is AllOps.INDEX:
                        self._register_var_load_from_slice(stm, args[0], args[1:])
                    elif op is AllOps.CONCAT:
                        self._register_var_load_from_concat(stm, args)
                    elif op in BITWISE_OPS:
                        for a in args:
                            self._register_var_load(stm, a)

    def _resolve_split_point(self) -> Tuple[Dict[SsaValue, Set[int]], int]:
        var_segments = self.var_segments
        open_set:UniqList[SsaValue] = UniqList()
        # dependenciesOfVar = Dict[SsaValue, UniqList[SsaValue]] = {}
        # :note: the number represents the bit index where new slice starts
        splitPointsOfVariable: Dict[SsaValue, Set[int]] = {}
        for k, v in sorted(var_segments.items(), key=lambda x: x[0]._name):
            open_set.append(k)
            slicePoints = splitPointsOfVariable.setdefault(k, set())
            for er in v.endpoint_ranges:
                er: VarBitSegmentEndpointInfo
                h, l_ = er.range_from_self
                assert h > l_, (k, v, h, l_)
                if l_ != 0:
                    slicePoints.add(l_)

                if h != k._dtype.bit_length():
                    slicePoints.add(h)

                # deps = dependenciesOfVar.get(er.dst_var, None)
                # if deps is None:
                #    deps = dependenciesOfVar[er.dst_var] = UniqList()
                # deps.append(k)
            # print(k, slicePoints)
            # #print(v.driver_ranges)
            # print(v.endpoint_ranges)
            # print("")

        while open_set:
            v = open_set.pop()
            vinfo: VarBitSegments = var_segments[v]
            # if I am beeing sliced than propagate my slice parts to a successor
            # to let them know that it can be split
            srcSplitPoints = splitPointsOfVariable[v]
            # transitively propagate slices from predecessor to sucessor
            for er in vinfo.endpoint_ranges:
                er: VarBitSegmentEndpointInfo
                srcEnd, srcOffset = er.range_from_self
                dstSplitPoints = splitPointsOfVariable[v]
                origDstSplitPointLen = len(dstSplitPoints)
                if srcSplitPoints is dstSplitPoints:
                    # src is dst, we need to prevent changing of set during the iteration
                    srcSplitPoints = tuple(srcSplitPoints)

                for srcSplitPoint in srcSplitPoints:
                    if srcSplitPoint < srcOffset or srcSplitPoint > srcEnd:
                        # is out of sub range of dst which is beeing used
                        continue

                    s = srcSplitPoint - srcOffset
                    w = er.dst_var._dtype.bit_length()
                    if s != 0 and s != w:
                        assert s >= 0 and s < w, (v, er, s)
                        dstSplitPoints.add(s)

                if origDstSplitPointLen != len(dstSplitPoints):
                    open_set.append(er.dst_var)

        # print("#" * 80)
        # for k, v in sorted(var_segments.items(), key=lambda x: x[0].i):
        #    splits = splitPointsOfVariable.setdefault(k, set())
        #    print(k, splits)
        #    #print(v.driver_ranges)
        #    print(v.endpoint_ranges)
        #    print("")

        # filter out variables which are not beeing split
        return {k: v for k, v in splitPointsOfVariable.items() if v}

    def _splitVariablesOnSplitPointsAndUpdateObjList(self,
                                                     ctx: SsaContext,
                                                     objList: Union[List[SsaPhi], List[SsaInstr]],
                                                     insertFn: Callable[[Union[SsaPhi, SsaInstr]], None],
                                                     splitPointsOfVariable:Dict[SsaValue, Set[int]],
                                                     variableForRange: Dict[Tuple[SsaValue, int, int], SsaValue],
                                                     varEntirelyReplaced: Dict[SsaValue, bool]
                                                     ):
        if not objList:
            return

        # isphi = isinstance(objList[0], SsaPhi)
        offset = 0
        for i in range(len(objList)):
            o = objList[offset + i]
            # splits = splitPointsOfVariable.get(o, None)
            wasReplaced = varEntirelyReplaced[o]
            if wasReplaced:
                objList.pop(offset + i)
                offset -= 1
                continue

            # if splits:
            #    # generate variables for each part
            #    var = o.origin
            #    prevSplitPoint = 0
            #
            #    for splitPoint in chain(sorted(splits), (var._dtype.bit_length(),)):
            #        newRtlVar = var[splitPoint:prevSplitPoint]
            #        vfrKey = (o, splitPoint, prevSplitPoint)
            #        if isinstance(newRtlVar, HValue):
            #            variableForRange[vfrKey] = newRtlVar
            #            continue
            #
            #        newHlsVar = variableForRange.get(vfrKey, None)
            #        if newHlsVar is None:
            #            # if was not already generated before
            #            t = newRtlVar._dtype
            #            if isphi:
            #                subO = SsaPhi(ctx, t, origin=newRtlVar)
            #            else:
            #                sub0 = None
            #                # subO = SsaInstr(ctx, t, OP_ASSIGN, (t.from_py(None),), origin=newRtlVar)
            #            if sub0 is not None:
            #                insertFn(offset + i + 1, subO)
            #                offset += 1
            #
            #            variableForRange[vfrKey] = newHlsVar
            #            prevSplitPoint = splitPoint
            #
    def _isConstantSlice(self, o: SsaValue):
        return isinstance(o, SsaInstr) and o.operator == AllOps.INDEX and isinstance(o.operands[1], HValue)

    def _checkIfUsedOnlyByReplaced(self, o: SsaValue,
                                  splitPointsOfVariable: Dict[SsaValue, Set[int]],
                                  varEntirelyReplaced: Dict[SsaValue, Optional[SsaValue]]):
        if self._isConstantSlice(o) and (o in splitPointsOfVariable or
                                         varEntirelyReplaced.get(o.operands[0], False)):
            usedOnlyByReplaced = True
        elif isinstance(o, HlsStreamProcRead):
            # can not reduce the read as it can not be split to parts
            usedOnlyByReplaced = False
        else:
            usedOnlyByReplaced = bool(o.users)
            for u in o.users:
                if u in splitPointsOfVariable or varEntirelyReplaced.get(u, False):
                    continue
                userIsIndex = self._isConstantSlice(u)
                if userIsIndex:
                    continue
                if isinstance(u, SsaInstrBranch):
                    usedOnlyByReplaced = False
                    break
                else:
                    usedOnlyByReplaced = False
                    break

        _usedOnlyByReplaced = varEntirelyReplaced.get(o, False)
        assert not (_usedOnlyByReplaced and not usedOnlyByReplaced), o
        varEntirelyReplaced[o] = usedOnlyByReplaced

        if usedOnlyByReplaced and not _usedOnlyByReplaced:
            # transitively re-check all dependencies
            if isinstance(o, SsaPhi):
                inputs = (i for i, _ in o.operands if not isinstance(i, HValue))
            else:
                inputs = (i for i in o.operands if not isinstance(i, HValue))

            for inp in inputs:
                self._checkIfUsedOnlyByReplaced(inp, splitPointsOfVariable, varEntirelyReplaced)

            for u in o.users:
                self._checkIfUsedOnlyByReplaced(u, splitPointsOfVariable, varEntirelyReplaced)

    def collectVarBitAlises(self, o: SsaValue, varBitAlises: Dict[SsaValue, Optional[ConcatOfSlices]]):
        if isinstance(o, SsaInstr):
            op = o.operator
            if op == OP_ASSIGN and o.operands:
                varBitAlises[o] = ConcatOfSlices(o.operands)
            elif op == AllOps.INDEX:
                v, i = o.operands
                if isinstance(i, HValue):
                    if isinstance(i._dtype, HSlice):
                        high = int(i.val.start)
                        low = int(i.val.stop)
                        assert int(i.val.step) == -1
                    else:
                        low = int(i)
                        high = low + 1

                    varBitAlises[o] = ConcatOfSlices(((v, high, low),))

                    # update also the parent input because this o is an alias of it but parent will not check for it explicitely
                    # parAlias = varBitAlises.get(v, ConcatOfSlices((v, )))
                    # parAlias.overwrite(high, low, o)
                    # print(parAlias)

            elif op == AllOps.CONCAT:
                varBitAlises[o] = ConcatOfSlices(o.operands)

    def checkIfUsedOnlyByReplaced(self, allBlocks: List[SsaBasicBlock],
                                  splitPointsOfVariable: Dict[SsaValue, Set[int]]):
        """
        Chceck if variable was entirely replaced byt its splited parts (for each variable).
        """
        varEntirelyReplaced: Dict[SsaValue, Optional[SsaValue]] = {}
        varBitAlises: Dict[SsaValue, Optional[ConcatOfSlices]] = {}
        for b in allBlocks:
            b: SsaBasicBlock
            for o in chain(b.phis, b.body):
                self.collectVarBitAlises(o, varBitAlises)
                self._checkIfUsedOnlyByReplaced(o, splitPointsOfVariable, varEntirelyReplaced)

        return varEntirelyReplaced, varBitAlises

    def resolveFinalReplacedVarValue(self,
                                     v: SsaValue,
                                     bitRange: Tuple[int, int],
                                     variableForRange: Dict[Tuple[SsaValue, int, int], SsaValue],
                                     varEntirelyReplaced: Dict[SsaValue, Optional[SsaValue]],
                                     varBitAlises: Dict[SsaValue, Optional[ConcatOfSlices]]):

            var_range_key = (v, bitRange[0], bitRange[1])
            replacement = variableForRange.get(var_range_key, None)
            if replacement is not None:
                return replacement

            v_varEntirelyReplaced = varEntirelyReplaced.get(v, False)
            if isinstance(v, HValue):
                if v._dtype.bit_length() == 1:
                    assert bitRange == (1, 0), bitRange
                    return v
                else:
                    return v[bitRange[0]:bitRange[1]]
            elif not v_varEntirelyReplaced:
                if v._dtype.bit_length() != bitRange[0] - bitRange[1]:
                    b = SsaExprBuilder(v.block, possition=v.block.body.index(v) + 1)
                    replacement = b._binaryOp(v, AllOps.INDEX, SLICE.from_py(slice(bitRange[0], bitRange[1], -1)))
                    # print(var_range_key, replacement)
                    variableForRange[var_range_key] = replacement

                    return replacement
                return v
            else:
                replacement = varBitAlises.get(v, None)
                if replacement is None:
                    if isinstance(v, SsaPhi):
                        v: SsaPhi
                        args: List[Tuple[SsaValue, SsaBasicBlock]] = []
                        for a, bl in v.operands:
                            _a = self.resolveFinalReplacedVarValue(a, bitRange, variableForRange, varEntirelyReplaced, varBitAlises)
                            args.append((_a, bl))
                        b = SsaExprBuilder(v.block, possition=v.block.phis.index(v))
                        replacement = b.phi(args)
                    else:
                        args: List[SsaValue] = []
                        assert v.operator in BITWISE_OPS, v.operator
                        for a in v.operands:
                            _a = self.resolveFinalReplacedVarValue(a, bitRange, variableForRange, varEntirelyReplaced, varBitAlises)
                            args.append(_a)

                        # :note: instructionindex must be resolved after all inputs are resolved
                        # because generating inputs may change the code possition
                        startIndex = 0
                        for _a in args:
                            if isinstance(_a, HValue):
                                continue
    
                            _a: SsaValue
                            if v.block is not _a.block:
                                continue
    
                            startIndex = max(startIndex, v.block.body.index(_a))
    
                        b = SsaExprBuilder(v.block, possition=startIndex + 1)
                        if len(args) == 1:
                            replacement = b._unaryOp(args[0], v.operator)
                        elif len(args) == 2:
                            o0, o1 = args
                            replacement = b._binaryOp(o0, v.operator, o1)
                        else:
                            raise NotImplementedError(v, args)
    
                    variableForRange[var_range_key] = replacement

                    return replacement

                # slice first so we resolve only part we need and nothing else
                replacement = replacement.slice(*bitRange)
                expanded = ConcatOfSlices(tuple(
                    self.resolveFinalReplacedVarValue(
                        _v, (high, low),
                        variableForRange, varEntirelyReplaced, varBitAlises)
                    for _v, high, low in replacement.slices
                ))

                resW = bitRange[0] - bitRange[1]
                assert resW == expanded.bit_length

                if v_varEntirelyReplaced:
                    if len(expanded.slices) == 1:
                        assert expanded.slices[0][1] == expanded.slices[0][0]._dtype.bit_length() and expanded.slices[0][2] == 0
                        return expanded.slices[0][0]
                    else:
                        # generate concatenation variable because it does not exist
                        startIndex = 0
                        for vPart in expanded.slices:
                            if isinstance(vPart[0], HValue):
                                # value has no dependencies
                                continue
                            if v.block is not vPart[0].block:
                                # some predecessor block, it is safe to start at beggining
                                continue
                            startIndex = max(startIndex, v.block.body.index(vPart[0]))

                        b = SsaExprBuilder(v.block, possition=startIndex + 1)
                        ops = []
                        for (sv, high, low) in expanded.slices:
                            assert high == sv._dtype.bit_length() and low == 0, (sv, high, low)
                            if not isinstance(sv, HValue):
                                assert not varEntirelyReplaced.get(sv, False), sv

                            ops.append(sv)

                        replacement = balanced_reduce(ops, lambda o0, o1: b._binaryOp(o0, AllOps.CONCAT, o1))
                        variableForRange[var_range_key] = replacement

                        return replacement

                else:
                    assert len(expanded.slices) == 1, ("Each unique part has have a custom variable, this should expand so it", expanded)
                    s = expanded.slices[0]

                    var = variableForRange.get(s, None)
                    if var is not None:
                        return var
                    else:
                        s0, sh, sl = s
                        assert sh == s0._dtype.bit_length() and sl == 0, ("Each unique part has have a custom variable, this should expand so it", expanded)
                        return s0

    def splitTheVariablesOnSplitPoints(self,
                                       allBlocks: List[SsaBasicBlock],
                                       splitPointsOfVariable: Dict[SsaValue, Set[int]]):
        """
        :note: We have to not just replace the variable, we need also to update its use.
            There is a problem that we can not just replace the usage with a concatenation
            of variables for parts because it would result in the same state as we had before.
            Because of this we need to check the uses and if possible (bitwise/cast operations)
            we need to duplicate the instruction for each part.
            If there are some uses which can not be split (e.g. multiplication operator)
            we we need to keep the original variable. However if the variable is a SsaPhi
            we need to downgrade it to a regular variable and we need to downgrade it to a regular
            variable and move the concatenation into block body. (This is because we want to allow fine graded
            optimization of phi functions.)
        """
        # resolve which variable we entirely remove
        varEntirelyReplaced, varBitAlises = self.checkIfUsedOnlyByReplaced(allBlocks, splitPointsOfVariable)
        # print("\nvarBitAlises", pformat({k._name: v for k, v in varBitAlises.items()}))
        # print("\nvarEntirelyReplaced", pformat({k: v for k, v in varEntirelyReplaced.items() if v}))
        # print("splitPointsOfVariable", pformat({k._name: v for k, v in splitPointsOfVariable.items()}))

        #
        # 1. construct all new variables and place them behind the actual variable (variable is always part of SsaInstr/SsaPhi)
        # [todo] rm using of RTL objects, 1. it does not have to be present, 2. we need to replace only in scope of the original variable

        variableForRange: Dict[Tuple[SsaValue, int, int], SsaValue] = {}
        for b in allBlocks:
            b: SsaBasicBlock
            # :note: we need to use index because we are modifying the collection
            self._splitVariablesOnSplitPointsAndUpdateObjList(
                b.ctx, b.phis, b.insertPhi, splitPointsOfVariable,
                variableForRange, varEntirelyReplaced)
            self._splitVariablesOnSplitPointsAndUpdateObjList(
                b.ctx, b.body, b.insertInstruction, splitPointsOfVariable,
                variableForRange, varEntirelyReplaced)

        # replace variable with new ones in all instructions
        for v, replace in sorted(varEntirelyReplaced.items(), key=lambda x: x[0]._name):
            if replace and v.users:
                replacement: Optional[SsaValue] = None  # lazy loaded
                for u in v.users:
                    if not varEntirelyReplaced[u]:
                        u: SsaInstr
                        if replacement is None:
                            replacement = self.resolveFinalReplacedVarValue(
                                v, (v._dtype.bit_length(), 0),
                                variableForRange, varEntirelyReplaced, varBitAlises)

                        # print("replace ", v, "in", u, "with", replacement)

                        u.replaceInput(v, replacement)

        # for b in allBlocks:
        #    b: SsaBasicBlock
        #    for phi in b.phis:
        #        phi: SsaPhi
        #        newOps = []
        #        for c, dstBlock in phi.operands:
        #            if isinstance(c, SsaValue):
        #                repl = variableForRange.get(c.origin, None)
        #                if repl is not None:
        #                    c.users.discard(phi)
        #                    c = repl
        #
        #            newOps.append((c, dstBlock))
        #        phi.operands = tuple(newOps)
        #
        #    for instr in b.body:
        #        instr: SsaInstr
        #        newOps = []
        #        for argI, arg in enumerate(instr.operands):
        #            if not isinstance(arg, SsaValue):
        #                continue
        #            repl = variableForRange.get(arg.origin, None)
        #            if repl is not None:
        #                arg.users.discard(instr)
        #                instr.operands[argI] = repl

        # copy the value initializations for new values
        # if we requre slice/concat we already should have it from previous steps
        # we search the value using rtl object in .origin property

        # print("variableForRange", pformat(variableForRange, sort_dicts=False))

        # 2. resolve varialbe aliases of newly created and existing vars., place in the block as soon as all dependencies ready
        # 3. replace the operands of instructions to use new variables

    def apply(self, hls: "HlsStreamProc", to_ssa: AstToSsa):
        self.var_segments: Dict[SsaValue, VarBitSegments] = {}
        allBlocksSet = set()
        allBlocks = list(collect_all_blocks(to_ssa.start, allBlocksSet))
        # Collect very concat/index on every variable so we know how should we split the variables
        self._collect_indexes_on_variables(allBlocks)
        if not self.var_segments:
            return

        splitPointsOfVariable = self._resolve_split_point()
        self.splitTheVariablesOnSplitPoints(allBlocks, splitPointsOfVariable)

        # split each variable as requested and replace it with a
        # raise NotImplementedError()
        # split the variables so their indexes never overlap and each indexed assignment drives only own segment
