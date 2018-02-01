
from typing import Union

from hwt.code import If, And
from hwt.hdl.assignment import Assignment
from hwt.hdl.operator import Operator
from hwt.hdl.value import Value
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal


SigOrVal = Union[RtlSignal, Value]
AssigOrOp = Union[Assignment, Operator]


class RtlNetlistManipulator():
    def __init__(self, cntx: RtlNetlist):
        self.cntx = cntx

    def reconnectDriverOf(self, sig: SigOrVal,
                          driver: AssigOrOp,
                          replacement: SigOrVal):
        sig.drivers.remove(driver)

        if isinstance(driver, Operator):
            raise NotImplementedError()
        elif isinstance(driver, Assignment):
            raise NotImplementedError()
        else:
            raise TypeError(driver)

    def reconnectEndpointsOf(self, sig: RtlSignal,
                             replacement: SigOrVal):
        for endpoint in sig.endpoints:
            if isinstance(endpoint, Operator):
                raise NotImplementedError()
            elif isinstance(endpoint, Assignment):
                a = endpoint
                if a.src is sig:
                    if a.indexes:
                        raise NotImplementedError()
                    self.destroyAssignment(a)
                    # [TODO] if type matches reuse old assignment
                    if a.cond:
                        If(And(*a.cond),
                           a.dst(replacement)
                           )
                    else:
                        a.dst(replacement)
                else:
                    raise NotImplementedError()
            else:
                raise TypeError(endpoint)

    def destroyAssignment(self, a: Assignment, disconnectDst=True, disconnectSrc=True):
        if a.indexes:
            for i in a.indexes:
                if isinstance(i, RtlSignal):
                    i.endpoints.remove(a)

        for c in a.cond:
            if isinstance(c, RtlSignal):
                c.endpoints.remove(a)

        if disconnectSrc:
            a.src.endpoints.remove(a)
        if disconnectDst:
            a.dst.drivers.remove(a)
        self.cntx.startsOfDataPaths.remove(a)

    def disconnectDriverOf(self, sig: RtlSignal,
                           driver: AssigOrOp):

        if isinstance(driver, Operator):
            raise NotImplementedError()
        elif isinstance(driver, Assignment):
            if driver.dst is sig:
                self.destroyAssignment(driver)
            else:
                raise NotImplementedError()
        else:
            raise TypeError(driver)

    def disconnectEndpointOf(self, sig: RtlSignal,
                             endpoint: AssigOrOp):
        sig.endpoints.remove(endpoint)

        if isinstance(endpoint, Operator):
            raise NotImplementedError()
        elif isinstance(endpoint, Assignment):
            raise NotImplementedError()
        else:
            raise TypeError(endpoint)

