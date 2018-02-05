
from typing import Union, Tuple, Dict, List, Set

from hwt.hdl.assignment import Assignment
from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.value import Value
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.uniqList import UniqList
from hwt.synthesizer.unit import Unit
from hwtHls.codeOps import HlsIO


SigOrVal = Union[RtlSignal, Value]
AssigOrOp = Union[Assignment, Operator]


class SubgraphDestroyCntx():
    def __init__(self, endpoint_destroy_set, driver_destroy_set,
                 inBoudaries, outBoundaries):
        """
        :param endpoint_destroy_set: set of RtlSignals to recursively
            destroy in endpoint direction (inputs)
        :param driver_destroy_set: set of RtlSignals to recursively
            destroy in driver direction (outputs)
        """
        self.endpoint_destroy_set = endpoint_destroy_set
        self.driver_destroy_set = driver_destroy_set
        self.inBoudaries = inBoudaries
        self.outBoundaries = outBoundaries
        self.destroyed = set()


class RtlNetlistManipulator():
    def __init__(self, cntx: RtlNetlist, io: Dict[HlsIO, Interface]={}):
        self.cntx = cntx
        self.io = io

    def destroy_subgraph(self, inSignals: List[RtlSignal], outSignals: [RtlSignal]):
        """
        :attention: boundary signals are not destroyed
        :attention: all boundaries has to be specified otherwise parent graph will be damaged
        """
        outSignals = set(outSignals)
        inSignals = set(inSignals)
        d_cntx = SubgraphDestroyCntx(
            inSignals.copy(), outSignals.copy(),
            outSignals, inSignals)
        drvs = d_cntx.driver_destroy_set
        eps = d_cntx.endpoint_destroy_set
        while drvs or eps:
            print("drvs", drvs)
            print("eps", eps)
            if drvs:
                self.recursive_destroy_drivers(d_cntx)
            if eps:
                self.recursive_destroy_endpoints(d_cntx)

    def recursive_destroy_drivers(self, cntx: SubgraphDestroyCntx):
        """
        Recursively disconect signals and it's drivers
        """
        destroyed = cntx.destroyed
        open_set = cntx.driver_destroy_set

        while open_set:
            sig = open_set.pop()
            destroyed.add(sig)
            drvs = sig.drivers
            while drvs:
                driver = drvs.pop()
                self.destroy_driver(driver, cntx)

    def recursive_destroy_endpoints(self, cntx: SubgraphDestroyCntx):
        """
        Recursively disconect signals and it's endpoints
        """
        destroyed = cntx.destroyed
        open_set = cntx.endpoint_destroy_set

        while open_set:
            sig = open_set.pop()
            destroyed.add(sig)
            eps = sig.endpoints
            while eps:
                endpoint = eps.pop()
                self.destroy_endpoint(endpoint, cntx)

    def destroy_driver(self, driver: Union[Operator, Assignment], cntx: SubgraphDestroyCntx):
        """
        :return: list of input signals to this driver
        """
        boundaries = cntx.inBoudaries
        destroyed = cntx.destroyed
        to_destroy = cntx.driver_destroy_set

        if isinstance(driver, Assignment):
            # comming from dst
            self.cntx.startsOfDataPaths.remove(driver)
            if driver.indexes:
                for i in driver.indexes:
                    if isinstance(i, RtlSignal):
                        if i not in boundaries and i not in destroyed:
                            to_destroy.add(i)

                driver.indexes = None
                for c in driver.cond:
                    if isinstance(c, RtlSignal) and \
                            c not in boundaries and \
                            c not in destroyed:
                        to_destroy.add(c)
                driver.cond.clear()

                src = driver.src
                if isinstance(src, RtlSignal) and \
                        src not in boundaries and \
                        src not in destroyed:
                    to_destroy.append(src)
                driver.src = None
                driver.dst = None

        elif isinstance(driver, Operator):
            # comming from result
            to_destroy = cntx.driver_destroy_set
            for op in driver.operands:
                if isinstance(op, RtlSignal):
                    if op not in boundaries and op not in destroyed:
                        to_destroy.add(op)
                        print(op, driver)
                        try:
                            op.endpoints.remove(driver)
                        except KeyError:
                            pass

            driver.operands = []
        else:
            raise TypeError(driver)

    def destroy_endpoint(self, endpoint: Union[Operator, Assignment],
                         boundaries: Set[RtlSignal],
                         destroyed: Set[Union[RtlSignal, Operator, Assignment]]):
        """
        :return: outputs from this endpoint
        """
        if isinstance(endpoint, Assignment):
            if endpoint.indexes:
                for i in endpoint.indexes:
                    if isinstance(i, RtlSignal):
                        self.recursive_destroy_drivers(
                            i, boundaries, destroyed)

                endpoint.indexes = None
                for c in endpoint.cond:
                    if isinstance(c, RtlSignal):
                        self.recursive_destroy_drivers(
                            c, boundaries, destroyed)
                endpoint.cond.clear()

                inputs.append(endpoint.dst)
                endpoint.src = None
                endpoint.dst = None
        elif isinstance(endpoint, Operator):
            raise NotImplementedError()
        else:
            raise TypeError(endpoint)

    def reconnect_subgraph(self, inSignals: Dict[RtlSignal, RtlSignal],
                           outSignals: Dict[RtlSignal, RtlSignal]):

        for sig, replacement in inSignals.items():
            if sig is not replacement:
                self.reconnect_drivers_of(sig, replacement)

        for sig, replacement in outSignals.items():
            if sig is not replacement:
                self.reconnect_endpoints_of(sig, replacement)

        #self.destroy_subgraph(inSignals.keys(), outSignals.keys())

    def reconnect_drivers_of(self, sig: SigOrVal,
                             replacement: SigOrVal):
        if sig in self.io:
            assert not sig.drivers
            # can not directly replace signal because it is IO to utside graph
            # for ep in sig.endpoints:
            #    self.destroy_endpoint(ep)
            sig.endpoints.clear()
            sig(replacement)
        else:
            for driver in sig.drivers:
                self.reconnect_driver_of(sig, driver, replacement)

    def reconnect_driver_of(self, sig: SigOrVal,
                            driver: AssigOrOp,
                            replacement: SigOrVal):
        if isinstance(driver, Operator):
            raise NotImplementedError()
        elif isinstance(driver, Assignment):
            driver.dst = replacement
        else:
            raise TypeError(driver)

        sig.drivers.remove(driver)
        replacement.drivers.append(driver)

    def reconnect_endpoints_of(self, sig: RtlSignal,
                               replacement: SigOrVal):
        for endpoint in sig.endpoints:
            if isinstance(endpoint, Operator):
                raise NotImplementedError()
            elif isinstance(endpoint, Assignment):
                a = endpoint
                if a.src is sig:
                    if a.indexes:
                        raise NotImplementedError()

                    if a.src._dtype == replacement._dtype:
                        a.src = replacement
                        a.src.endpoints.append(a)
                        sig.endpoints.remove(a)
                    else:
                        # type has to be exactly the same
                        raise TypeError(a.src._dtype, replacement._dtype)
                        # self.destroyAssignment(a)
                        # if a.cond:
                        #    If(And(*a.cond),
                        #       a.dst(replacement)
                        #       )
                        # else:
                        #    a.dst(replacement)
                else:
                    raise NotImplementedError()
            else:
                raise TypeError(endpoint)

    def destroy_assignment(self, a: Assignment):
        if a.indexes:
            for i in a.indexes:
                if isinstance(i, RtlSignal):
                    i.endpoints.remove(a)

        for c in a.cond:
            if isinstance(c, RtlSignal):
                c.endpoints.remove(a)

        a.src.endpoints.remove(a)
        a.dst.drivers.remove(a)
        self.cntx.startsOfDataPaths.remove(a)

    def disconnect_driver_of(self, sig: RtlSignal,
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

    def disconnect_endpoint_of(self, sig: RtlSignal,
                               endpoint: AssigOrOp):
        sig.endpoints.remove(endpoint)

        if isinstance(endpoint, Operator):
            raise NotImplementedError()
        elif isinstance(endpoint, Assignment):
            raise NotImplementedError()
        else:
            raise TypeError(endpoint)


class QuerySignal():
    def __init__(self, label: str=None):
        self.label = label
        self.drivers = UniqList()
        self.endpoints = UniqList()
        self._usedOps = {}

    def setLabel(self, label: str):
        self.label = label

    def naryOp(self, operator, *otherOps):
        """
        Try lookup operator with this parameters in _usedOps
        if not found create new one and soter it in _usedOps
        """
        k = (operator, otherOps)
        try:
            return self._usedOps[k]
        except KeyError:
            pass

        o = QueryOperator.signalWrapped(operator, (self, *otherOps))
        self._usedOps[k] = o
        return o

    def __add__(self, other):
        return self.naryOp(AllOps.ADD, other)

    def __mul__(self, other):
        return self.naryOp(AllOps.MUL, other)

    def __call__(self, other):
        raise NotImplementedError()

    def __repr__(self):
        if self.label:
            return self.label
        else:
            return object.__repr__(self)


class QueryAssignment():
    def __init__(self, dst, src):
        #self.cond = UniqList()
        #self.indexes = None
        self.dst = dst
        self.src = src


class QueryOperator():
    def __init__(self, operator: OpDefinition, operands: Tuple[QuerySignal]):
        self.operator = operator
        self.operands = operands
        self.op_order_depends = operator in {
            AllOps.CONCAT, AllOps.DIV, AllOps.DOT,
            AllOps.DOWNTO, AllOps.LE, AllOps.LT,
            AllOps.GE, AllOps.GT, AllOps.MOD, AllOps.POW,
            AllOps.RISING_EDGE, AllOps.FALLIGN_EDGE,
            AllOps.SUB, AllOps.TERNARY, AllOps.TO
        }

    @staticmethod
    def signalWrapped(opertor: OpDefinition, ops: Tuple[QuerySignal]):
        s = QuerySignal()
        o = QueryOperator(opertor, ops)
        s.drivers.append(o)
        return s


class HwSelect():
    def __init__(self, ctx: Unit):
        self.ctx = ctx

    def match_operator_drivers(self, op: Operator, qop: QueryOperator, res: dict):
        if op.operator != qop.operator:
            return False
        # if not qop.op_order_depends:
        #    raise NotImplementedError()

        for oper, qoper in zip(op.operands, qop.operands):
            if not self.match_signal_drivers(oper, qoper, res):
                return False

        return True

    def match_signal_drivers(self, sig: RtlSignal, q: QuerySignal, res: dict):
        if not q.drivers:
            if q.label:
                res[q.label] = sig
            return True

        if len(sig.drivers) == len(q.drivers):
            if len(sig.drivers) != 1:
                # [TODO] need to check all combinations of driver oders
                raise NotImplementedError()

            for d, dq in zip(sig.drivers, q.drivers):
                if isinstance(dq, QueryOperator):
                    if isinstance(d, Operator) and self.match_operator_drivers(d, dq, res):
                        continue
                    else:
                        return False
                else:
                    raise NotImplementedError()

            if q.label:
                res[q.label] = sig
            return True

    def select(self, query):
        q = query()
        for sig in self.ctx.signals:
            res = {}
            if self.match_signal_drivers(sig, q, res):
                yield res
