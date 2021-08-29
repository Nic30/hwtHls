# https://stackoverflow.com/questions/46040382/spline-interpolation-in-3d-in-python
from itertools import islice
from pprint import pformat
from scipy.interpolate import UnivariateSpline
from typing import Tuple, Optional

from hwtHls.scheduler.errors import TimeConstraintError


class Spline(UnivariateSpline):

    def __init__(self, *args, **kwargs):
        if "k" not in kwargs:
            kwargs["k"] = 1
        super(Spline, self).__init__(*args, **kwargs)

    def __repr__(self):
        knots = tuple(self.get_knots())
        coefs = tuple(self.get_coeffs())
        return f"Spline(\n            {knots},\n            {coefs})"


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

        raise TimeConstraintError("No operation realizations statisfying the constrain", arg_cnt, arg_bit_width, min_latency, max_val)

    def __repr__(self):
        return f"{self.__class__.__name__:s}{pformat(tuple(self.splines))}"

