# https://stackoverflow.com/questions/46040382/spline-interpolation-in-3d-in-python
from itertools import islice
from pprint import pformat
from typing import Tuple

from hwtHls.scheduler.errors import TimeConstraintError
from scipy.interpolate._interpolate import interp1d


class Spline(interp1d):

    def __init__(self, x, y, kind='linear', axis=-1,
                 copy=False, bounds_error=False, fill_value="extrapolate",
                 assume_sorted=True):
        super(Spline, self).__init__(x, y, kind=kind, axis=axis, copy=copy, bounds_error=bounds_error, fill_value=fill_value, assume_sorted=assume_sorted)


class ResourceSplineBundle():

    def __init__(self, *spline_for_each_possible_latency: Optional[Spline]):
        assert spline_for_each_possible_latency
        self.splines = spline_for_each_possible_latency

    def __call__(self, arg_cnt:int, arg_bit_width:int, min_latency: int, max_val:float) -> Tuple[int, float]:
        latency = min_latency - 1
        for s in islice(self.splines, min_latency, None):
            latency += 1
            if s is None:
                continue
            v = s(arg_bit_width)
            if v <= max_val:
                return (latency, v)

        raise TimeConstraintError("No operation realizations satisfying the constrain", arg_cnt, arg_bit_width, min_latency, max_val)

    def __repr__(self):
        return f"{self.__class__.__name__:s}{pformat(tuple(self.splines))}"

