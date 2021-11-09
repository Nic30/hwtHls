from itertools import chain
from typing import Dict, Union, Optional, List, Tuple

from hwt.code import If, CodeBlock, Switch
from hwt.hdl.operator import Operator
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.nodes.io import HlsRead, HlsWrite, HlsIO
from hwtHls.netlist.nodes.mux import HlsMux
from hwtHls.netlist.nodes.ops import AbstractHlsOp, HlsOperation, HlsConst
from hwtHls.netlist.nodes.ports import HlsOperationOut, link_hls_nodes


class HwtNetlistToHwtHlsNetlist():
    """
    Translate hwt netlict (RtlNetlist) to DAG of AbstractHlsOp nodes
    """

    def __init__(self, hls: "Hls", to_hls: Dict[Union[RtlSignal, Operator], Tuple[AbstractHlsOp, int]]):
        self.hls = hls
        self._to_hls = to_hls

    def to_hls_operator(self, operator: Operator) -> HlsOperation:
        """
        Recursively convert operator and it's inputs to HLS representation

        :return: instance of HlsOperation representing of this operator
        """
        try:
            return (self._to_hls[operator], 0)
            # was already discovered
        except KeyError:
            pass

        # create HlsOperation node for this operator and register it
        op_node = HlsOperation(self.hls,
                               operator.operator,
                               len(operator.operands),
                               operator.operands[0]._dtype.bit_length())
        self._to_hls[operator] = op_node

        # walk all inputs and connect them as my parent
        for i, op in enumerate(operator.operands):
            op = self.to_hls_expr(op)
            assert op is not None
            link_hls_nodes(op, op_node._inputs[i])

        return op_node._outputs[0]

    def to_hls_driver_block(self, sig: RtlSignal,
                            obj: Union[CodeBlock, List[HdlStatement], None],
                            default_driver: Optional[AbstractHlsOp]) -> AbstractHlsOp:
        if obj is not None:
            if isinstance(obj, CodeBlock):
                obj: CodeBlock
                obj = obj.statements
                if obj.parentStm is None:
                    raise NotImplementedError("We need to store something in _to_hls first")

            for stm in obj:
                stm: HdlStatement
                if sig in stm._outputs:
                    default_driver = self.to_hls_driver(sig, stm, default_driver)

        assert default_driver is not None, ("The signal ", sig, " has undriven branch and has no default value specified (result in undefined value without explicit notation)")
        return default_driver

    def to_hls_driver_mux_case(self, mux: HlsMux,
                               sig: RtlSignal,
                               cond:Optional[RtlSignal],
                               stms: List[HdlStatement],
                               default_driver):
        # :note: dependsOn slots must be spoted first before going deeper in statements
        #  because potential controll dependency must have slot available

        if cond is None:
            _c = None
        else:
            cond_i = mux._add_input()
            _c = self.to_hls_expr(cond)
            link_hls_nodes(_c, cond_i)

        val_i = mux._add_input()
        v = self.to_hls_driver_block(sig, stms, default_driver)
        link_hls_nodes(v, val_i)
        mux.elifs.append((_c, v))

    def to_hls_driver_if(self, sig: RtlSignal,
                         obj: If,
                         default_driver: Optional[AbstractHlsOp]) -> Tuple[HlsMux, int]:
        mux = HlsMux(self.hls, sig._dtype.bit_length(), sig.name)
        if obj.parentStm is None:
            self._to_hls[sig] = mux

        for c, stms in chain(obj._iter_all_elifs(), [(None, obj.ifFalse), ]):
            self.to_hls_driver_mux_case(mux, sig, c, stms, default_driver)

        return mux._outputs[0]

    def to_hls_driver_switch(self, sig: RtlSignal,
                         obj: Switch,
                         default_driver: Optional[AbstractHlsOp]) -> Tuple[HlsMux, int]:
        mux = HlsMux(self.hls, sig._dtype.bit_length(), sig.name)
        if obj.parentStm is None:
            self._to_hls[sig] = mux

        for c, stms in chain(obj._iter_all_elifs(), [(None, obj.default), ]):
            self.to_hls_driver_mux_case(mux, sig, c, stms, default_driver)

        return (mux, 0)

    def to_hls_driver(self,
                      sig: RtlSignal,
                      obj: Union[HlsRead, HlsWrite, Operator, HdlAssignmentContainer, If, Switch, CodeBlock],
                      default_driver: Optional[AbstractHlsOp]) -> HlsOperationOut:
        """
        :param default_driver: a value which should drive the sighal when the signal is not actively driven
        """
        try:
            return self._to_hls[obj]._outputs[0]
        except KeyError:
            pass

        if isinstance(obj, HlsRead):
            self._to_hls[obj] = obj
            return obj._outputs[0]

        elif isinstance(obj, HlsWrite):
            if obj.indexes:
                raise NotImplementedError()

            self._to_hls[obj] = obj

            src = self.to_hls_expr(obj.src)
            if obj.parentStm is None:
                link_hls_nodes(src, obj._inputs[0])
            else:
                # read/write is not just assigment which just marks some connection
                # instead it is operation which may take some time and require some synchronization
                # because of this we need to transfer all potentiall controll inputs to input of this operation
                top_sig_driver = self._to_hls[sig]
                link_hls_nodes(src, top_sig_driver._inputs[0])
                link_hls_nodes(top_sig_driver._outputs[0], obj._inputs[0])

            return src

        elif isinstance(obj, Operator):
            return self.to_hls_operator(obj)

        elif isinstance(obj, HdlAssignmentContainer):
            if obj.indexes:
                raise NotImplementedError()

            assert obj.dst is sig, (obj, sig)
            src = self.to_hls_expr(obj.src)
            # for _dst in sig.endpoints:
            #    if isinstance(dst)
            #    dst = self._to_hls[_dst]
            #    link_hls_nodes(src, dst)
            return src

        elif isinstance(obj, If):
            return self.to_hls_driver_if(sig, obj, default_driver)

        elif isinstance(obj, Switch):
            return self.to_hls_driver_switch(sig, obj, default_driver)

        elif isinstance(obj, CodeBlock):
            return self.to_hls_driver_block(sig, obj, default_driver)

        else:
            raise NotImplementedError(obj)

    def to_hls_expr(self, obj: Union[RtlSignal, HValue]) -> HlsOperationOut:
        """
        Convert RtlObject to HlsObject, register it and link it wit parent

        :note: parent is an object what provides values to operation
        """
        try:
            return self._to_hls[obj]._outputs[0]
        except KeyError:
            pass

        if isinstance(obj, HValue) or obj._const:
            _obj = HlsConst(obj)
            self._to_hls[_obj] = _obj
            return _obj._outputs[0]

        if not obj.drivers:
            assert isinstance(obj, HlsIO), obj
            return obj._outputs[0]
        else:
            if len(obj.drivers) == 1:
                # parent is just RtlSignal, we needs operation it is driven from
                return self.to_hls_driver(
                    obj,
                    obj.drivers[0],
                    None if obj._nop_val is NOT_SPECIFIED else self.to_hls_expr(obj._nop_val))
            else:
                # [TODO] multi port memories
                raise NotImplementedError(obj, "Multiple drivers")
