from copy import deepcopy
from io import StringIO
import networkx
from networkx.classes.digraph import DiGraph
import pydot
from typing import Set, List, Tuple, Generator

from hwtHls.frontend.pyBytecode.blockLabel import BlockLabel, \
    generateBlockLabel
from hwtHls.frontend.pyBytecode.frame import PyBytecodeLoopInfo
from hwtHls.frontend.pyBytecode.loopsDetect import PreprocLoopScope, \
    PyBytecodeLoop


class BlockPredecessorTracker():
    """
    An object used to track if all predecessors were resolved for SSA where blocks are generated conditionally and some blocks may be duplicated.

    :note: to_ssa._onAllPredecsKnown causes block to be sealed for PHIs and all PHIs are constructed and simplified when this function is called.
    However the blocks are generated conditionally based on if the jump values can be resolved compile time or in hw.

    This means that if we reach the block we know that there may be multiple predecessors from original CFG but some branches may be reduced
    compile time. And we do not know if we did not see this branch or if it was reduced if not noted explicitly.
    We also can not note all paths through CFG which are reduced because the number of such a paths if prohibiting.
    
    #But if we extract the loops and treat the entry points separately we can do this for linear segments of code:
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
      This unique label is generated from scope of currently evaluated loops and their iteration indexes and the label of original block.
    """

    def __init__(self, cfg: DiGraph, loopStack: List[PyBytecodeLoopInfo]):
        self.originalCfg = cfg
        self.cfg: DiGraph = deepcopy(cfg)
        self.generated: Set[BlockLabel] = set()
        self.notGenerated: Set[BlockLabel] = set()
        self.notGeneratedEdges: Set[Tuple[BlockLabel, BlockLabel]] = set()
        self.loopStack = loopStack

    def hasAllPredecessorsKnown(self, blockLabel: BlockLabel) -> bool:
        allPredecKnown = True
        for p in self.cfg.predecessors(blockLabel):
            isNotGenerated = p in self.notGenerated
            if p not in self.generated and not isNotGenerated:
                allPredecKnown = False
        return allPredecKnown
    
    def checkAllNewlyResolvedBlocks(self, blockWithPredecJustResolved: BlockLabel) -> Generator[BlockLabel, None, None]:
        allKnown = True
        for p in self.cfg.predecessors(blockWithPredecJustResolved):
            if p not in self.generated and p not in self.notGenerated:
                allKnown = False

        if allKnown:
            yield blockWithPredecJustResolved

    def addGenerated(self, block: BlockLabel) -> Generator[BlockLabel, None, None]:
        """
        Add a regular block which have a representation in output SSA.
        """
        assert block not in self.generated, block
        assert block not in self.notGenerated, block
        self.generated.add(block)
        yield from self.checkAllNewlyResolvedBlocks(block)
        for suc in self.cfg.successors(block):
            if suc in self.generated and suc != block:
                yield from self.checkAllNewlyResolvedBlocks(suc)

    def _getBlockLabelPrefix(self, blockOffset:int) -> Generator[PreprocLoopScope, None, None]:
        # the block can be outside of current loop body, if this is the case we have to pop several loop scopes
        for scope in self.loopStack:
            scope: PyBytecodeLoopInfo
            curLoop: PyBytecodeLoop = scope.loop
            if (blockOffset,) in curLoop.allBlocks:
                # in current loop
                yield PreprocLoopScope(scope.loop, scope.iteraionI)
            else:
                break

    def _getBlockLabel(self, blockOffset:int) -> BlockLabel:
        return generateBlockLabel(self._getBlockLabelPrefix(blockOffset), blockOffset)

    def _labelForBlockOutOfLoop(self, curScope: List[PreprocLoopScope],
                                dstBlockOffset: int,
                                viewFromLoopBody: bool) -> BlockLabel:
        prefix: List[PreprocLoopScope] = []
        for scope in curScope:
            scope: PreprocLoopScope
            if (dstBlockOffset,) in scope.loop.allBlocks:
                if viewFromLoopBody and dstBlockOffset == scope.loop.entryPoint[-1]:
                    # backedge pointing to entry point of a new iteration of loop body
                    scope = PreprocLoopScope(scope.loop, scope.iterationIndex + 1) 
                    prefix.append(scope)
                    break

                prefix.append(scope)

            elif prefix:
                # rest of prefix points on some other loop in parent loop
                break

        return (*prefix, dstBlockOffset)
    
    def _isReachableFromGenerated(self, block: BlockLabel, seen: Set[BlockLabel]) -> bool:
        if block in self.generated:
            return True
        if block in self.notGenerated:
            return False
        for pred in self.cfg.predecessors(block):
            if pred in seen or (pred, block) in self.notGeneratedEdges:
                continue
            seen.add(pred)
            if self._isReachableFromGenerated(pred, seen):
                return True
        return False
      
    def addNotGenerated(self, srcBlockLabel: BlockLabel, dstBlockLabel: BlockLabel) -> Generator[BlockLabel, None, None]:
        """
        Mark a block which was not generated and mark all blocks entirely dependent on not generated blocks also as not generated.
        (The information about not generated blocks is used to resolve which predecessor blocks are actually required for each generated block.)
        :attention: This does not catch the case where the block is a header of not generated cycle. 
        """
        e = (srcBlockLabel, dstBlockLabel)
        assert e not in self.notGeneratedEdges, e
        # assert block not in self.generated, block
        assert dstBlockLabel not in self.notGenerated, dstBlockLabel
        self.notGeneratedEdges.add(e)
        # if dstBlockLabel in self.generated:
        if dstBlockLabel not in self.cfg.nodes:
            return

        # isNotGenerated = True
        # for pred in self.cfg.predecessors(dstBlockLabel):
        #    if (pred, dstBlockLabel) not in self.notGeneratedEdges:
        #        if pred in self.generated:
        #            isNotGenerated = False
        #
        #        # we are not sure yet if this block is generated or not because we do not know about some predecessors
        #        return

        isNotGenerated = not self._isReachableFromGenerated(dstBlockLabel, set())
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
                        yield from self.checkAllNewlyResolvedBlocks(suc)
    
                    elif allPredecNotGenerated:
                        yield from self.addNotGenerated(dstBlockLabel, suc)
    
# , loopExitPlaceholder: BlockLabel
    def cfgAddPrefixToLoopBlocks(self, loop: PyBytecodeLoop, newPrefix: BlockLabel) -> Generator[BlockLabel, None, None]:
        """
        Add a prefix to loop body block labels and create a new entry point block for next loop body iteration.
        The entry point for next iteration is added behind this loop body and all edges which were originally going into entry point
        are redirected to this entry point. Original entry point is left only with edges which are entering the loop.
        
        :note: The next entry point must be generated in order to distinguish if all potential successors were processed
            for each block.
        """
        oldPrefix = (*newPrefix[:-1],)
        blockMap = {
            (*oldPrefix, *b): (*newPrefix, *b)
            for b in loop.allBlocks
        }
        cfg = self.cfg
        
        oldEntry = (*oldPrefix, *loop.entryPoint)
        # allEntryPredecAlreadyKnown = True
        # for p in self.cfg.predecessors(oldEntry):
        #    isNotGenerated = p in self.notGenerated
        #    if p not in self.generated and not isNotGenerated:
        #        allEntryPredecAlreadyKnown = False

        # for each node create a new one with updated name and also generate all edges
        for newNode in blockMap.values():
            cfg.add_node(newNode)

        # nextEntry = self._labelForBlockOutOfLoop(newPrefix, loop.entryPoint[-1], True)
        
        for origNode, newNode in blockMap.items():
            isSrcEntry = origNode[-1] == loop.entryPoint[-1]
            if isSrcEntry:
                # assert origNode in self.generated, (origNode, "Entrypoint should be generated because we are generating this loop body")
                # self.generated.add(newNode)
                # allPredecsKnown = True

                for pred in cfg.predecessors(origNode):
                    # if (pred not in self.generated and
                    #        pred not in self.notGenerated and
                    #        (pred[-1],) not in loop.allBlocks):
                        # allPredecsKnown = False
                    # add edges to loop header from outside of loop
                    # inLoop = pred in blockMap
                    # if not inLoop:
                    cfg.add_edge(pred, newNode)

                # for suc in cfg.successors(origNode):
                #     if suc not in blockMap:
                #         cfg.add_edge(nextEntry, suc)

                # if not allEntryPredecAlreadyKnown:
                #    if allPredecsKnown:
                #        # after remove of backedges entry block now have all predecessors known
                #        yield newNode

            for suc in cfg.successors(origNode):
                if suc == oldEntry:
                    # jump to next iteration of this loop body
                    # suc = nextEntry
                    continue  # we skip it because it will be added once we reach end of loop body

                else:
                    _suc = blockMap.get(suc, None)
                    if _suc is not None:
                        # if we are jumping in  loop we just use blockMap
                        suc = _suc

                    # elif isSrcEntry:
                    #    ## if this edge was transplanted to next entry point we skip it
                    #    continue # we skip it because it will be added once we reach end of loop body

                    else:
                        # in the case of we are jumping to a header from body of the loop
                        # we need to jump to next iteration of this loop
                        suc = self._labelForBlockOutOfLoop(newPrefix, suc[-1], True)

                cfg.add_edge(newNode, suc)

        # remove original nodes and left only replacements
        cfg.remove_nodes_from(blockMap.keys())
        return
        yield

    def cfgCopyLoopBlocks(self, loop: PyBytecodeLoop, newPrefix: BlockLabel) -> Generator[BlockLabel, None, None]:
        """
        Copy block of the loop and change prefix to labels.
        """
        cfg = self.cfg
        originalCfg = self.originalCfg
        # copy loop body basic block graph and connect it behind previous iteration
        # * an entry point block should be already created
        # * all edges from the loop body to loop header are redirected to next loop body header
        # * because the loop body can be in some other loop body and thus it can be renamed we have to
        #   use block labels from predecessor loop body for blocks outside of the loop
        # loopItLabel:PreprocLoopScope = newPrefix[-1]
        # prevItLabel = PreprocLoopScope(loop, loopItLabel.iterationIndex - 1)
        # oldPrefix: BlockLabel = (*newPrefix[:-1], prevItLabel)
        # curEntryPoint = (*newPrefix, *loop.entryPoint)
        # newEntryPoint = (*newPrefix, *loop.entryPoint)
        # nextEntry = self._labelForBlockOutOfLoop(newPrefix, loopItLabel.loop.entryPoint[-1], True)
        
        # for suc in tuple(cfg.successors(curEntryPoint)):
        #    cfg.remove_edge(curEntryPoint, suc)
        
        for nodeOffset in loop.allBlocks:
            cfg.add_node((*newPrefix, *nodeOffset))

        for originalNode in loop.allBlocks:
            newNode = (*newPrefix, *originalNode)
            # isFromEntry = originalNode[-1] == loop.entryPoint[-1] 
            for suc in originalCfg.successors(originalNode):
                inLoop = (suc[-1],) in loop.allBlocks
                isJmpToEntry = suc == loop.entryPoint
                if isJmpToEntry:
                    continue  # skip because we add this edge once we jump from loop body

                if inLoop:
                    suc = (*newPrefix, suc[-1])
                else:
                    suc = self._labelForBlockOutOfLoop(newPrefix, suc[-1], True)
    
                # if isFromEntry and not inLoop:
                #    cfg.add_edge(nextEntry, suc)
                # else:
                cfg.add_edge(newNode, suc)

        yield from []
        # yield from self.checkAllNewlyResolvedBlocks(nextEntry)

    def dumpCfgToDot(self, file: StringIO, sealedBlocks: Set[BlockLabel]):
        N = self.cfg
        graph_type = "digraph"
        strict = networkx.number_of_selfloops(N) == 0 and not N.is_multigraph()
        name = N.name
        graph_defaults = N.graph.get("graph", {})
        P = pydot.Dot("" if name == "" else f'"{name}"', graph_type=graph_type, strict=strict, **graph_defaults)
        
        legendTable = """<
<table border="0" cellborder="1" cellspacing="0">
  <tr><td bgcolor="LightGreen">sealed</td></tr>
  <tr><td bgcolor="LightBlue">generated</td></tr>
  <tr><td bgcolor="gray">notGenerated</td></tr>
  <tr><td bgcolor="white">generating</td></tr>
  <tr><td bgcolor="LightCoral">sealed not in generated</td></tr>
</table>>"""
        legend = pydot.Node("legend", label=legendTable, style='filled', shape="plain")
        P.add_node(legend)

        for n in N.nodes():
            if n in sealedBlocks:
                if n in self.generated:
                    color = "LightGreen"
                else:
                    assert n not in self.notGenerated, n
                    color = "LightCoral"
                
            elif n in self.generated:
                assert n not in self.notGenerated, n
                color = "LightBlue"
            elif n in self.notGenerated:
                color = "gray"
            else:
                color = "white"

            p = pydot.Node(str(n), fillcolor=color, style='filled')
            P.add_node(p)
    
        assert not N.is_multigraph()
        for u, v in N.edges():
            if (u, v) in self.notGeneratedEdges:
                attrs = {"color": "gray"}
            else:
                attrs = {}
            edge = pydot.Edge(str(u), str(v), **attrs)
            P.add_edge(edge)

        file.write(P.to_string())