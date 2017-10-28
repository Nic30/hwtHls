from hwtHls.scheduler.scheduler import HlsScheduler
from hwtHls.allocator.allocator import HlsAllocator


class VirtualHlsPlatform():
    """
    Platform with informations about target platform
    and configuration of HLS
    """

    def __init__(self):
        self.allocator = HlsAllocator
        self.scheduler = HlsScheduler

    def onHlsInit(self, hls):
        pass
