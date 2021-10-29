from typing import List, Dict, Union, Set, Tuple, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import OpDefinition
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.hlsStreamProc.ssa.analysis.liveness import EdgeLivenessDict
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from hwtHls.hlsStreamProc.ssa.branchControlLabel import BranchControlLabel
from hwtHls.hlsStreamProc.ssa.instr import SsaInstr
from hwtHls.hlsStreamProc.ssa.phi import SsaPhi
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.syncAndIo import SsaToHwtHlsNetlistSyncAndIo
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead, HlsStreamProcWrite
from hwtHls.netlist.codeOps import AbstractHlsOp, HlsRead, HlsWrite, HlsOperationOut, \
    HlsConst, HlsOperationIn, HlsMux, HlsOperation
from hwtHls.netlist.codeOpsPorts import HlsOperationOutLazy, link_hls_nodes
from hwtHls.netlist.utils import hls_op_or, hls_op_not, hls_op_and
from hwtHls.tmpVariable import HlsTmpVariable
from ipCorePackager.constants import DIRECTION


class SsaToHwtHlsNetlist():
    """
    A class used to translate :mod:`hwtHls.hlsStreamProc.ssa` to objects from :mod:`hwtHls.netlist.codeOps`.
    These objects are typicaly used for scheduling and circuit generating.

    :ivar hls: parent hls synthetizer which is used to generate scheduling graph
    :ivar start_block: a basic block where program begins
    :ivar start_block_en: optionaly port to trigger the program execution
    :ivar edge_var_live: dictionary which maps which variable is live on block transition
    """

    def __init__(self, hls: HlsPipeline,
                 start_block: SsaBasicBlock,
                 out_of_pipeline_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]],
                 edge_var_live: EdgeLivenessDict):
        self.hls = hls
        self.start_block = start_block
        self.start_block_en: Optional[HsStructIntf] = None
        self.start_block_en_r: Optional[HlsOperationOut] = None

        self.nodes: List[AbstractHlsOp] = hls.nodes
        self.io = SsaToHwtHlsNetlistSyncAndIo(self, out_of_pipeline_edges, edge_var_live)

        self._to_hls_cache = {}
        self._current_block:Optional[SsaBasicBlock] = None

        self._block_ens: Dict[SsaBasicBlock,
                              Union[HlsOperationOut, HlsOperationOutLazy, None]] = {}

    def _to_hls_expr_op(self,
                        fn:OpDefinition,
                        args: List[Union[HValue, RtlSignalBase, HlsOperationOut, SsaPhi]]
                        ) -> HlsOperationOut:
        """
        Construct and link the operator node from operator and arguments.
        """
        a0 = args[0]
        if isinstance(a0, SsaPhi):
            a0 = a0.dst
        if isinstance(a0, HlsOperationOut):
            if isinstance(a0.obj, HlsRead):
                w = a0.obj.src.T.bit_length()
            else:
                raise NotImplementedError()
        else:
            w = a0._dtype.bit_length()

        c = HlsOperation(self.hls, fn, len(args), w)
        self.nodes.append(c)
        for i, arg in enumerate(args):
            a = self.to_hls_expr(arg)
            link_hls_nodes(a, HlsOperationIn(c, i))

        return HlsOperationOut(c, 0)

    def _add_to_to_hls_cache(self, k, v:HlsOperationOut) -> None:
        """
        Register object in _to_hls_cache dictionary, which is used to avoid duplication of object in network.
        """
        assert not isinstance(k, HlsTmpVariable), (k, "tmp variable has to always be tied to some block")
        if isinstance(v, HlsOperationOutLazy):
            assert v.replaced_by is None, (v, v.replaced_by)
            v.keys_of_self_in_cache.append(k)

        cur = self._to_hls_cache.get(k, None)
        if cur is not None:
            assert isinstance(cur, HlsOperationOutLazy), (k, cur, v)
            cur.replace(v)
            return

        self._to_hls_cache[k] = v

    def _get_from_to_hls_cache(self, k) -> Union[HlsOperationOut, HlsOperationOutLazy]:
        """
        Load object form _to_hls_cache dictionary, if the object is not preset temporary placeholder (HlsOperationOutLazy)
        is returned instead (and must be replaced later).
        """
        try:
            v = self._to_hls_cache[k]
            assert not isinstance(v, HlsOperationOutLazy) or v.replaced_by is None, (k, v)
            return v
        except KeyError:
            o = HlsOperationOutLazy(k, self._to_hls_cache)
            self._to_hls_cache[k] = o
            return o

    def to_hls_expr(self, obj: Union[HValue]) -> HlsOperationOut:
        if isinstance(obj, HValue) or (isinstance(obj, RtlSignalBase) and obj._const):
            _obj = HlsConst(obj)
            self._add_to_to_hls_cache(_obj, _obj)
            self.nodes.append(_obj)
            return HlsOperationOut(_obj, 0)

        elif isinstance(obj, (HlsOperationOut, HlsOperationOutLazy)):
            return obj

        elif isinstance(obj, HlsStreamProcRead):
            obj: HlsStreamProcRead
            self.io._out_of_hls_io.append(obj._src)
            return self.io._read_from_io(obj._src)

        elif isinstance(obj, SsaPhi):
            return self._get_from_to_hls_cache((self._current_block, obj.dst))

        elif isinstance(obj, HlsTmpVariable):
            return self._get_from_to_hls_cache((self._current_block, obj))
        else:
            raise NotImplementedError(obj)

    def _construct_in_mux_for_phi(self,
                                  phi: SsaPhi,
                                  block_predecessors: List[SsaBasicBlock],
                                  en_from_pred_OH:List[HlsOperationOut]):
        """
        The phi may appear only if the block has multiple predecessors.
        The value needs to be selected based on predecessor block of current block.
        """
        # variable value is selected based on predecessor block
        mux = HlsMux(self.hls, phi.dst._dtype.bit_length(), phi.dst._name)
        self.nodes.append(mux)
        cur_dst = self._to_hls_cache.get(phi.dst, None)
        mux_out = HlsOperationOut(mux, 0)
        assert cur_dst is None or isinstance(cur_dst, HlsOperationOutLazy), (phi, cur_dst)
        self._add_to_to_hls_cache((self._current_block, phi.dst), mux_out)

        for lastSrc, (src, src_block) in iter_with_last(phi.operands):
            if isinstance(src, SsaPhi):
                src = src.dst
            src = self.to_hls_expr(src)

            mux.dependsOn.append(None)
            if lastSrc:
                c = None
            else:
                mux.dependsOn.append(None)
                c = en_from_pred_OH[block_predecessors.index(src_block)]
                link_hls_nodes(c, HlsOperationIn(mux, len(mux.dependsOn) - 2))

            link_hls_nodes(src, HlsOperationIn(mux, len(mux.dependsOn) - 1))
            for d in mux.dependsOn:
                assert d is not None

            assert src is not None
            for o in (c, src):
                if isinstance(o, HlsOperationOutLazy):
                    o.register_mux_elif(mux, len(mux.elifs))

            mux.elifs.append((c, src))

        return mux_out

    def _add_block_en_to_controll_if_required(self, op: Union[HlsRead, HlsWrite]):
        en = self._collect_en_from_predecessor(self._current_block)
        if en is not None:
            assert len(op.dependsOn) == 1
            op.dependsOn.append(None)
            link_hls_nodes(en, HlsOperationIn(op, 1))

    def _collect_en_from_predecessor_one_hot(self, block: SsaBasicBlock):
        en_from_pred = []
        # [todo] check if does not lead to a deadlock if there is only as single predecessor
        # and the predecessor block has some extrenal io
        for pred in block.predecessors:
            en = self._get_from_to_hls_cache(BranchControlLabel(pred, block, DIRECTION.OUT))
            en_from_pred.append(en)

        return en_from_pred

    def _collect_en_from_predecessor(self, block: SsaBasicBlock):
        assert block is self._current_block
        cur = self._block_ens.get(block, NOT_SPECIFIED)
        if cur is not NOT_SPECIFIED:
            while isinstance(cur, HlsOperationOutLazy) and cur.replaced_by is not None:
                cur = cur.replaced_by
                self._block_ens[block] = cur

            return cur

        if block is self.start_block and self.start_block_en is not None:
            en_by_pred = self.start_block_en_r
        else:
            en_by_pred = None
            assert block.predecessors, (self._current_block,
                                        "Must have predecessor because it is not start block")

        for pred_token in self._collect_en_from_predecessor_one_hot(block):
            if en_by_pred is None:
                en_by_pred = pred_token
            else:
                en_by_pred = hls_op_or(self.hls, en_by_pred, pred_token)

        assert en_by_pred is not None
        self._block_ens[block] = en_by_pred
        return en_by_pred

    def to_hls_SsaBasicBlock_phis(self, block: SsaBasicBlock):
        # single predecessor, and marked to re-exec after end
        # is_just_reexecuting_itself = block is self.start_block and len(block.predecessors) == 2 and block in block.predecessors
        if block.phis:
            en_from_pred = self._collect_en_from_predecessor_one_hot(block)

            # construct input muxes
            # this exists because of branching in original code and may appear in 2 variants
            #    * branching which involves loop (contains input from some later pipeline stage)
            #    * branching which does not originate from loop headers
            # :note: this probel is described in :mod:`hwtHls.hlsStreamProc.pipelineMaterialization`
            for phi in block.phis:
                phi: SsaPhi
                self._construct_in_mux_for_phi(phi, block.predecessors, en_from_pred)

    def to_hls_SsaBasicBlock_successors(self, block: SsaBasicBlock):
        # require token from all predecessors
        # * phi muxes do select a correct data, we now care only about
        #   the value of control token.
        #   * the value of control token can mean that this branch was taken or cancelled
        #   * the reading of a token asserst correct number of output tokens for block
        #     where branching does not depend on input data (the block itself
        #     can contain such a branching, but still may be a part of a branch
        #     which requires synchronization)
        # produce tokens for all successors depending on brach condition on the end of this block
        # if edge is out of pipeline it will be connected to io later
        en_by_pred = self._collect_en_from_predecessor(block)
        cond = None
        for c, suc_block in block.successors.targets:
            # cummulatively build the condition for the branching
            if c is not None:
                c = self.to_hls_expr(c)

            if cond is None:
                cond = c
            else:
                cond = hls_op_not(self.hls, cond)
                if c is not None:
                    cond = hls_op_and(self.hls, cond, c)

            # merge branching condition and enable for this block
            if cond is None:
                br_cond = en_by_pred
            else:
                br_cond = hls_op_and(self.hls, cond, en_by_pred)

            is_out_of_pipeline = (block, suc_block) in self.io.out_of_pipeline_edges

            for d in (DIRECTION.IN, DIRECTION.OUT):
                label = BranchControlLabel(block, suc_block, d)
                if is_out_of_pipeline and d is DIRECTION.OUT:
                    # input will be or already is connected to io port which provides the data from
                    # out of pipeline
                    assert label in self._to_hls_cache, label
                    continue

                self._add_to_to_hls_cache(label, br_cond)

            if not is_out_of_pipeline:
                # propagete variables on block input
                for v in self.io.edge_var_live.get(block, {}).get(suc_block, ()):
                    self._add_to_to_hls_cache((suc_block, v), self._get_from_to_hls_cache((block, v)))

    def to_hls_SsaBasicBlock(self, block: SsaBasicBlock):
        try:
            # print(block.label)
            # prepare HlsOutputLazy and input interface for variables which are live on
            # edges which are corssing pipeline boundaries
            self._current_block = block
            self.to_hls_SsaBasicBlock_phis(block)
            # propagate also for variables which are not explicitely used

            for stm in block.body:
                if isinstance(stm, SsaInstr):
                    # arbitrary arithmetic instructions
                    stm: SsaInstr
                    if isinstance(stm.src, tuple):
                        fn, ops = stm.src
                        src = self._to_hls_expr_op(fn, ops)
                    else:
                        src = self.to_hls_expr(stm.src)

                    self._add_to_to_hls_cache((self._current_block, stm.dst), src)

                elif isinstance(stm, HlsStreamProcRead):
                    # Read without any consummer
                    self.io._out_of_hls_io.append(stm._src)
                    self._add_block_en_to_controll_if_required(stm)

                elif isinstance(stm, HlsStreamProcWrite):
                    # this is a write to output port which may require synchronization
                    stm: HlsStreamProcWrite
                    src = self.to_hls_expr(stm.src)
                    dst = stm.dst
                    assert isinstance(dst, Interface), dst
                    self.io._out_of_hls_io.append(stm.dst)
                    self.io._write_to_io(dst, src)

                else:
                    raise NotImplementedError(stm)

            if block.successors:
                self.to_hls_SsaBasicBlock_successors(block)

        finally:
            self._current_block = None
