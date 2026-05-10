#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld, HwIOStructVld
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.types.net.ethernet import Eth2Header_t, eth_mac_t, Eth802_1qHeader_t, \
    ETHER_TYPE, EthType_t
from tests.io.amba.axi4Stream.axi4sVlan1qDecap_test import Axi4SVlan1qDecapUncond, \
    forwardUntilEoF
from hwtHls.frontend.pragmaFunction import PyBytecodeThreadExtractIoFsm
from hwtHls.frontend.pragmaLoop import PyBytecodeStreamSegmentLoopUnroll
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS


# Ethernet and alike processing architectures
# https://github.com/alexforencich/verilog-ethernet
# https://github.com/ryanjthomas/FPGA-Ethernet
# https://www.sciencedirect.com/science/article/abs/pii/S1084804520300382?via%3Dihub
# HyperParser: A High-Performance Parser Architecture for Next Generation Programmable Switch and SmartNIC (butterfly networks
# The Design of a Dynamic Configurable Packet Parser Based on FPGA https://www.mdpi.com/2072-666X/14/8/1560)
# PrismParser: A Framework for Implementing Efficient P4-Programmable Packet Parsers on FPGA https://www.mdpi.com/1999-5903/16/9/307
# Limago: an FPGA-based Open-source 100 GbE TCP/IP Stack https://www.davidsidler.com/files/fpl19-limago.pdf
# Low-latency modular packet header parser for FPGA https://asvk.cs.msu.ru/wp-content/uploads/2023/04/09-Low-Latency-Modular-Packet-Header-Parser-for-FPGA.pdf
# https://github.com/QUICKLY0000/FPGA-update-project/blob/main/axi_stream_insert_header
# https://github.com/wengwz/blue-ethernet
# P4-compatible High-level Synthesis of Low Latency 100 Gb/s Streaming Packet Parsers in FPGAs https://arxiv.org/pdf/1711.06613
# P4 to FPGA - A Fast Approach for Generating Efficient Network Processors https://www.researchgate.net/publication/338926337_P4_to_FPGA_-_A_Fast_Approach_for_Generating_Efficient_Network_Processors
# https://docs.amd.com/r/en-US/ug1308-vitis-p4-user-guide/Introduction
# https://www.xilinx.com/support/documents/sw_manuals/xilinx2017_1/UG1012-sdnet-packet-processor.pdf
# https://github.com/Lijinlin-dot/axi_stream_insert_header/blob/main/rtl/axi_stream_insert_header.v
# https://github.com/mbattyani/sub-25-ns-nasdaq-itch-fpga-parser
# FFShark: A 100G FPGA Implementation of BPF Filtering for Wireshark https://www.fccm.org/past/2020/proceedings/2020/pdfs/FCCM2020-65FOvhMqzyMYm99lfeVKyl/580300a047/580300a047.pdf
class Axi4SVlan1qEncapUncond(HwModule):
    """
    Insert 802.1Q vlan tag into Ethernet frame
    """
    # QinQ https://info.support.huawei.com/info-finder/encyclopedia/en/QinQ.html

    AXI_CLS = Axi4Stream

    @override
    def hwConfig(self) -> None:
        Axi4SVlan1qDecapUncond.hwConfig(self)

    @override
    def hwDeclr(self):
        Axi4SVlan1qDecapUncond.hwDeclr(self)
        self.vlan_tci: HwIOStructRdVld[eth_mac_t] = HwIOStructVld()
        self.vlan_tci.T = HBits(16)

    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        # to multi segmeneted IO
        while b1:
            rx.readStartOfFrame()
            eth = rx.read(Eth2Header_t, reliable=True).data
            eth_802_1q = Eth802_1qHeader_t.from_py(None)
            # copy all props from eth
            for field in Eth2Header_t.fields:
                setattr(eth_802_1q, field.name, getattr(eth, field.name))

            # set newly added fields
            eth_802_1q.tag.tpid = EthType_t.from_py(ETHER_TYPE.VLAN_1Q)
            eth_802_1q.tag.tci = hls.read(self.vlan_tci).data

            tx.writeStartOfFrame()
            tx.write(eth_802_1q)

            forwardUntilEoF(rx, tx)
            tx.writeEndOfFrame()

            rx.readEndOfFrame()
            PyBytecodeStreamSegmentLoopUnroll(rx)
            PyBytecodeThreadExtractIoFsm(tx) # separte rx/tx part for more simple scheduling and expansion

    @override
    def hwImpl(self) -> None:
        Axi4SVlan1qDecapUncond.hwImpl(self)


class Axi4SSVlan1qEncapUncond(Axi4SVlan1qEncapUncond):
    AXI_CLS = Axi4StreamSegmented


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = Axi4SVlan1qEncapUncond()
    m.CLK_FREQ = int(1e6)
    m.DATA_WIDTH = 512
    # m.PREFER_MULTI_THREAD = False
    # m.SEGMENT_DATA_WIDTH = 128
    # m.SEGMENT_CNT = 2
    # m.USE_SOF = True

    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                           llvmCliArgs=[LLVM_CLI_COMMON_OPTS.VERIFY_EACH, ])
    print(to_rtl_str(m, target_platform=p))
