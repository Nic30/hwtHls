from typing import Set, Tuple, Dict

from hwtHls.ssa.analysis.liveness import EdgeLivenessDict
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtHls.ssa.value import SsaValue
from hwtHls.ssa.analysis.threadMining import SsaPassThreadMining
from hwt.pyUtils.uniqList import UniqList


class BlockMeta():
    """
    :ivar isCycleEntryPoint: This block is a header of the cycle.
    :ivar needsControl: This bolock needs the control channel on the input for its functionality.
    :ivar requiresStarter: This block requires a provider of initial sync token for its functionality.
    :ivar isInitialization: This block is run just once on the beginning of the program.
    :ivar phiCyclicArgs: Set of varialbes which are writen in this block but also read by some phi.
    :ivar inLiveVarsWithMultipleSrcBlocks: values which may come from multiple predecessor blocks
        and the mux needs to be generated if this shuld be in pipeline
    """

    def __init__(self,
                 isCycleEntryPoint: bool,
                 needsControl: bool,
                 requiresStarter: bool,
                 isInitialization:bool,
                 phiCyclicArgs: Set[SsaValue],
                 inLiveVarsWithMultipleSrcBlocks: UniqList[SsaValue]):
        self.isCycleEntryPoint = isCycleEntryPoint
        self.needsControl = needsControl
        self.requiresStarter = requiresStarter
        self.isInitialization = isInitialization
        self.phiCyclicArgs = phiCyclicArgs
        self.inLiveVarsWithMultipleSrcBlocks = inLiveVarsWithMultipleSrcBlocks

    def __repr__(self):
        flags = []
        for f in ('isCycleEntryPoint', 'needsControl', 'requiresStarter', 'isInitialization'):
            if getattr(self, f):
                flags.append(f)
        if self.phiCyclicArgs:
            flags.append(f"phiCyclicArgs={self.phiCyclicArgs}")
        return f"<{self.__class__.__name__:s} {', '.join(flags)}>"


class SaaGetBlockSyncType():
    '''

    .. code-block:: llvm

        entry: # isInitialization
            br label while
        while: # isCycleEntryPoint
            %0 = phi [0, entry], [1, while] # later resolved as a register with a 0 as reset value
            use(%0)
            br label while

    In this case the synchronization is not needed because body contains
    a single thread and phis can be reduced using reset value extraction.


    .. code-block:: llvm

        entry: # isInitialization
            br label while0
        while0: # isCycleEntryPoint, needsControl
            br label while1
        while1: # isCycleEntryPoint, needsControl
            %0 = phi [0, while0], [1, while1]
            use(%0)
            %1 = read()
            br %1 label while0, label while1

    In this case phi can select just based on value of %1 if the channel with its value is initializaed to while0 braching value.
    However this is not implemented yet and controll channels are generated instead.

    '''

    def __init__(self, start: SsaBasicBlock,
                 out_of_pipeline_edges:Set[Tuple[SsaBasicBlock, SsaBasicBlock]],
                 edge_var_live:EdgeLivenessDict):
        self._blockMeta = {}
        self.start_block = start
        self.edge_var_live = edge_var_live
        self.out_of_pipeline_edges = out_of_pipeline_edges

    def _get_SsaBasicBlock_meta(self, block: SsaBasicBlock) -> BlockMeta:
        """
        The code needs a sychronization if it starts a new thread without data dependencies and has predecessor thread.
        :note: They synchronization is always marked fot the start of the thread.
        """
        m: BlockMeta = self._blockMeta[block]

        threads = self.threadsPerBlock[block]
        predThreadIds = set()
        for pred in block.predecessors:
            predThreadIds.update(id(t) for t in self.threadsPerBlock[pred])
        threadsStartingThere = [t for t in self.threadsPerBlock[block] if id(t) not in predThreadIds]

        if m.isCycleEntryPoint:
            # The synchronization is not required if it could be only by the data itself.
            # It can be done by data itself if there is an single output/write which has all
            # input as transitive dependencies (uncoditionally.) And if this is an infinite cycle.
            # So we do not need to check the number of executions.
            needsControlOld = m.needsControl
            if not m.needsControl:
                if len(threads) > 1 or len(block.predecessors) > 2 or bool(block.phis):
                    # multiple independent threads in body or more entry points to a loop
                    m.needsControl = True

                else:
                    for cond, suc in block.successors.targets:
                        if cond is not None:
                            m.needsControl = True
                            break

                    if not m.needsControl:
                        sucThreads = sum((len(self.threadsPerBlock[suc])
                                          for suc in block.successors.iterBlocks()))
                        if sucThreads > 1:
                            m.needsControl = True

                        # and not any(bool(suc.phis) for suc in block.successors.iterBlocks()):
                        # pred = block.predecessors[0]
                        # if (pred, block) in self.out_of_pipeline_edges:
                        #    pred = block.predecessors[1]
                        #
                        # assert (pred, block) not in self.out_of_pipeline_edges
                        # for cond, suc in pred.successors.targets:
                        #    if suc is block and cond is None:
                        #        m.needsControl = len(self.threadsPerBlock[pred]) > 1
                        #        if m.needsControl:
                        #            break

            if m.needsControl:
                m.requiresStarter = len(block.predecessors) == 1
            if not needsControlOld and m.needsControl:
                self._onBlockNeedsControl(block)
        else:
            m.requiresStarter = (
                not block.predecessors and
                (
                    len(threadsStartingThere) >= 1 or
                    len(block.successors) != 1
                )
            )
            # sucThreadCnt = sum((len(self.threadsPerBlock[suc]) for suc in block.successors.iterBlocks()))
            # predThreadCnt = sum((len(self.threadsPerBlock[suc]) for suc in block.predecessors))
            if not m.needsControl:
                m.needsControl = (
                    m.requiresStarter or
                    # (len(threads) >= 1 and not self.edge_var_live) or
                    # (self._inputVariableCnt(block) == 0 and bool(threads)) or
                    # ( predThreadCnt > 1) or
                    # sucThreadCnt > 1 or
                    len(threadsStartingThere) > 1 or
                    (bool(threads) and
                        (
                            any(self._blockMeta[pred].needsControl for pred in block.predecessors) or
                            any(self._blockMeta[suc].needsControl for suc in block.successors.iterBlocks())
                        )
                    )
                )
                if m.needsControl:
                    self._onBlockNeedsControl(block)

    def _onBlockNeedsControl(self, block: SsaBasicBlock):
        for pred in block.predecessors:
            m: BlockMeta = self._blockMeta[pred]
            if not m.needsControl:
                m.needsControl = True
                if not m.requiresStarter and not pred.predecessors:
                    m.requiresStarter = True

                self._onBlockNeedsControl(pred)

        for suc in block.successors.iterBlocks():
            m: BlockMeta = self._blockMeta[suc]
            if not m.needsControl:
                m.needsControl = True
                self._onBlockNeedsControl(suc)

    def _inputVariableCnt(self, block: SsaBasicBlock):
        return sum(
            len(self.edge_var_live.get(pred, {}).get(block, ()))
            for pred in block.predecessors
        )

    def collectPhiCyclicArgs(self, block: SsaBasicBlock, m: BlockMeta):
        liveIn = set()
        liveOut = set()
        for pred in block.predecessors:
            liveIn.update(self.edge_var_live[pred][block])
        for suc in block.successors.iterBlocks():
            liveOut.update(self.edge_var_live[block][suc])
        for v in liveIn.intersection(liveOut):
            if v.block is block:
                m.phiCyclicArgs.add(v)

    def collectCycles(self, block: SsaBasicBlock, m: BlockMeta):
        for pred in block.predecessors:
            if (pred, block) in self.out_of_pipeline_edges:
                m.isCycleEntryPoint = True
                break

        if m.isCycleEntryPoint:
            self.collectPhiCyclicArgs(block, m)

    def markInitializations(self):
        block = self.start_block
        while len(block.predecessors) <= 1:
            m: BlockMeta = self._blockMeta[block]
            m.isInitialization = True
            if len(block.successors.targets) == 1:
                block = block.successors.targets[0][1]
            else:
                break

    def collectLiveInVarsWithMultipleSrcBlocks(self, block: SsaBasicBlock):
        seenInLiveVars: UniqList[SsaValue] = UniqList()
        inLiveVarsWithMultipleSrcBlocks: UniqList[SsaValue] = UniqList()
        for pred in block.predecessors:
            block_var_live = self.edge_var_live.get(pred, {})
            for v in block_var_live.get(block, ()):
                if v in seenInLiveVars:
                    inLiveVarsWithMultipleSrcBlocks.append(v)
                else:
                    seenInLiveVars.append(v)
        return inLiveVarsWithMultipleSrcBlocks
        
    def apply(self):
        threadMining = SsaPassThreadMining(self.out_of_pipeline_edges)
        threadMining.apply(self.start_block)
        self.threadsPerBlock = threadMining.threadsPerBlock
        self._blockMeta: Dict[SsaBasicBlock, BlockMeta] = {}
        blocks = list(collect_all_blocks(self.start_block, set()))

        for block in blocks:
            m = self._blockMeta[block] = BlockMeta(False, False, False, False,
                                                   set(), self.collectLiveInVarsWithMultipleSrcBlocks(block))
            self.collectCycles(block, m)
        self.markInitializations()

        for b in blocks:
            self._get_SsaBasicBlock_meta(b)

        return self._blockMeta
