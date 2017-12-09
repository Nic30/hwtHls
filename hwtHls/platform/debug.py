from hwtHls.scheduler.scheduler import HlsScheduler
from hwtHls.allocator.allocator import HlsAllocator
from hwt.hdl.operatorDefs import AllOps


class DebugHlsPlatform():
    """
    Platform with informations about target platform
    and configuration of HLS
    """
    OP_LATENCIES = {
        # operator: s
        AllOps.ADD: 1.5,
        AllOps.SUB: 0.2,
        AllOps.UN_MINUS: 0.2,

        AllOps.DIV: 0.2,
        AllOps.POW: 0.2,
        AllOps.MUL: 3.2,
        AllOps.MOD: 0.2,

        AllOps.NOT: 0.2,
        AllOps.NEG: 0.2,
        AllOps.XOR: 0.2,
        AllOps.AND: 0.2,
        AllOps.OR: 0.2,

        AllOps.EQ:  0.1,
        AllOps.NEQ: 0.1,
        AllOps.GT: 0.2,
        AllOps.GE: 0.2,
        AllOps.LT: 0.2,
        AllOps.LE: 0.2,

        AllOps.TERNARY: 0.3,
        AllOps.INDEX: 0,
    }

    def __init__(self):
        self.allocator = HlsAllocator
        self.scheduler = HlsScheduler

    def onHlsInit(self, hls):
        pass
