#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn, propagateClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.frontend.threadFromLlvmIr import HlsThreadFromLlvmIr
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, \
    parseIR, SMDiagnostic, verifyModule, HwtHlsIoMetadata, IODirection, HwtHlsIoMetadataSmallVector, \
    HwtHlsIoMetadata_set, Module
from hwtHls.scope import HlsScope
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtLib.handshaked.reg_test import HandshakedRegL1D0TC
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC


class ExampleThreadHwtComponent_regDirect(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        i = self.dataIn = HwIOStructRdVld()
        o = self.dataOut = HwIOStructRdVld()._m()
        i.T = o.T = HBits(self.DATA_WIDTH, signed=False)

    IR_STR = """\
        source_filename = "hwtHlsModule"
        target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
        
        define void @reg(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) !hwthls.thread.hwtcomponent !0 {
        bb0:
          ret void
        }
        ; constructor path,
        ; constructor args,
        ; constructor kwargs,
        ; HwParam values,
        ; (the connection is done based on arg names by default but can be overriden in last optional arg)
        !0 = distinct !{!1, !2, !5, !6, !7}
        !1 = !{!"hwtLib", !"handshaked", !"reg", !"HandshakedReg"} ; constructor path
        !2 = !{!3} ; args, 
        ; kwargs are optional tuple with {name, value}+ for keyword args
        !3 = !{!"pyobj", !4}
        !4 = !{!"hwt", !"hwIOs", !"std", !"HwIODataRdVld"}
        !5 = !{}
        !6 = !{!"DATA_WIDTH", i64 8}
        !7 = !{}
        """

    def constructIR(self, t: HlsThreadFromLlvmIr):
        llvm = t.toLlvm.llvm
        Err = SMDiagnostic()
        M = parseIR(self.IR_STR, self.__class__.__name__, Err, llvm.ctx)
        if M is None:
            raise AssertionError(Err.str("test", True, True))
        else:
            llvm.module = M
            llvm._tryToFindMain()
        if verifyModule(M):
            raise AssertionError()
        tr: ToLlvmIrTranslator = t.toLlvm
        hls = t.hls
        ioMd = HwtHlsIoMetadataSmallVector()
        for i, (hwio, dir_) in enumerate(((self.dataIn, IODirection.IO_DIR_IN),
                                          (self.dataOut, IODirection.IO_DIR_OUT))):
            ioProxy = IoProxyScalar(hls, hwio)
            hls._ioProxyForIo[hwio] = ioProxy
            tr.ioToArgIndex[hwio] = i
            md = HwtHlsIoMetadata()
            md.direction = dir_
            md.otherArgIndex = i
            if dir_ == IODirection.IO_DIR_IN:
                wordT = ioProxy.getDataTypeOfNativeRead()
                md.readWordWidth = wordT.bit_length()
            else:
                wordT = ioProxy.getDataTypeOfNativeWrite()
                md.writeWordWidth = wordT.bit_length()
            ioMd.push_back(md)
            addrWidth = 0
            tr.ioSorted.append((hwio, wordT, addrWidth, ioProxy,
                                 [], [], md))
        HwtHlsIoMetadata_set(llvm.main, ioMd)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        hls.addThread(HlsThreadFromLlvmIr(hls, self.constructIR))
        hls.compile()
        propagateClkRstn(self)


class ExampleThreadHwtComponent_regThreadToThread(ExampleThreadHwtComponent_regDirect):
    IR_STR = """\
        source_filename = "hwtHlsModule"
        target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"

        define void @t0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb0:
          br label %bb1
        bb1:
          %0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
          store volatile i8 %0, ptr addrspace(2) %dataOut, align 1
          br label %bb1
        }
        
        define void @tReg(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) !hwthls.thread.hwtcomponent !0 {
        bb0:
          ret void
        }

        define void @t1(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb0:
          br label %bb1
        bb1:
          %0 = load volatile i8, ptr addrspace(1) %dataIn, align 1
          store volatile i8 %0, ptr addrspace(2) %dataOut, align 1
          br label %bb1
        }

        !0 = distinct !{!1, !2, !5, !6, !7}
        !1 = !{!"hwtLib", !"handshaked", !"reg", !"HandshakedReg"}
        !2 = !{!3} ; args, 
        !3 = !{!"pyobj", !4}
        !4 = !{!"hwt", !"hwIOs", !"std", !"HwIODataRdVld"}
        !5 = !{}
        !6 = !{!"DATA_WIDTH", i64 8}
        !7 = !{}
        """

    def constructIR(self, t: HlsThreadFromLlvmIr):
        llvm: LlvmCompilationBundle = t.toLlvm.llvm
        Err = SMDiagnostic()
        M: Module = parseIR(self.IR_STR, self.__class__.__name__, Err, llvm.ctx)
        if M is None:
            raise AssertionError(Err.str("test", True, True))
        else:
            llvm.module = M

        if verifyModule(M):
            raise AssertionError()
        strCtx = t.toLlvm.strCtx
        t0F = M.getFunction(strCtx.addStringRef("t0"))
        tRegF = M.getFunction(strCtx.addStringRef("tReg"))
        t1F = M.getFunction(strCtx.addStringRef("t1"))
        tr: ToLlvmIrTranslator = t.toLlvm
        hls = t.hls
        t0_ioMds = HwtHlsIoMetadataSmallVector()
        tReg_ioMds = HwtHlsIoMetadataSmallVector()
        t1_ioMds = HwtHlsIoMetadataSmallVector()
        for i, (hwio, dir_) in enumerate(((self.dataIn, IODirection.IO_DIR_IN),
                                          (self.dataOut, IODirection.IO_DIR_OUT))):
            ioProxy = IoProxyScalar(hls, hwio)
            hls._ioProxyForIo[hwio] = ioProxy
            tr.ioToArgIndex[hwio] = i
            md = HwtHlsIoMetadata()
            md.direction = dir_
            md.otherArgIndex = i
            if dir_ == IODirection.IO_DIR_IN:
                wordT = ioProxy.getDataTypeOfNativeRead()
                md.readWordWidth = wordT.bit_length()
                tReg_ioMd = HwtHlsIoMetadata()
                t1_ioMd = HwtHlsIoMetadata()
                tReg_ioMd.direction = t1_ioMd.direction = dir_
                tReg_ioMd.otherArgIndex = t1_ioMd.otherArgIndex = 1
                tReg_ioMd.readWordWidth = t1_ioMd.readWordWidth = md.readWordWidth

                t0_ioMds.push_back(md)

                tReg_ioMd.otherThreadFn = t0F
                tReg_ioMds.push_back(tReg_ioMd)

                t1_ioMd.otherThreadFn = tRegF
                t1_ioMds.push_back(t1_ioMd)
            else:
                wordT = ioProxy.getDataTypeOfNativeWrite()
                md.writeWordWidth = wordT.bit_length()

                t0_ioMd = HwtHlsIoMetadata()
                tReg_ioMd = HwtHlsIoMetadata()
                t0_ioMd.direction = tReg_ioMd.direction = dir_
                t0_ioMd.otherArgIndex = tReg_ioMd.otherArgIndex = 0
                t0_ioMd.writeWordWidth = tReg_ioMd.writeWordWidth = md.writeWordWidth

                t0_ioMd.otherThreadFn = tRegF
                t0_ioMds.push_back(t0_ioMd)

                tReg_ioMd.otherThreadFn = t1F
                tReg_ioMds.push_back(tReg_ioMd)

                t1_ioMds.push_back(md)

            addrWidth = 0
            tr.ioSorted.append((hwio, wordT, addrWidth, ioProxy,
                                 [], [], md))
        HwtHlsIoMetadata_set(t0F, t0_ioMds)
        HwtHlsIoMetadata_set(tRegF, tReg_ioMds)
        HwtHlsIoMetadata_set(t1F, t1_ioMds)


class ThreadHwtComponentReg_rtl_TC(SimTestCase):
    DELAY = 0
    MAX_LATENCY = 1

    def _test_no_comb_loops(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)

    def _test_pass_data(self, cls: Type[ExampleThreadHwtComponent_regDirect], N: int=20, randomize=False):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        if randomize:
            HandshakedRegL1D0TC.test_r_passdata(self, N=N)
        else:
            HandshakedRegL1D0TC.test_passdata(self, N=N)

    def test_direct_passdata(self, N=20):
        self._test_pass_data(ExampleThreadHwtComponent_regDirect, N=N, randomize=False)

    def test_direct_r_passdata(self, N=20):
        self._test_pass_data(ExampleThreadHwtComponent_regDirect, N=N, randomize=True)

    def test_threadToThread_passdata(self, N=20):
        self._test_pass_data(ExampleThreadHwtComponent_regThreadToThread, N=N, randomize=False)

    def test_threadToThread_r_passdata(self, N=20):
        self._test_pass_data(ExampleThreadHwtComponent_regThreadToThread, N=N, randomize=True)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.virtual import VirtualHlsPlatform

    m = ExampleThreadHwtComponent_regThreadToThread()
    print(to_rtl_str(m,
                    target_platform=VirtualHlsPlatform(
                        llvmCliArgs=[#LLVM_CLI_COMMON_OPTS.PRINT_CHANGED
                                     #LLVM_CLI_COMMON_OPTS.printAfter("hwtfpga-tonetlist")
                                     ],
                        debugFilter=HlsDebugBundle.ALL_RELIABLE,
                        )
                    ))
    
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([ThreadHwtComponentReg_rtl_TC('test_pktTrim')])
    suite = testLoader.loadTestsFromTestCase(ThreadHwtComponentReg_rtl_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
