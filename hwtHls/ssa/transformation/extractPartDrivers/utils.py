from typing import Tuple, List

from hwtHls.ssa.value import SsaValue


class VarBitSegmentDriverInfo():
    """
    :ivar range_to_self, range_from_src: in the format of high,low
    """
    __slots__ = ["src_var", "ranges_to_self", "range_from_src"]

    def __init__(self, src_var: SsaValue, range_to_self: Tuple[int, int], range_from_src: Tuple[int, int]):

        self.src_var = src_var
        self.ranges_to_self = range_to_self
        self.range_from_src = range_from_src

    def __repr__(self):
        return (
            f"<{self.__class__.__name__:s} [{self.ranges_to_self[0]}:{self.ranges_to_self[1]}] ="
            f" {self.src_var}[{self.range_from_src[0]}:{self.range_from_src[1]}]>"
        )


class VarBitSegmentEndpointInfo():
    """
    :ivar range_to_self, range_from_src: in the format of high,low
    """
    __slots__ = ["dst_var", "range_from_self", "range_to_dst"]

    def __init__(self, dst_var: SsaValue, range_in_self: Tuple[int, int], range_to_dst: Tuple[int, int]):
        self.dst_var = dst_var
        self.range_from_self = range_in_self
        self.range_to_dst = range_to_dst

    def __repr__(self):
        return (
            f"<{self.__class__.__name__:s} {self.dst_var}[{self.range_to_dst[0]}:{self.range_to_dst[1]}] ="
            f" [{self.range_from_self[0]}:{self.range_from_self[1]}]>"
        )


class VarBitSegments():
    __slots__ = ["var", "driver_ranges", "endpoint_ranges"]

    def __init__(self, var: SsaValue):
        self.var = var
        self.driver_ranges: List[VarBitSegmentDriverInfo] = []
        self.endpoint_ranges: List[VarBitSegmentEndpointInfo] = []
