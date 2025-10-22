#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import In
from hwt.hdl.commonConstants import b1, b0
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.platform.xilinx.fromVitisDB import HlsPlatformFromVitisDB
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.types.ctypes import uint8_t
from hwtLib.types.net.ethernet import Eth2Header_t, ETHER_TYPE
from hwtLib.types.net.ip import IPv4Header_t, IPv6Header_t, IP_PROTOCOL, \
    IPv6ExtCommonHeader_t, l4port_t, ipv6_t
from hwtLib.types.net.tcp import TCP_header_t
from hwtLib.types.net.udp import UDP_header_t


class Axi4SParse5Tuple(HwModule):
    """
    Example used in https://dl.acm.org/doi/10.1145/3174243.3174270, https://arxiv.org/pdf/1711.06613
    Ethernet, IPv4/IPv6 (with 2 extensions), UDP, TCP, and ICMP/ICMPv6;
    """
    AXI_CLS = Axi4Stream

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(256)
        self.CLK_FREQ = HwParam(int(100e6))
        self.USE_STRB:bool = HwParam(False)
        self.USE_KEEP:bool = HwParam(False)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = self.AXI_CLS()
        # :note: if width of o >>> width of i consider using stream
        #  for outputs as steaam with fixed position of fields is nearly overhead-less
        #  and lower bitwidth means lower consumption of registers/rams
        self.tx: HwIOStructVld = HwIOStructVld()._m()
        self.tx.T = HStruct(
            (uint8_t, "proto"),
            (BIT, "isIPv6"),
            (ipv6_t, "src"),
            (ipv6_t, "dst"),
            (l4port_t, "srcp"),
            (l4port_t, "dstp"),
        )

    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: IoProxyAxi4Stream) -> None:
        UDP_TCP = (IP_PROTOCOL.TCP, IP_PROTOCOL.UDP)
        # :note: using block labels for better readability of generated code
        PyBytecodeBlockLabel("bb.entry")
        while b1:
            rx.readStartOfFrame()
            PyBytecodeBlockLabel("bb.eth")
            # :note: Sequential reads/writes are merged into one during
            #  preprocessing but many small field reads/writes may increase
            #  compilation time, reading larger chunks is preffered
            # :note: using reliable=True because there must be some data as minimal Ethernet frame has 64B
            #        and reliable=False may generate checks for eofs which may complicate circuit significantly for smaller
            #        bitwidths
            eth = rx.read(Eth2Header_t, reliable=True).data
            res = self.tx.T.from_py({"proto": 0})
            res.isIPv6 = b0
            if eth.type._eq(ETHER_TYPE.IPv4):
                PyBytecodeBlockLabel("bb.ipv4")
                ipv4 = rx.read(IPv4Header_t, reliable=True).data
                res.proto = ipv4.protocol
                res.src = ipv4.src._zext(ipv6_t.bit_length())
                res.dst = ipv4.dst._zext(ipv6_t.bit_length())
            elif eth.type._eq(ETHER_TYPE.IPv6):
                PyBytecodeBlockLabel("bb.ipv6")
                res.isIPv6 = b1
                ipv6 = rx.read(IPv6Header_t, reliable=True).data
                res.proto = ipv6.nextHeader
                res.src = ipv6.src
                res.dst = ipv6.dst
                if ~In(res.proto, UDP_TCP):
                    PyBytecodeBlockLabel("bb.ipv6.ext0")
                    # :attention: this assumes headerExtensionLen=0
                    ext0 = rx.read(IPv6ExtCommonHeader_t, reliable=True).data
                    # [todo] headerExtensionLen, what sizes are actually supported in original paper?
                    res.proto = ext0.nextHeader
                    if ~In(res.proto, UDP_TCP):
                        PyBytecodeBlockLabel("bb.ipv6.ext1")
                        ext1 = rx.read(IPv6ExtCommonHeader_t, reliable=True).data
                        res.proto = ext1.nextHeader

            PyBytecodeBlockLabel("bb.beforeTcpUdp")
            if res.proto._eq(IP_PROTOCOL.TCP):
                PyBytecodeBlockLabel("bb.tcp")
                tcp = rx.read(TCP_header_t, reliable=True).data
                res.srcp = tcp.srcp
                res.dstp = tcp.dstp
            elif res.proto._eq(IP_PROTOCOL.UDP):
                PyBytecodeBlockLabel("bb.udp")
                udp = rx.read(UDP_header_t, reliable=True).data
                res.srcp = udp.srcp
                res.dstp = udp.dstp

            PyBytecodeBlockLabel("bb.out")
            # [todo] this expects input to be exactly just headers, if there is more data the FSM will break
            rx.readEndOfFrame()
            hls.write(res, self.tx, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        rx = IoProxyAxi4Stream(hls, self.rx)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, rx))
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS

    m = Axi4SParse5Tuple()
    m.CLK_FREQ = int(100e6)  # int(0.625e9)
    # m.DATA_WIDTH = 384
    # m.DATA_WIDTH = 112
    m.DATA_WIDTH = 128
    # p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)

    # versal https://static6.arrow.com/aropdfconversion/70a0cb7fa10106f8afcd000a0e321c8de2d89591/ds959-versal-premium.pdf
    p = HlsPlatformFromVitisDB("versal_fast", debugFilter=HlsDebugBundle.ALL_RELIABLE,
                               llvmCliArgs=[
                                   LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                                   # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,

                                ]
                               )
    print(to_rtl_str(m, target_platform=p))

