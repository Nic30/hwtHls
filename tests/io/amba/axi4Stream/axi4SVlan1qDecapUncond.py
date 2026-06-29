#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hwIOs.utils import addClkRstn, propagateClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pragmaFunction import PyBytecodeThreadExtractIoFsm
from hwtHls.frontend.pragmaLoop import PyBytecodeLoopFlattenUsingIf, \
    PyBytecodeStreamSegmentLoopUnroll, PyBytecodeStreamLoopUnroll
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline, \
    PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream, \
    IoProxyAxi4StreamSegmented
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.types.net.ethernet import Eth2Header_t, Eth802_1qHeader_t
from tests.io.amba.axi4StreamSegmented.axi4ssSegmentMerge import Axi4SSStreamMerge
from tests.io.amba.axi4StreamSegmented.axi4ssSegmentUnmerge import Axi4SSStreamUnmerge


@PyBytecodeInline
@hlsBytecode
def forwardUntilEoF(rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream, loopPragmaGetter=lambda: None):
    PyBytecodeBlockLabel("bb.forwardUntilEoF.entry")
    while b1:
        PyBytecodeBlockLabel("bb.forwardUntilEoF.head")
        # read at most the word and forward it to output
        # (the code is sw like, but of couser on low level the data may be
        # shifted and buffered to match throughput if streams are not aligned)
        if isinstance(rx, IoProxyAxi4StreamSegmented):
            PyBytecodeBlockLabel("bb.forwardUntilEoF.axi4ss.head")
            word_t = rx.interface.data[0]._dtype
            word = rx.read(word_t, reliable=False)
            tx.write(word.data, empty=word.empty, eof=word._isEoF())

        else:
            PyBytecodeBlockLabel("bb.forwardUntilEoF.axi4s.head")
            word_t = rx.interface.data._dtype
            word = rx.read(word_t, reliable=False)
            tx.write(word.data, mask=word.strb, eof=word._isEoF())

        PyBytecodeBlockLabel("bb.forwardUntilEoF.latch")
        loopPragmaGetter()
        if word._isEoF():
            PyBytecodeBlockLabel("bb.forwardUntilEoF.exit")
            break

    PyBytecodeBlockLabel("bb.forwardUntilEoF.ret")


class Axi4SVlan1qDecapUncond(HwModule):
    """
    Assume that each frame has  802.1Q vlan tag, pop it from frame
    """
    AXI_CLS = Axi4Stream

    @override
    def hwConfig(self) -> None:
        self.AXI_CLS.hwConfig(self)
        self.CLK_FREQ = HwParam(int(100e6))
        self.PREFER_MULTI_THREAD = HwParam(False)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = self.AXI_CLS()
            self.tx = self.AXI_CLS()._m()
            for c in (self.rx, self.tx):
                c.USE_STRB = True

    # def reduceOrdering(self, hls: HlsScope, thread: HlsThreadFromPy):
    #    """
    #    Allow to read new rx data before tx data is put to output
    #    """
    #    netlist = thread.netlist
    #    for rwNode in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
    #        if isinstance(rwNode, HlsNetNodeWrite):
    #            rwNode: HlsNetNodeWrite
    #            depO = rwNode.dependsOn[rwNode._portSrc.in_i].obj
    #            if rwNode.dst is self.tx or (isinstance(depO, HlsNetNodeRead) and depO.src is self.rx):
    #                netlistExplicitSyncDisconnectFromOrderingChain(DebugTracer(None), rwNode, None,
    #                                                               disconnectPredecessors=True,
    #                                                               disconnectSuccesors=True)
    #                break
    #
    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        if self.AXI_CLS is Axi4StreamSegmented and self.PREFER_MULTI_THREAD and self.SEGMENT_CNT > 1:
            unmerge = Axi4SSStreamUnmerge()
            unmerge.SEGMENT_CNT = self.SEGMENT_CNT
            unmerge.SEGMENT_DATA_WIDTH = self.SEGMENT_DATA_WIDTH
            unmerge.CLK_FREQ = self.CLK_FREQ
            self.unmerge = unmerge

            merge = Axi4SSStreamMerge()
            merge.SEGMENT_CNT = merge.INPUT_CNT = self.SEGMENT_CNT
            merge.SEGMENT_DATA_WIDTH = self.SEGMENT_DATA_WIDTH
            merge.CLK_FREQ = self.CLK_FREQ
            self.merge = merge

            propagateClkRstn(self)
            for rx, tx in zip(unmerge.tx, merge.rx):
                t = HlsThreadFromPy(hls, self.mainThread,
                                             hls, IoProxyAxi4StreamSegmented(hls, rx),
                                                  IoProxyAxi4StreamSegmented(hls, tx))

                hls.addThread(t)

            unmerge.rx(self.rx)
            self.tx(merge.tx)
            hls.compile()

        else:
            if self.AXI_CLS is Axi4StreamSegmented:
                rx = IoProxyAxi4StreamSegmented(hls, self.rx)
                tx = IoProxyAxi4StreamSegmented(hls, self.tx)
            else:
                rx = IoProxyAxi4Stream(hls, self.rx)
                tx = IoProxyAxi4Stream(hls, self.tx)

            mainThread = HlsThreadFromPy(hls, self.mainThread,
                                         hls, rx, tx)
            # mainThread.netlistCallbacks.append(self.reduceOrdering)

            # 1. Allow last tx to finish after iteration of copy loop
            #    otherwise the loop body will take 2 or more clock cycles
            # 2. Extract begin section of bb.pktLoop as a pipeline which consumes first word, then forwards the rest

            # for low-freq designs:
            #  1. the first section will be activated at the beginning of the packet
            #    arbieter will decide when to pass data to second arch element which implements the main copy loop and shift logic
            #  2. assume that output can accept 2 words at once, construct delay pipe for distribution of input data

            # for hi-freq designs:
            #  * the problem is that there is always 1 more write than reads and the backedge
            #    of write of the main loop (allows for start of new iteration)  is scheduled
            #    after last write, this prevents circuit from reading next packet until all data have been flushed
            #    this interwires update of parser with update of deparser and makes it more complex, in some cases
            #    this may result in loop roundtrip time >1 which limits the troughput
            # 1. cut out deparser thread
            # 2. rest is the same
            hls.addThread(mainThread)
            hls.compile()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        while b1:
            PyBytecodeBlockLabel("bb.pktLoop.head")
            rx.readStartOfFrame()
            eth_802_1q = rx.read(Eth802_1qHeader_t, reliable=True).data
            eth = Eth2Header_t.from_py(None)
            # copy all props to eth
            for field in Eth2Header_t.fields:
                PyBytecodeBlockLabel("bb.pktLoop.set." + field.name)
                setattr(eth, field.name, getattr(eth_802_1q, field.name))

            PyBytecodeBlockLabel("bb.pktLoop.txSof")
            tx.writeStartOfFrame()
            tx.write(eth)
            forwardUntilEoF(rx, tx,
                loopPragmaGetter=lambda: PyBytecodeStreamLoopUnroll(tx.interface, alignLoopBodyBeginByPrequelExtract=True,
                                         # followup_unrolled=PyBytecodeLoopFlattenUsingIf(mode=PyBytecodeLoopFlattenUsingIf.Mode.CHILD_LOOP_ENTRY_IN_SAME_ITERATION)
            ))
            tx.writeEndOfFrame()
            rx.readEndOfFrame()
            # PyBytecodeThreadExtractIoFsm(tx)
            PyBytecodeBlockLabel("bb.pktLoop.latch")
            PyBytecodeStreamSegmentLoopUnroll(rx)


class Axi4SSVlan1qDecapUncond(Axi4SVlan1qDecapUncond):
    AXI_CLS = Axi4StreamSegmented


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = Axi4SVlan1qDecapUncond()
    m.CLK_FREQ = int(1e6)
    # m.PREFER_MULTI_THREAD = False
    m.DATA_WIDTH = 64
    # m.SEGMENT_DATA_WIDTH = 128
    # m.SEGMENT_CNT = 1
    # m.USE_SOF = True

    p = VirtualHlsPlatform(
        debugFilter={
           *HlsDebugBundle.ALL_RELIABLE,
           HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
           HlsDebugBundle.DBG_4_0_addSignalNamesToData,
        },
        llvmCliArgs=[
            LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
            # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED
        ])
    print(to_rtl_str(m, target_platform=p))

