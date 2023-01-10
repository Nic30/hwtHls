from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwt.pyUtils.uniqList import UniqList
from typing import Union, Set
from hwtHls.architecture.archElement import ArchElement
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.analysis.syncReach import BetweenSyncNodeIsland, \
    HlsNetlistAnalysisPassSyncReach
from hwtHls.netlist.nodes.orderable import HdlType_isNonData


def addOutputAndAllSynonymsToElement(o: HlsNetNodeOut, useT: int,
                                      synonyms: UniqList[Union[HlsNetNodeOut, HlsNetNodeIn]],
                                      dstElm: ArchElement,
                                      normalizedClkPeriod: int):
    # check if any synonym is already declared
    oRes = None
    for syn in synonyms:
        synRtl = dstElm.netNodeToRtl.get(syn, None)
        if synRtl is not None:
            assert oRes is None or oRes is synRtl, ("All synonyms must have same RTL realization", o, oRes, syn, synRtl)
            assert start_clk(synRtl.timeOffset, normalizedClkPeriod) == start_clk(useT, normalizedClkPeriod) , (synRtl.timeOffset, useT, syn, o)
            oRes = synRtl

    # now optionally declare and set all synonyms at input of dstElm
    if oRes is None:
        # if no synonym declared create a new declaration
        oRes = o.obj.allocateRtlInstanceOutDeclr(dstElm, o, useT)
        for syn in synonyms:
            dstElm.netNodeToRtl[syn] = oRes
    else:
        # declare also rest of the synonyms
        for syn in synonyms:
            synRtl = dstElm.netNodeToRtl.get(syn, None)
            if synRtl is None:
                dstElm.netNodeToRtl[o] = oRes


def expandAllOutputSynonymsInElement(iea: InterArchElementNodeSharingAnalysis):
    # a set used to avoid adding another sync channel if same if is already present
    seenOuts: Set[HlsNetNodeOut] = set()
    for o, _ in iea.interElemConnections:
        srcElm = iea.getSrcElm(o)
        # expand all synonyms at output of element
        if o in seenOuts:
            continue
        else:
            synonyms = iea.portSynonyms.get(o, ())
            if synonyms:
                foundRtl = None
                for syn in synonyms:
                    foundRtl = srcElm.netNodeToRtl.get(syn, None)
                    if foundRtl is not None:
                        break
                assert foundRtl is not None, "At least some synonym port must be defined"
                for syn in synonyms:
                    rtl = srcElm.netNodeToRtl.get(syn, None)
                    if rtl is None:
                        srcElm.netNodeToRtl[syn] = foundRtl
                    else:
                        assert rtl is foundRtl, "All synonyms must have same RTL object"
                    seenOuts.add(syn)

            else:
                seenOuts.add(o)
                assert o in srcElm.netNodeToRtl, o


def isDrivenFromSyncIsland(node: HlsNetNodeExplicitSync,
                           syncIsland: BetweenSyncNodeIsland,
                           syncReach: HlsNetlistAnalysisPassSyncReach) -> bool:
    for dep in node.dependsOn:
        if HdlType_isNonData(dep._dtype):
            continue
        else:
            isl = syncReach.syncIslandOfNode[dep.obj]
            if isl is syncIsland or (isinstance(isl, tuple) and (isl[0] is syncIsland or isl[1] is syncIsland)):
                return True
    return False
