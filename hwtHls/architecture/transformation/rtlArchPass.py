from hwtHls.architecture.allocator import HlsAllocator


class RtlArchPass():

    def apply(self, hls: "HlsScope", allocator: HlsAllocator):
        raise NotImplementedError("Should be implemented in child class", self)
