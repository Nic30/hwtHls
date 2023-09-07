from typing import Dict, Union

from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.ssa.analysis.axisDetectReadStatements import SsaAnalysisAxisDetectReadStatements
from hwtHls.ssa.analysis.axisDetectWriteStatements import SsaAnalysisAxisDetectWriteStatements
from hwtHls.ssa.analysis.ssaAnalysisPass import SsaAnalysisPass
from hwtHls.ssa.analysis.streamReadWriteGraphDetector import StreamReadWriteGraphDetector
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtLib.amba.axis import AxiStream
from ipCorePackager.constants import DIRECTION




class SsaAnalysisAxisDetectIoAccessGraph(SsaAnalysisPass):

    def __init__(self, toSsa: HlsAstToSsa, intf: AxiStream, direction: DIRECTION):
        self.toSsa = toSsa
        self.intf = intf
        self.direction = direction
        self.cfg: StreamReadWriteGraphDetector
        self.predecessorsSeen: Dict[Union[HlsRead, HlsWrite], int]
        self.startBlock: SsaBasicBlock

    def __hash__(self):
        return hash((self.__class__, self.intf))

    def __eq__(self, other):
        return other.__class__ is self.__class__ and self.intf is other.intf

    def run(self):
        toSsa = self.toSsa
        if self.direction == DIRECTION.IN:
            stmAnalysisCls = SsaAnalysisAxisDetectReadStatements
        else:
            assert self.direction == DIRECTION.OUT
            stmAnalysisCls = SsaAnalysisAxisDetectWriteStatements

        stms = toSsa.getAnalysis(stmAnalysisCls)

        cfg = StreamReadWriteGraphDetector(self.intf.DATA_WIDTH, stms.ioForIntf[self.intf])
        cfg.detectIoAccessGraphs(None, 0, toSsa.start, set())
        cfg.resolvePossibleOffset()
        cfg.finalize()
        self.cfg = cfg
        self.startBlock = cfg.findStartBlock()
