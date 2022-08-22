from typing import Set, List, Union

from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineLoopInfo, MachineLoop
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.io import HlsNetNodeWrite, HlsNetNodeRead
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer


class HlsNetlistAnalysisPassBlockSyncType(HlsNetlistAnalysisPass):
    '''
    This pass updates blockSync dictionary in :class:`hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.mirToNetlist.HlsNetlistAnalysisPassMirToNetlist` with
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

    def _threadContainsNonConcurrentIo(self, thread: Set[HlsNetNode]):
        seenIos: Set[Union[InterfaceBase, RtlSignalBase]] = set()
        for n in thread:
            if isinstance(n, HlsNetNodeWrite):
                i = n.dst
            elif isinstance(n, HlsNetNodeRead):
                i = n.src
            else:
                i = None
            if i is not None:
                if i in seenIos:
                    return True
                else:
                    seenIos.add(i)

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

        needsControlOld = mbSync.needsControl

        if self.loops.isLoopHeader(mb):
            loop: MachineLoop = loops.getLoopFor(mb)
            # The synchronization is not required if it could be only by the data itself.
            # It can be done by data itself if there is an single output/write which has all
            # input as transitive dependencies (unconditionally.) And if this is an infinite cycle.
            # So we do not need to check the number of executions.
            if mbSync.rstPredeccessor is None and mb.pred_size() == 2:
                # one of predecessors may possibly be suitable for reset extraction
                p0, p1 = mb.predecessors()
                if p1.getNumber() == 0:
                    p0, p1 = p1, p0
                if p0.getNumber() == 0:
                    mbSync.rstPredeccessor = p0
                
            if not mbSync.needsControl:
                if not loop.hasNoExitBlocks():
                    # need sync to synchronize code behind the loop
                    mbSync.needsControl = True
    
                elif (len(mbThreads) > 1 or
                      (mb.pred_size() > 1 and (mb.pred_size() != 2 or not mbSync.rstPredeccessor)) or
                      not mbThreads or
                      self._threadContainsNonConcurrentIo(mbThreads[0])):
                    # multiple independent threads in body or more entry points to a loop
                    loopBodySelfSynchronized = True
                    for pred in mb.predecessors():
                        pred: MachineBasicBlock
                        isLoopReenter = loop.containsBlock(pred)
                        # reenter does not need explicit sync because it is synced by data
                        # rstPredeccessor does not need explicit sync because it will be inlined to reset values
                        if not isLoopReenter and mbSync.rstPredeccessor is not pred:
                            loopBodySelfSynchronized = False
                            break
                            
                    if loopBodySelfSynchronized and mb.pred_size() == 2:
                        pass
                    else:
                        mbSync.needsControl = True
        
                elif mb.succ_size() > 1:
                    mbSync.needsControl = True
        
                else:
                    sucThreads = sum((len(self.threadsPerBlock[suc])
                                      for suc in mb.successors()))
                    if sucThreads > 1:
                        mbSync.needsControl = True

            #if mbSync.needsControl and not mbSync.uselessOrderingFrom:
            #    loopHasOnly1Thread = True
            #    onlyDataThread = None
            #    for _mb in loop.getBlocks():
            #        _mbThreads = self.threadsPerBlock[_mb]
            #        if len(_mbThreads) > 1:
            #            loopHasOnly1Thread = True
            #        elif onlyDataThread is None:
            #            if _mbThreads:
            #                onlyDataThread = _mbThreads[0]
            #        elif _mbThreads:
            #            if onlyDataThread is not _mbThreads[0]:
            #                loopHasOnly1Thread = False
            #    # [fixme] if the block is part of FSM there is a problem caused by storing of control bit to register
            #    #         the FSM detect state transitions by the time when write happens
            #    #         if we allow the write of this bit before all IO is finished the FSM transition detection alg.
            #    #         will resolve IO as to skip if after control bit is written which is incorrect    
            #    if loopHasOnly1Thread:
            #        for pred in mb.predecessors():
            #            if loop.containsBlock(pred):
            #                mbSync.uselessOrderingFrom.add(pred)
                
        elif not mbSync.needsControl:
            needsControl = False
            if (len(threadsStartingThere) > 1 or 
                any(self._threadContainsNonConcurrentIo(t) for t in threadsStartingThere)):
                needsControl = True
            elif (bool(mbThreads) and
                    (
                        any(self.blockSync[pred].needsControl for pred in mb.predecessors()) or
                        any(self.blockSync[suc].needsControl for suc in mb.successors())
                    )
                ):
                needsControl = True
            elif (mbSync.needsStarter and 
                      (mb.succ_size() == 0 or
                       any(loops.getLoopFor(suc) is None for suc in mb.successors()))):
                needsControl = True
            mbSync.needsControl = needsControl

        if not needsControlOld and mbSync.needsControl:
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
        originalMir: HlsNetlistAnalysisPassMirToNetlist = self.netlist.getAnalysis(HlsNetlistAnalysisPassMirToNetlist)
        threads: HlsNetlistAnalysisPassDataThreads = self.netlist.getAnalysis(HlsNetlistAnalysisPassDataThreads)
        self.threadsPerBlock = threads.threadsPerBlock
        self.blockSync = originalMir.blockSync
        self.loops: MachineLoopInfo = originalMir.loops

        for mb in originalMir.mf:
            mb: MachineBasicBlock
            self._getBlockMeta(mb)

        entry: MachineBasicBlock = next(iter(originalMir.mf))
        entrySync: MachineBasicBlockSyncContainer = self.blockSync[entry]
        # if everything from entry was inlined to reset values and the successor is infinite loop we do not need starter
        if entrySync.needsStarter and not entrySync.needsControl and entry.succ_size() == 1:
            suc = next(iter(entry.successors()))
            sucSync: MachineBasicBlockSyncContainer = self.blockSync[suc]
            if self.loops.isLoopHeader(suc) and self.blockSync[suc].rstPredeccessor is entry and not sucSync.needsControl:
                entrySync.needsStarter = False

