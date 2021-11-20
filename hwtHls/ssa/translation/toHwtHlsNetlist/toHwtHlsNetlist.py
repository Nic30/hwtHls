from typing import List, Dict, Union, Set, Tuple, Optional, Sequence

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import OpDefinition
from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.ssa.analysis.liveness import EdgeLivenessDict
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.branchControlLabel import BranchControlLabel
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.translation.toHwtHlsNetlist.nodes.loopHeader import HlsLoopGate
from hwtHls.ssa.translation.toHwtHlsNetlist.opCache import SsaToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.toHwtHlsNetlist.syncAndIo import SsaToHwtHlsNetlistSyncAndIo
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead, HlsStreamProcWrite
from hwtHls.netlist.nodes.io import HlsRead, HlsWrite
from hwtHls.netlist.nodes.mux import HlsMux
from hwtHls.netlist.nodes.ops import AbstractHlsOp, HlsConst, HlsOperation
from hwtHls.netlist.nodes.ports import HlsOperationOutLazy, link_hls_nodes, \
    HlsOperationOut
from hwtHls.netlist.utils import hls_op_or, hls_op_not, hls_op_and
from ipCorePackager.constants import INTF_DIRECTION
from hwtHls.ssa.value import SsaValue


class BlockMeta():

    def __init__(self, is_cycle_entry_point: bool, needs_control: bool, requires_starter: bool):
        self.is_cycle_entry_point = is_cycle_entry_point
        self.needs_control = needs_control
        self.requires_starter = requires_starter

    def __repr__(self):
        flags = []
        for f in ("is_cycle_entry_point", 'needs_control', 'requires_starter'):
            if getattr(self, f):
                flags.append(f)
        return f"<{self.__class__.__name__:s} {', '.join(flags)}>"


class SsaToHwtHlsNetlist():
    """
    A class used to translate :mod:`hwtHls.ssa` to objects from :mod:`hwtHls.netlist.nodes.ops`.
    These objects are typicaly used for scheduling and circuit generating.

    :ivar hls: parent hls synthetizer which is used to generate scheduling graph
    :ivar start_block: a basic block where program begins
    :ivar edge_var_live: dictionary which maps which variable is live on block transition
    """

    def __init__(self, hls: HlsPipeline,
                 start_block: SsaBasicBlock,
                 out_of_pipeline_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]],
                 edge_var_live: EdgeLivenessDict):
        self.hls = hls
        self.start_block = start_block

        self.nodes: List[AbstractHlsOp] = hls.nodes
        self.io = SsaToHwtHlsNetlistSyncAndIo(self, out_of_pipeline_edges, edge_var_live)

        self._to_hls_cache = SsaToHwtHlsNetlistOpCache()
        self._current_block:Optional[SsaBasicBlock] = None

        self._block_meta: Dict[SsaBasicBlock, BlockMeta] = {}
        self._block_ens: Dict[SsaBasicBlock,
                              Union[HlsOperationOut, HlsOperationOutLazy, None]] = {}

    def _get_SsaBasicBlock_meta(self, block: SsaBasicBlock) -> BlockMeta:
        try:
            return self._block_meta[block]
        except KeyError:
            pass

        is_cycle_entry_point = False
        for pred in block.predecessors:
            if (pred, block) in self.io.out_of_pipeline_edges:
                is_cycle_entry_point = True
                break

        needs_control = True
        requires_starter = False
        if is_cycle_entry_point:
            # The synchronization is not required if it could be only by the data itself.
            # It can be done by data itself if there is an single output/write which has all
            # input as transitive dependencies (uncoditionally.) And if this is an infinite cycle.
            # So we do not need to check the number of executions.
            if len(block.predecessors) == 1 and len(block.successors) == 1:
                pred = block.predecessors[0]
                for cond, suc in pred.successors.targets:
                    if suc is block and cond is None:
                        needs_control = len(self.io.edge_var_live[pred][block]) > 1

            if needs_control:
                requires_starter = block is self.start_block

        else:
            requires_starter = block is self.start_block and not block.predecessors
            needs_control = (
                requires_starter or
                len(block.predecessors) != 1 or
                len(block.successors) != 1 or
                self._get_SsaBasicBlock_meta(block.predecessors[0]).needs_control or
                self._get_SsaBasicBlock_meta(block.successors.targets[0][1]).needs_control

            )

        m = BlockMeta(is_cycle_entry_point, needs_control, requires_starter)
        self._block_meta[block] = m

        return m

    def _prepare_SsaBasicBlockControl(self, block: SsaBasicBlock):
        # prepare HlsOutputLazy and input interface for variables which are live on
        # edges which are corssing pipeline boundaries
        self._current_block = block
        m = self._get_SsaBasicBlock_meta(block)

        if m.is_cycle_entry_point:
            if m.needs_control:
                if m.requires_starter:
                    self.io._add_HlsProgramStarter()

                HlsLoopGate.inset_before_block(
                    self.hls,
                    block,
                    self.io,
                    self._to_hls_cache,
                    self.nodes)
        elif m.requires_starter:
            self.io._add_HlsProgramStarter()

    def to_hls_SsaBasicBlock_resolve_io_and_sync(self, block: SsaBasicBlock):
        m = self._get_SsaBasicBlock_meta(block)
        for pred in block.predecessors:
            if (pred, block) in self.io.out_of_pipeline_edges:
                self.io.init_out_of_pipeline_variables(pred, block, m.needs_control)

    def finalize_out_of_pipeline_variables(self, blocks: Sequence[SsaBasicBlock]):
        assert self._current_block is None
        try:
            for block in blocks:
                for dst_block in block.successors.iter_blocks():
                    if (block, dst_block) in self.io.out_of_pipeline_edges:
                        self._current_block = block
                        self.io.finalize_block_out_of_pipeline_variable_outputs(block, dst_block)
        finally:
            self._current_block = None

        for k, v in self._block_ens.items():
            assert not isinstance(v, HlsOperationOutLazy) or v.replaced_by, ("All outputs should be already resolved", k, v)

        for k, v in self._to_hls_cache.items():
            assert not isinstance(v, HlsOperationOutLazy), ("All outputs should be already resolved", k, v)

    def to_hls_SsaBasicBlock(self, block: SsaBasicBlock):
        try:
            self._prepare_SsaBasicBlockControl(block)
            self.to_hls_SsaBasicBlock_phis(block)
            # propagate also for variables which are not explicitely used

            for stm in block.body:

                if isinstance(stm, HlsStreamProcRead):
                    stm: HlsStreamProcRead
                    try:
                        return self._to_hls_cache._to_hls_cache[(block, stm)]
                    except KeyError:
                        pass
                    self.io._out_of_hls_io.append(stm._src)
                    o = self.io._read_from_io(stm._src)
                    self._to_hls_cache.add((block, stm), o)

                    #self.io._out_of_hls_io.append(stm._src)
                    #self._add_block_en_to_control_if_required(stm)

                elif isinstance(stm, HlsStreamProcWrite):
                    # this is a write to output port which may require synchronization
                    stm: HlsStreamProcWrite
                    src = self.to_hls_expr(stm.getSrc())
                    dst = stm.dst
                    assert isinstance(dst, (Interface, RtlSignalBase)), dst
                    self.io._out_of_hls_io.append(dst)
                    self.io._write_to_io(dst, src)

                elif isinstance(stm, SsaInstr):
                    # arbitrary arithmetic instructions
                    stm: SsaInstr
                    src = self._to_hls_expr_op(stm.operator, stm.operands)
                    # variable can be potentially input and output variable of the block if it is used
                    # because it can be used only in phi under the condition which is not met on first pass
                    # trough the block
                    self._to_hls_cache.add((self._current_block, stm), src)

                else:
                    raise NotImplementedError(stm)

            if block.successors:
                self.to_hls_SsaBasicBlock_successors(block)

        finally:
            self._current_block = None

    def _to_hls_expr_op(self,
                        fn:OpDefinition,
                        args: List[Union[HValue, RtlSignalBase, HlsOperationOut, SsaValue]]
                        ) -> HlsOperationOut:
        """
        Construct and link the operator node from operator and arguments.
        """
        a0 = args[0]
        if isinstance(a0, HlsOperationOut):
            if isinstance(a0.obj, HlsRead):
                w = a0.obj.src.T.bit_length()
            else:
                raise NotImplementedError()
        else:
            w = a0._dtype.bit_length()

        c = HlsOperation(self.hls, fn, len(args), w)
        self.nodes.append(c)
        for i, arg in zip(c._inputs, args):
            a = self.to_hls_expr(arg)
            link_hls_nodes(a, i)

        return c._outputs[0]

    def to_hls_expr(self, obj: Union[HValue, SsaValue, RtlSignalBase, HlsOperationOut]) -> HlsOperationOut:
        if isinstance(obj, SsaValue):
            return self._to_hls_cache.get((self._current_block, obj))
        elif isinstance(obj, HValue) or (isinstance(obj, RtlSignalBase) and obj._const):
            _obj = HlsConst(obj)
            self._to_hls_cache.add(_obj, _obj)
            self.nodes.append(_obj)
            return _obj._outputs[0]

        elif isinstance(obj, (HlsOperationOut, HlsOperationOutLazy)):
            return obj

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
        mux = HlsMux(self.hls, phi._dtype.bit_length(), phi._name)
        self.nodes.append(mux)

        mux_out = mux._outputs[0]
        self._to_hls_cache.add((phi.block, phi), mux_out)
        # cur_dst = self._to_hls_cache._to_hls_cache.get(phi, None)
        # assert cur_dst is None or isinstance(cur_dst, HlsOperationOutLazy), (phi, cur_dst)
        self._to_hls_cache._to_hls_cache.get((self._current_block, phi), mux_out)

        for lastSrc, (src, src_block) in iter_with_last(phi.operands):
            if lastSrc:
                c = None
            else:
                c = en_from_pred_OH[block_predecessors.index(src_block)]
                mux._add_input_and_link(c)

            src = self.to_hls_expr(src)
            mux._add_input_and_link(src)
            mux.elifs.append((c, src))

        return mux_out

    def _add_block_en_to_control_if_required(self, op: Union[HlsRead, HlsWrite]):
        if self._get_SsaBasicBlock_meta(self._current_block).needs_control:
            en = self._collect_en_from_predecessor(self._current_block)
            if en is not None:
                op.add_control_extraCond(en)

    def _collect_en_from_predecessor_one_hot(self, block: SsaBasicBlock):
        en_from_pred = []
        # [todo] check if does not lead to a deadlock if there is only as single predecessor
        # and the predecessor block has some extrenal io
        for pred in block.predecessors:
            if self._get_SsaBasicBlock_meta(pred).needs_control:
                en = self._to_hls_cache.get(BranchControlLabel(pred, block, INTF_DIRECTION.SLAVE))
                en_from_pred.append(en)

        return en_from_pred

    def _collect_en_from_predecessor(self, block: SsaBasicBlock):
        """
        [todo] The en is not required if the synchronisation can be done purely by data.
        """
        assert block is self._current_block
        cur = self._block_ens.get(block, NOT_SPECIFIED)
        if cur is not NOT_SPECIFIED:
            while isinstance(cur, HlsOperationOutLazy) and cur.replaced_by is not None:
                # lazy update of _block_ens if something got resolved
                cur = cur.replaced_by
                self._block_ens[block] = cur

            return cur

        if not self._get_SsaBasicBlock_meta(self._current_block).needs_control:
            self._block_ens[block] = None
            return None

        if block is self.start_block and self.io.start_block_en is not None:
            en_by_pred = self.io.start_block_en
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
        en_by_pred = self._collect_en_from_predecessor(block)
        cond = None
        block_var_live = self.io.edge_var_live.get(block, {})
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
            elif en_by_pred is None:
                br_cond = None
            else:
                br_cond = hls_op_and(self.hls, cond, en_by_pred)

            # produce tokens for all successors depending on brach condition on the end of this block
            is_out_of_pipeline = (block, suc_block) in self.io.out_of_pipeline_edges
            if br_cond is not None:
                for d in (INTF_DIRECTION.SLAVE, INTF_DIRECTION.MASTER):
                    label = BranchControlLabel(block, suc_block, d)
                    if is_out_of_pipeline and d is INTF_DIRECTION.SLAVE:
                        # input will be or already is connected to io port which provides the data from
                        # out of pipeline
                        assert label in self._to_hls_cache, label
                        continue
                        # else we need to add the record for output port to find it

                    self._to_hls_cache.add(label, br_cond)

            if not is_out_of_pipeline:
                # propagete variables on block input
                for v in block_var_live.get(suc_block, ()):
                    cur_v = self._to_hls_cache.get((block, v))
                    self._to_hls_cache.add((suc_block, v), cur_v)

