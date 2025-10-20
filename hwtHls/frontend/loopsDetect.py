from networkx.classes.digraph import DiGraph
from typing import Set, NamedTuple, Dict, List, Tuple, TypeVar, Generic

from hwtHls.frontend.blockPredecessorTracker import BlockLabel
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, BasicBlock, IRBuilder, FunctionType, Type, \
    Function, UndefValue, VectorOfTypePtr, LoopInfo, Loop


BlockT = TypeVar("T")


class PyBytecodeLoop(Generic[BlockT]):
    """
    :note: Integers represents offset of instruction where block starts.
    """

    def __init__(self, label: str, entryPoint: BlockT, allBlocks: Set[BlockT], allEdges: Tuple[Tuple[BlockT, BlockT], ...]):  # , backedges: Set[int]
        self.label = label
        self.entryPoint = entryPoint
        self.allBlocks = allBlocks
        self.allEdges = allEdges

    @classmethod
    def _getLoopLabel(cls, entry: BlockT, loopIndex:int):
        if loopIndex == 0:
            return f"L{entry:d}"
        else:
            return f"L{entry:d}subL{loopIndex:d}"

    @classmethod
    def detectLoops(cls, cfg: DiGraph):
        llvm = LlvmCompilationBundle("PyBytecodeLoop.detectLoops.module", [])
        FT = FunctionType.get(Type.getVoidTy(llvm.ctx), VectorOfTypePtr(), False)
        F = llvm.main = Function.Create(FT, Function.LinkageTypes.ExternalLinkage, llvm.strCtx.addTwine("PyBytecodeLoop.detectLoops.main"), llvm.module)

        blockToNode: Dict[BasicBlock, BlockLabel] = {}
        nodeToBlock: Dict[BlockLabel, BasicBlock] = {}
        dummyName = llvm.strCtx.addTwine("")
        for n in cfg.nodes():
            bb = BasicBlock.Create(llvm.ctx, dummyName, F, None)
            blockToNode[bb] = n
            nodeToBlock[n] = bb

        undef1b = UndefValue.get(Type.getIntNTy(llvm.ctx, 1))
        builder: IRBuilder = llvm.builder
        for n in cfg.nodes():
            srcBb = nodeToBlock[n]
            successors = tuple(cfg.successors(n))
            sucLen = len(successors)
            if sucLen == 0:
                pass
            elif sucLen == 1:
                builder.SetInsertPoint(srcBb)
                sucT, = successors
                builder.CreateBr(nodeToBlock[sucT])
            elif sucLen == 2:
                builder.SetInsertPoint(srcBb)
                sucT, sucF = successors
                builder.CreateCondBr(undef1b, nodeToBlock[sucT], nodeToBlock[sucF], None)
            else:
                raise NotImplementedError(n, successors)

        loops = []

        def _addLoop(L: Loop):
            loopNodes: Set[BlockLabel] = set()
            for BB in L.blocks():
                BB: BasicBlock
                loopNodes.add(blockToNode[BB])

            header = blockToNode[L.getHeader()]
            label = cls._getLoopLabel(header, 0)
            loopEdges = tuple(cfg.subgraph(loopNodes).edges())
            loops.append(cls(label, header, loopNodes, loopEdges))
            for subLoop in L:
                _addLoop(subLoop)

        def collectLoops(LI: LoopInfo):
            for L in LI:
                _addLoop(L)

        llvm.runLoopAnalysisGet(collectLoops)

        return loops

    @classmethod
    def collectLoopsPerBlock(cls, cfg: DiGraph) -> Dict[BlockT, List["PyBytecodeLoop"]]:
        loops: Dict[BlockT, List[PyBytecodeLoop]] = {}
        for loop in cls.detectLoops(DiGraph(cfg)):
            entryOffset: BlockT = loop.entryPoint
            loopsPerBlock = loops.get(entryOffset, None)
            assert loopsPerBlock is None
            loops[entryOffset] = [loop, ]  # bottom most loop containing block
        return loops

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.entryPoint}>"


class PreprocLoopScope(NamedTuple("PreprocLoopScope", [("loop", PyBytecodeLoop),
                                                       ("iterationIndex", int)])):
    """
    Non-mutable label of preproc loop body segment.
    """

    def __new__(cls, loop: PyBytecodeLoop, iterationIndex: int):
        return super().__new__(cls, loop, iterationIndex)

    def __repr__(self):
        return str(self)

    def __str__(self):
        return f"{self.loop.label:s}i{self.iterationIndex}"
