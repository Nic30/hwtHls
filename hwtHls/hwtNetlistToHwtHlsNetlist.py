from typing import Dict, Union, Optional, List

from hwt.code import If, CodeBlock, Switch
from hwt.hdl.operator import Operator
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.codeOps import AbstractHlsOp, HlsOperation, HlsMux, HlsConst, HlsIO, \
    HlsRead, HlsWrite
from hwt.hdl.statements.statement import HdlStatement
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED


def link_hls_nodes(parent: AbstractHlsOp, child: AbstractHlsOp) -> None:
    child.dependsOn.append(parent)
    parent.usedBy.append(child)


class HwtNetlistToHwtHlsNetlist():

    def __init__(self, hls: "Hls", to_hls: Dict[Union[RtlSignal, Operator], AbstractHlsOp]):
        self.hls = hls
        self._to_hls = to_hls

    def to_hls_operator(self, operator: Operator) -> HlsOperation:
        """
        Recursively convert operator and it's inputs to HLS representation

        :return: instance of HlsOperation representing of this operator
        """
        try:
            return self._to_hls[operator]
            # was already discovered
        except KeyError:
            pass

        # create HlsOperation node for this operator and register it
        op_node = HlsOperation(self.hls,
                               operator.operator,
                               operator.operands[0]._dtype.bit_length())
        self._to_hls[operator] = op_node

        # walk all inputs and connect them as my parent
        for op in operator.operands:
            op = self.to_hls_expr(op)
            if op is not None:
                link_hls_nodes(op, op_node)

        return op_node

    # def to_hls_mux(self, obj: RtlSignal) -> HlsMux:
    #    """
    #    Recursively convert signal which is output of multiplexer/demultiplexer
    #    to HLS nodes
    #    """
    #    try:
    #        return self._to_hls[obj]
    #        # was already discovered
    #    except KeyError:
    #        pass
    #
    #    if obj.hasGenericName:
    #        name = "mux_"
    #    else:
    #        name = obj.name
    #
    #    _obj = HlsMux(self.hls, obj._dtype.bit_length(), name=name)
    #    self._to_hls[obj] = _obj
    #
    #    # add condition to dependencies of this MUX operator
    #    c = self.to_hls_expr(obj.drivers[0].cond)
    #    link_nodes(c, _obj)
    #
    #    for a in obj.drivers:
    #        assert isinstance(a, HdlAssignmentContainer), a
    #        if a.indexes:
    #            raise NotImplementedError()
    #
    #        src = self.to_hls_expr(a.src)
    #        link_nodes(src, _obj)
    #
    #    return _obj
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

    def to_hls_driver_if(self, sig: RtlSignal,
                         obj: If,
                         default_driver: Optional[AbstractHlsOp]) -> HlsMux:
        mux = HlsMux(self.hls, sig._dtype.bit_length(), sig.name)
        if obj.parentStm is None:
            self._to_hls[sig] = mux

        for c, stms in obj._iter_all_elifs():
            _c = self.to_hls_expr(c)
            link_hls_nodes(_c, mux)
            v = self.to_hls_driver_block(sig, stms, default_driver)
            link_hls_nodes(v, mux)
            mux.elifs.append((_c, v))

        v = self.to_hls_driver_block(sig, obj.ifFalse, default_driver)
        link_hls_nodes(v, mux)
        mux.elifs.append((None, v))

        return mux

    def to_hls_driver_switch(self, sig: RtlSignal,
                         obj: Switch,
                         default_driver: Optional[AbstractHlsOp]) -> HlsMux:
        mux = HlsMux(self.hls, sig._dtype.bit_length(), sig.name)
        if obj.parentStm is None:
            self._to_hls[sig] = mux

        for c, stms in obj._iter_all_elifs():
            _c = self.to_hls_expr(c._eq(1))
            link_hls_nodes(_c, mux)
            v = self.to_hls_driver_block(sig, stms, default_driver)
            link_hls_nodes(v, mux)

        v = self.to_hls_driver_block(sig, obj.default, default_driver)
        link_hls_nodes(v, mux)
        return mux

    def to_hls_driver(self,
                      sig: RtlSignal,
                      obj: Union[HlsRead, HlsWrite, Operator, HdlAssignmentContainer, If, Switch, CodeBlock],
                      default_driver: Optional[AbstractHlsOp]) -> AbstractHlsOp:
        """
        :param default_driver: a value which should drive the sighal when the signal is not actively driven
        """
        try:
            return self._to_hls[obj]
        except KeyError:
            pass

        if isinstance(obj, HlsRead):
            self._to_hls[obj] = obj
            return obj

        elif isinstance(obj, HlsWrite):
            if obj.indexes:
                raise NotImplementedError()

            self._to_hls[obj] = obj

            src = self.to_hls_expr(obj.src)
            if obj.parentStm is None:
                link_hls_nodes(src, obj)
            else:

                # read/write is not just assigment which just marks some connection
                # instead it is operation which may take some time and require some synchronization
                # because of this we need to transfer all potentiall controll inputs to input of this operation
                top_sig_driver = self._to_hls[sig]
                link_hls_nodes(src, top_sig_driver)
                link_hls_nodes(top_sig_driver, obj)

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

    def to_hls_expr(self, obj: Union[RtlSignal, HValue]) -> AbstractHlsOp:
        """
        Convert RtlObject to HlsObject, register it and link it wit parent

        :note: parent is an object what provides values to operation
        """
        try:
            return self._to_hls[obj]
        except KeyError:
            pass

        if isinstance(obj, HValue) or obj._const:
            _obj = HlsConst(obj)
            self._to_hls[_obj] = _obj
            return _obj

        if not obj.drivers:
            assert isinstance(obj, HlsIO), obj
            return obj
        else:
            if len(obj.drivers) == 1:
                # parent is just RtlSignal, we needs operation
                # it is drivern from
                return self.to_hls_driver(
                    obj,
                    obj.drivers[0],
                    None if obj._nop_val is NOT_SPECIFIED else self.to_hls_expr(obj._nop_val))
            else:
                raise NotImplementedError(obj, "Multiple drivers")
                # [TODO] mux X indexed assignments
                # return mux2Hls(obj, hls, _to_hls)
