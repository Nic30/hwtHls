from copy import deepcopy
from typing import Set, List, Tuple

from networkx.classes.digraph import DiGraph
from hwtHls.ssa.translation.fromPython.blockLabel import BlockLabel, \
    generateBlockLabel
from hwtHls.ssa.translation.fromPython.loopsDetect import PreprocLoopScope, \
    PyBytecodeLoop


class BlockPredecessorTracker():
    """
    :note: to_ssa._onAllPredecsKnown causes block to be sealed for PHIs and all PHIs are constructed and simplified when this function is called.
    However the blocks are generated conditionally based on if the jump values can be resolved compiletime or in hw.
    
    This means that if we reach the block we know that there may be multiple predecessors from original CFG but some branches may be reduced
    comipletime. And we do not know if we did not see this brach or if it was reduced if not noted explicitely.
    We also can not note all paths trought CFG wich are reduced because the number of such a paths if prohibiting.
    
    #But if we extract the loops and treat the entry points sparately we can do this for linear segments of code:
    * Entry point block is always hw block.
    * If the block is hw block and condition from it is hw evaluated, the successor is also hw block.
      If it is compile time evaluated we are reusing predecessor hw block and each path which was not taken we add to set of not generated nodes.
    * We have to compute transitive enclosure of this set if something new is added. The block is not generated if it was marked as not generated
      or all its predecessors are not generated.
    * Once each predecessors is in set of generated or not generated block the block should be sealed.
    * If this is a compile time evaluated loop we may have to create new blocks for body with every iteration.
      And treat it as a linear code as described in previous paragraph.
      In generated blocks from body we have to rewrite continue branches to jump to a header next loop body. 
      Generated blocks must have unique label in order to block sealing to work.
      This unique label is generated from scope of currently evalueated loops and their iteration indexes and the label of original block.

    """

    def __init__(self, cfg: DiGraph):
        self.originalCfg = cfg
        self.cfg: DiGraph = deepcopy(cfg)
        self.generated: Set[BlockLabel] = set()
        self.notGenerated: Set[BlockLabel] = set()
        self.notGeneratedEdges: Set[Tuple[BlockLabel, BlockLabel]] = set()
        self.preprocLoopScope: List[PreprocLoopScope] = []
        #orig_add_edge = self.cfg.add_edge

        #def add_edge(u_of_edge, v_of_edge):
        #    print("adding", u_of_edge, v_of_edge)
        #    return orig_add_edge(u_of_edge, v_of_edge)

        #self.cfg.add_edge = add_edge

    def checkAllNewlyResolvedBlocks(self, blockWithPredecJustResolved: BlockLabel):
        allKnown = True
        for p in self.cfg.predecessors(blockWithPredecJustResolved):
            if p not in self.generated and p not in self.notGenerated:
                allKnown = False

        if allKnown:
            yield blockWithPredecJustResolved
            # for suc in self.cfg.successors(blockWithPredecJustResolved):
            #    yield from self.checkAllNewlyResolvedBlocks(suc)

    def addGenerated(self, block: BlockLabel):
        """
        Add a regular block which have a representation in output SSA.
        """
        assert block not in self.generated
        assert block not in self.notGenerated
        self.generated.add(block)

        yield from self.checkAllNewlyResolvedBlocks(block)

    def _getBlockLabel(self, blockOffset:int) -> BlockLabel:
        # the block can be outside of curent loop body, if this is the case we have to pop several loop scopes
        preprocLoopScope = self.preprocLoopScope
        requiresSlice = False
        i = len(preprocLoopScope)
        for scope in reversed(preprocLoopScope):
            curLoop: PyBytecodeLoop = scope.loop
            if (blockOffset,) in curLoop.allBlocks:
                break  # in current loop
            i -= 1
            requiresSlice = True

        if requiresSlice:
            preprocLoopScope = preprocLoopScope[:i]

        return generateBlockLabel(preprocLoopScope, blockOffset)

    def addNotGenerated(self, srcBlockLabel: BlockLabel, dstBlockLabel: BlockLabel):
        """
        Mark a block which was not generated and mark all blocks entirely dependent on not generated blocks also as not generated.
        (The information about not generated blocks is used to resolve which predecessor blocks are actually required for each generated block.)
        """
        e = (srcBlockLabel, dstBlockLabel)
        assert e not in self.notGeneratedEdges, e
        # assert block not in self.generated, block
        assert dstBlockLabel not in self.notGenerated, dstBlockLabel
        self.notGeneratedEdges.add(e)
        # if dstBlockLabel in self.generated:
        isNotGenerated = True
        for pred in self.cfg.predecessors(dstBlockLabel):
            if (pred, dstBlockLabel) not in self.notGeneratedEdges:
                if pred in self.generated:
                    isNotGenerated = False
                return  # we are not sure yet if this block is generated or not

        if isNotGenerated:
            self.notGenerated.add(dstBlockLabel)

        for suc in self.cfg.successors(dstBlockLabel):
            allPredecKnown = True
            allPredecNotGenerated = True
            for p in self.cfg.predecessors(suc):
                isNotGenerated = p in self.notGenerated
                if p not in self.generated and not isNotGenerated:
                    allPredecKnown = False
                if not isNotGenerated:
                    allPredecNotGenerated = False

            if allPredecKnown:
                # recursively yield all successors which just got all predecessors resolved
                if suc in self.generated:
                    yield suc
                elif allPredecNotGenerated:
                    yield from self.addNotGenerated(dstBlockLabel, suc)

    def cfgAddPrefixToLoopBody(self, loop: PyBytecodeLoop, newPrefix: BlockLabel, deleteBackedges:bool):
        oldPrefix = (*newPrefix[:-1],)
        blockMap = {
            (*oldPrefix, *b): (*newPrefix, *b)
            for b in loop.allBlocks
        }
        cfg = self.cfg
        if deleteBackedges:
            dst = (*oldPrefix, *loop.entryPoint)
            for src in loop.backedges:
                cfg.remove_edge((*oldPrefix, *src), dst)

        # for each node create a new one with updated name and also generate all edges
        for newNode in blockMap.values():
            cfg.add_node(newNode)

        for origNode, newNode in blockMap.items():
            if origNode == loop.entryPoint[-1]:
                allPredecsKnown = True
                for pred in cfg.predecessors(origNode):
                    if pred not in self.generated and pred not in self.notGenerated:
                        allPredecsKnown = False
                    cfg.add_edge(blockMap.get(pred, pred), newNode)
                if allPredecsKnown:
                    yield newNode

            for suc in cfg.successors(origNode):
                cfg.add_edge(newNode, blockMap.get(suc, suc))

        # remove original nodes and left only replacements
        cfg.remove_nodes_from(blockMap.keys())

    def _labelForBlockOutOfLoop(self, curScope: List[PreprocLoopScope], dstBlockOffset: int):
        prefix = []
        for scope in curScope:
            if (dstBlockOffset, ) in scope.loop.allBlocks:
                prefix.append(scope)
        
        return (*prefix, dstBlockOffset)
        
    def cfgCopyLoopBody(self, loop: PyBytecodeLoop, newPrefix: BlockLabel, excludeBackedges:bool):
        cfg = self.cfg
        originalCfg = self.originalCfg
        # copy loop body basic block graph and connect it behind previous iteration
        # * all edges from the loop body to loop header are redirected to this newly generated loop body
        # * because the loop body can be in some other loop body and thus it can be renamed we have to
        #   use block labels from predecessor loop body for blocks outside of the loop
        # * [todo] old nodes could be already renamed or copied, we do not know exactly which is the original image
        loopItLabel:PreprocLoopScope = newPrefix[-1]
        prevItLabel = PreprocLoopScope(loop, loopItLabel.iterationIndex - 1)
        oldPrefix: BlockLabel = (*newPrefix[:-1], prevItLabel)

        for nodeOffset in loop.allBlocks:
            cfg.add_node((*newPrefix, *nodeOffset))

        for originalNode in loop.allBlocks:
            newNode = (*newPrefix, *originalNode)

            if originalNode[-1] == loop.entryPoint[-1]:
                for pred in originalCfg.predecessors(originalNode):
                    inLoop = pred[-1] in loop.allBlocks
                    if inLoop:
                        continue  # will be added from successor
                        # pred = (*newPrefix, pred[-1])
                    else:
                        pred = self._labelForBlockOutOfLoop(newPrefix, pred[-1])

                    cfg.add_edge(pred, newNode)

            for suc in originalCfg.successors(originalNode):
                inLoop = suc[-1] in loop.allBlocks
                if inLoop:
                    if excludeBackedges and suc[-1] == loop.entryPoint[-1]:
                        continue
                    suc = (*newPrefix, suc[-1])
                else:
                    suc = self._labelForBlockOutOfLoop(newPrefix, suc[-1])
                cfg.add_edge(newNode, suc)

        # entry point of previous loop body
        oldEntryPoint = (*oldPrefix, *loop.entryPoint)
        newEntryPoint = (*newPrefix, *loop.entryPoint)
        for pred in tuple(cfg.predecessors(oldEntryPoint)):
            inLoop = pred[-1] in loop.allBlocks
            if inLoop:
                cfg.remove_edge(pred, oldEntryPoint)
                cfg.add_edge(pred, newEntryPoint)

        # this removes the predecessors of previous loop body entry point, it may be the case that
        # all predecessors for the previous loop body are now resolved
        yield from self.checkAllNewlyResolvedBlocks(oldEntryPoint)

