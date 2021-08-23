
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


class QueryHdlAssignmentContainer():

    def __init__(self, dst: QuerySignal, src: QuerySignal):
        # self.indexes = None
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
            AllOps.RISING_EDGE, AllOps.FALLING_EDGE,
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

    def match_operator_drivers(self, op: Operator, qop: QueryOperator, res: dict) -> bool:
        if op.operator != qop.operator:
            return False
        # if not qop.op_order_depends:
        #    raise NotImplementedError()

        for oper, qoper in zip(op.operands, qop.operands):
            if not self.match_signal_drivers(oper, qoper, res):
                return False

        return True

    def match_signal_drivers(self, sig: RtlSignal, q: QuerySignal, res: Dict[str, RtlSignal]):
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

    def select(self, query: Callable[[], QuerySignal]):
        q = query()
        for sig in self.ctx.signals:
            res = {}
            if self.match_signal_drivers(sig, q, res):
                yield res
