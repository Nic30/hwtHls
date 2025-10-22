#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.llvmIr.HwtHlsInstCombinePass_bitcountExtract_test import HwtHlsInstCombinePass_bitcountExtract_TC
from tests.llvmIr.HwtHlsInstCombinePass_select_test import HwtHlsInstCombinePass_select_TC
from tests.llvmIr.HwtHlsInstCombinePass_streamEoFThreading_test import HwtHlsInstCombinePass_streamEoFThreading_TC
from tests.llvmIr.HwtHlsInstCombinePass_test import HwtHlsInstCombinePass_TC
from tests.llvmIr.LoopRotationNormalizationPass_test import LoopRotationNormalizationPass_TC
from tests.llvmIr.HwtHlsSimplifyCFGPass_phiToLogicalExpr_test import HwtHlsSimplifyCFGPass_phiToLogicalExp_TC
from tests.llvmIr.HwtHlsSimplifyCFGPass_streamWrite_test import HwtHlsSimplifyCFGPass_streamWrite_TC
from tests.llvmIr.HwtHlsSimplifyCFGPass_test import HwtHlsSimplifyCFGPass_TC
from tests.llvmIr.StreamReadLoweringPass_test import StreamReadLoweringPass_TC
from tests.llvmIr.bitWidthReductionPass_Cmp_test import BitWidthReductionPass_Cmp_TCs
from tests.llvmIr.bitWidthReductionPass_PHI_inLoopHeader_test import BitwidthReductionPass_PHI_inLoopHeader_TC
from tests.llvmIr.bitWidthReductionPass_PHI_test import BitwidthReductionPass_PHI_TC
from tests.llvmIr.bitWidthReduction_test import BitwidthReductionPass_TC
from tests.llvmIr.functionMutating_test import LlvmIrFunctionMutating_TC
from tests.llvmIr.llvmLoopUnroll_test import LlvmLoopUnroll_TC
from tests.llvmIr.loopFlattenUsingIfPass_test import LoopFlattenUsingIfPass_TC
from tests.llvmIr.rewriteExtractOnMergeValues_test import RewriteExtractOnMergeValuesPass_TC
from tests.llvmIr.selectPruningPass_test import SelectPruningPass_TC
from tests.llvmIr.slicesMergePass_select_test import SlicesMergePass_select_TC
from tests.llvmIr.slicesMergePass_test import SlicesMergePass_TC
from tests.llvmIr.slicesToIndependentVariablesPass_test import SlicesToIndependentVariablesPass_TC
from tests.testCaseUtils import testSuiteFromTCs
from tests.llvmIr.HwtHlsInstCombinePass_concat_test import HwtHlsInstCombinePass_concat_TC


llvmIr_TCs = [
    LlvmIrFunctionMutating_TC,
    SlicesToIndependentVariablesPass_TC,
    HwtHlsSimplifyCFGPass_TC,
    HwtHlsInstCombinePass_select_TC,
    HwtHlsSimplifyCFGPass_phiToLogicalExp_TC,
    HwtHlsSimplifyCFGPass_streamWrite_TC,
    LoopRotationNormalizationPass_TC,
    LoopFlattenUsingIfPass_TC,
    PruneLoopPhiDeadIncomingValuesPass_TC,
    RewriteExtractOnMergeValuesPass_TC,
    HwtHlsInstCombinePass_TC,
    HwtHlsInstCombinePass_concat_TC,
    HwtHlsInstCombinePass_bitcountExtract_TC,
    HwtHlsInstCombinePass_streamEoFThreading_TC,
    SlicesMergePass_TC,
    SlicesMergePass_select_TC,
    BitwidthReductionPass_TC,
    BitwidthReductionPass_PHI_TC,
    BitwidthReductionPass_PHI_inLoopHeader_TC,
    *BitWidthReductionPass_Cmp_TCs,
    SelectPruningPass_TC,
    LlvmLoopUnroll_TC,
    StreamReadLoweringPass_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*llvmIr_TCs))
