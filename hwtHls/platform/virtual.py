from hwtHls.scheduler.scheduler import HlsScheduler
from hwtHls.allocator.allocator import HlsAllocator
from hwt.hdl.operatorDefs import AllOps


class VirtualHlsPlatform():
    """
    Platform with informations about target platform
    and configuration of HLS

    :note: latencies like in average 28nm FPGA
    """
    OP_LATENCIES = {
        # operator: ns
        AllOps.ADD: 1.5e-9,
        AllOps.SUB: 0.2e-9,
        AllOps.UN_MINUS: 0.2e-9,

        AllOps.DIV: 0.2e-9,
        AllOps.POW: 0.2e-9,
        AllOps.MUL: 3.2e-9,
        AllOps.MOD: 0.2e-9,

        AllOps.NEG: 0.2e-9,
        AllOps.NOT: 0.2e-9,
        AllOps.XOR: 0.2e-9,
        AllOps.AND: 0.2e-9,
        AllOps.OR: 0.2e-9,

        AllOps.EQ:  0.1e-9,
        AllOps.NEQ: 0.1e-9,
        AllOps.GT: 0.2e-9,
        AllOps.GE: 0.2e-9,
        AllOps.LT: 0.2e-9,
        AllOps.LE: 0.2e-9,

        AllOps.TERNARY: 0.3e-9,
        AllOps.INDEX: 0,
    }

    def __init__(self):
        self.allocator = HlsAllocator
        self.scheduler = HlsScheduler

    def onHlsInit(self, hls):
        pass
