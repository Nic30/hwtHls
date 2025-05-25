#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.testCaseUtils import testSuiteFromTCs
from tests.llvmIr.HwtHlsInstCombinePass_bitcountExtract_test import HwtHlsInstCombinePass_bitcountExtract_TC
from tests.llvmIr.HwtHlsInstCombinePass_streamEoFThreading_test import HwtHlsInstCombinePass_streamEoFThreading_TC
from tests.llvmIr.HwtHlsInstCombinePass_test import HwtHlsInstCombinePass_TC
from tests.llvmIr.LoopRotationNormalizationPass_test import LoopRotationNormalizationPass_TC
from tests.llvmIr.PruneLoopPhiDeadIncomingValuesPass_test import PruneLoopPhiDeadIncomingValuesPass_TC
from tests.llvmIr.SimplifyCFG2Pass_streamWrite_test import SimplifyCFG2Pass_streamWrite_TC
from tests.llvmIr.SimplifyCFG2Pass_test import SimplifyCFG2Pass_TC
from tests.llvmIr.bitWidthReductionPass_Cmp_test import BitWidthReductionPass_Cmp_example_TC
from tests.llvmIr.bitWidthReductionPass_PHI_inLoopHeader_test import BitwidthReductionPass_PHI_inLoopHeader_TC
from tests.llvmIr.bitWidthReductionPass_PHI_test import BitwidthReductionPass_PHI_TC
from tests.llvmIr.bitWidthReduction_test import BitwidthReductionPass_TC
from tests.llvmIr.llvmLoopUnroll_test import LlvmLoopUnroll_TC
from tests.llvmIr.loopFlattenUsingIfPass_test import LoopFlattenUsingIfPass_TC
from tests.llvmIr.rewriteExtractOnMergeValues_test import RewriteExtractOnMergeValuesPass_TC
from tests.llvmIr.selectPruningPass_test import SelectPruningPass_TC
from tests.llvmIr.slicesMergePass_select_test import SlicesMergePass_select_TC
from tests.llvmIr.slicesMergePass_test import SlicesMergePass_TC
from tests.llvmIr.slicesToIndependentVariablesPass_test import SlicesToIndependentVariablesPass_TC

llvmIr_TCs = [
    SlicesToIndependentVariablesPass_TC,
    SimplifyCFG2Pass_TC,
    SimplifyCFG2Pass_streamWrite_TC,
    LoopRotationNormalizationPass_TC,
    LoopFlattenUsingIfPass_TC,
    PruneLoopPhiDeadIncomingValuesPass_TC,
    RewriteExtractOnMergeValuesPass_TC,
    HwtHlsInstCombinePass_TC,
    HwtHlsInstCombinePass_bitcountExtract_TC,
    HwtHlsInstCombinePass_streamEoFThreading_TC,
    SlicesMergePass_TC,
    SlicesMergePass_select_TC,
    BitwidthReductionPass_TC,
    BitwidthReductionPass_PHI_TC,
    BitwidthReductionPass_PHI_inLoopHeader_TC,
    BitWidthReductionPass_Cmp_example_TC,
    SelectPruningPass_TC,
    LlvmLoopUnroll_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*llvmIr_TCs))
