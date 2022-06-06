from typing import Set, List

from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineLoopInfo, MachineLoop
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads


class HlsNetlistAnalysisPassBlockSyncType(HlsNetlistAnalysisPass):
    '''
    This pass updates blockSync dictionary in :class:`HlsNetlistAnalysisPassMirToNetlist` with
    flags which are describing what type of synchronization for block should be used.
    :note: This is thread level synchronization of control flow in blocks not RTL type of synchronization.

    .. code-block:: llvm

        entry: # isInitialization
            br label while
        while: # isCycleEntryPoint
            %0 = phi [0, entry], [1, while] # later resolved as a register with a 0 as reset value
            use(%0)
            br label while

    In this case the synchronization is not needed because body contains
    a single thread and PHIs can be reduced using reset value extraction.


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

    In this case PHI can select just based on value of %1 if the channel with its value is initialized to while0 branching value.
    However this is not implemented yet and control channels are generated instead.
    '''

    def _getBlockMeta(self, mb: MachineBasicBlock):
        """
        The code needs a synchronization if it starts a new thread without data dependencies and has predecessor thread.
        :note: They synchronization is always marked for the start of the thread.
        """
        # resolve control enable flag for a block
        mbSync: MachineBasicBlockSyncContainer = self.blockSync[mb]
        mbThreads: List[Set[HlsNetNode]] = self.threadsPerBlock[mb]
        loops: MachineLoopInfo = self.loops

        predThreadIds: Set[int] = set()
        for pred in mb.predecessors():
            pred: MachineBasicBlock
            predThreadIds.update(id(t) for t in self.threadsPerBlock[pred])
        threadsStartingThere = [t for t in mbThreads if id(t) not in predThreadIds]

        if mb.pred_size() == 0:
            mbSync.needsStarter = True

        if self.loops.isLoopHeader(mb):
            loop: MachineLoop = loops.getLoopFor(mb)
            # The synchronization is not required if it could be only by the data itself.
            # It can be done by data itself if there is an single output/write which has all
            # input as transitive dependencies (unconditionally.) And if this is an infinite cycle.
            # So we do not need to check the number of executions.
            needsControlOld = mbSync.needsControl
            if not mbSync.needsControl:
                
                if len(mbThreads) > 1 or mb.pred_size() > 1:
                    # multiple independent threads in body or more entry points to a loop
                    loopBodySelfSynchronized = True
                    for pred in mb.predecessors():
                        pred: MachineBasicBlock
                        if not loop.containsBlock(pred) and not self.blockSync[pred].needsStarter:
                            loopBodySelfSynchronized = False
                            break
                            
                    if loopBodySelfSynchronized and mb.pred_size() == 2:
                        pass
                    else:
                        mbSync.needsControl = True

                else:
                    if mb.succ_size() > 1:
                        mbSync.needsControl = True

                    if not mbSync.needsControl:
                        sucThreads = sum((len(self.threadsPerBlock[suc])
                                          for suc in mb.successors.iterBlocks()))
                        if sucThreads > 1:
                            mbSync.needsControl = True

            if not needsControlOld and mbSync.needsControl:
                self._onBlockNeedsControl(mb)

        elif not mbSync.needsControl:
            mbSync.needsControl = (
                len(threadsStartingThere) > 1 or
                (bool(mbThreads) and
                    (
                        any(self.blockSync[pred].needsControl for pred in mb.predecessors()) or
                        any(self.blockSync[suc].needsControl for suc in mb.successors())
                    )
                )
            )
            if mbSync.needsControl:
                self._onBlockNeedsControl(mb)

    def _onBlockNeedsControl(self, mb: SsaBasicBlock):
        for pred in mb.predecessors():
            mbSync: MachineBasicBlockSyncContainer = self.blockSync[pred]
            if not mbSync.needsControl:
                mbSync.needsControl = True
                if not mbSync.needsStarter and not pred.pred_size():
                    mbSync.needsStarter = True

                self._onBlockNeedsControl(pred)

        for suc in mb.successors():
            mbSync: MachineBasicBlockSyncContainer = self.blockSync[suc]
            if not mbSync.needsControl:
                mbSync.needsControl = True
                self._onBlockNeedsControl(suc)


    def run(self):
        from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
        originalMir: HlsNetlistAnalysisPassMirToNetlist = self.netlist.requestAnalysis(HlsNetlistAnalysisPassMirToNetlist)
        threads: HlsNetlistAnalysisPassDataThreads = self.netlist.requestAnalysis(HlsNetlistAnalysisPassDataThreads)
        self.threadsPerBlock = threads.threadsPerBlock
        self.blockSync = originalMir.blockSync
        self.loops: MachineLoopInfo = originalMir.loops

        for mb in originalMir.mf:
            mb: MachineBasicBlock
            self._getBlockMeta(mb)

