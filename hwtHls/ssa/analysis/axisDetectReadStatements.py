from collections import defaultdict
from typing import Dict, Tuple

from hwt.pyUtils.uniqList import UniqList
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.ast.statements import HlsStm
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.io.amba.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.ssa.analysis.ssaAnalysisPass import SsaAnalysisPass
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtLib.amba.axis import AxiStream


class SsaAnalysisAxisDetectReadStatements(SsaAnalysisPass):
    """
    :ivar intfs: AxiStream interfaces discovered from read operations
    :ivar ioForIntf: Dictionary mapping interfaces to list of statements
        which are using it
    :ivar ios: list of all seen read statements
    """

    def __init__(self, toSsa: HlsAstToSsa):
        self.toSsa = toSsa
        self.intfs: UniqList[AxiStream]
        self.ioForIntf: Dict[AxiStream, UniqList[HlsStm]]
        self.ios: UniqList[HlsStm]

    def _detectIoAccessStatements(self, startBlock: SsaBasicBlock) \
            ->Tuple[UniqList[AxiStream], Dict[AxiStream, UniqList[HlsStm]], UniqList[HlsStm]]:
        ios: UniqList[HlsStm] = UniqList()
        for block in collect_all_blocks(startBlock, set()):
            for instr in block.body:
                if isinstance(instr, (HlsStmReadAxiStream, HlsStmReadStartOfFrame, HlsStmReadEndOfFrame)):
                    ios.append(instr)

        intfs: UniqList[AxiStream] = UniqList()
        ioForIntf: Dict[AxiStream, UniqList[HlsStm]] = defaultdict(UniqList)
        for io in ios:
            intfs.append(io._src)
            ioForIntf[io._src].append(io)

        return intfs, ioForIntf, ios

    def run(self):
        self.intfs, self.ioForIntf, self.ios = self._detectIoAccessStatements(self.toSsa.start)


