from hwtHls.architecture.allocator import HlsAllocator


class RtlArchPass():
    """
    A base class for passes which are working on architectural level.
    Passes of this type are used late in translation process to optimize usually optimizes communication between ArchElement instances or elements them self.
    """
    def apply(self, hls: "HlsScope", allocator: HlsAllocator):
        raise NotImplementedError("Should be implemented in child class", self)
