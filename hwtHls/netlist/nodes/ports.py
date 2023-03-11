from typing import List, Union, Optional

from hwt.hdl.types.hdlType import HdlType


def _reprMinify(o):
    # o.__repr__.__func__.__code__.co_varnames
    # o.__repr__.__func__.__code__.co_argcount
    try:
        return o.__repr__(minify=True)
    except:
        pass
    return o.__repr__()


class HlsNetNodeOut():
    """
    A class for object which represents output of :class:`HlsNetNode` instance.
    """

    def __init__(self, obj: "HlsNetNode", out_i: int, dtype: HdlType, name: Optional[str]):
        self.obj = obj
        self.out_i = out_i
        assert isinstance(dtype, HdlType), dtype
        self._dtype = dtype
        self.name = name
    
    def replaceDriverObj(self, o:"HlsNetNodeOut"):
        raise NotImplementedError()
        
    def __repr__(self, minify=True):
        if minify:
            objStr = _reprMinify(self.obj)
        else:
            objStr = repr(self.obj)
        if self.name is None:
            return f"<{self.__class__.__name__} {objStr:s} [{self.out_i:d}]>"
        else:
            return f"<{self.__class__.__name__} {objStr:s} [{self.out_i:d}-{self.name:s}]>"


class HlsNetNodeOutLazy():
    """
    A placeholder for future :class:`HlsNetNodeOut`.

    :ivar dependent_inputs: information about children where new object should be replaced
    """

    def __init__(self, netlist: "HlsNetlistCtx", keys_of_self_in_cache: list, op_cache:"SsaToHwtHlsNetlistOpCache", dtype: HdlType):
        self.netlist = netlist
        self._id = netlist.getUniqId()
        self.dependent_inputs: List[HlsNetNodeIn] = []
        self.replaced_by = None
        self.keys_of_self_in_cache = keys_of_self_in_cache
        self.op_cache = op_cache
        self._dtype = dtype

    def replaceDriverObj(self, o:HlsNetNodeOut):
        """
        Replace this output in all connected inputs.
        """
        assert self is not o, self
        assert self.replaced_by is None, (self, self.replaced_by)
        assert self._dtype == o._dtype or self._dtype.bit_length() == o._dtype.bit_length(), (self, o, self._dtype, o._dtype)
        for k in self.keys_of_self_in_cache:
            self.op_cache._toHlsCache[k] = o
        builder = self.netlist.builder
        l0 = len(self.dependent_inputs)
        for i in self.dependent_inputs:
            i: HlsNetNodeIn
            builder.unregisterNode(i.obj)
            i.replaceDriverInInputOnly(o)
            builder.registerNode(i.obj)
        
        assert len(self.dependent_inputs) == l0, "Must not modify dependent_inputs during replace"
        self.dependent_inputs.clear()
        
        self.replaced_by = o

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"


HlsNetNodeOutAny = Union[HlsNetNodeOut, HlsNetNodeOutLazy]


class HlsNetNodeIn():
    """
    A class for object which represents input of :class:`HlsNetNode` instance.
    """

    def __init__(self, obj: "HlsNetNode", in_i: int, name: Optional[str]):
        self.obj = obj
        self.in_i = in_i
        self.name = name

    def replaceDriver(self, o: HlsNetNodeOutAny) -> HlsNetNodeOutAny:
        """
        Disconnect old output object and connect new output object to this input while updating all.
        """
        oldO = self.obj.dependsOn[self.in_i]
        if oldO is None:
            pass
        elif isinstance(oldO, HlsNetNodeOut):
            oldO: HlsNetNodeOut
            oldO.obj.usedBy[oldO.out_i].remove(self)
        else:
            assert isinstance(oldO, HlsNetNodeOutLazy), oldO
            oldO: HlsNetNodeOutLazy
            oldO.dependent_inputs.remove(self)
        self.replaceDriverInInputOnly(o)
        return oldO

    def replaceDriverInInputOnly(self, o: HlsNetNodeOutAny) -> HlsNetNodeOutAny:
        """
        :attention: does not disconnect old output if there was any
        """
        oldO = self.obj.dependsOn[self.in_i]
        assert oldO is not o, ("If the replacement is the same, this fn. should not be called in the first place.", o)
        if isinstance(o, HlsNetNodeOut):
            usedBy = o.obj.usedBy[o.out_i]
            i = self.obj._inputs[self.in_i]
            if i not in usedBy:
                usedBy.append(i)
        else:
            assert isinstance(o, HlsNetNodeOutLazy), o
            o.dependent_inputs.append(self)
        self.obj.dependsOn[self.in_i] = o

        return oldO

    def __repr__(self, minify=False):
        if minify:
            objStr = _reprMinify(self.obj)
        else:
            objStr = repr(self.obj)
        if self.name is None:
            return f"<{self.__class__.__name__} {objStr:s} [{self.in_i:d}]>"
        else:
            return f"<{self.__class__.__name__} {objStr:s} [{self.in_i:d}-{self.name:s}]>"
            

def link_hls_nodes(parent: HlsNetNodeOutAny, child: HlsNetNodeIn) -> None:
    assert isinstance(child, HlsNetNodeIn), child

    if isinstance(parent, HlsNetNodeOutLazy):
        assert parent.replaced_by is None, (parent, parent.replaced_by, child)
        parent.dependent_inputs.append(child)
    else:
        assert isinstance(parent, HlsNetNodeOut), parent

        removed = parent.obj.netlist.builder._removedNodes
        assert parent.obj not in removed, parent
        assert child.obj not in removed, child
        parent.obj.usedBy[parent.out_i].append(child)

    assert child.obj.dependsOn[child.in_i] is None, ("child is already connected to " , child.obj.dependsOn[child.in_i], "when connecting" , parent, "->", child)
    child.obj.dependsOn[child.in_i] = parent
    if isinstance(parent, HlsNetNodeOut) and isinstance(child, HlsNetNodeOut):
        assert parent.obj is not child.obj


def unlink_hls_nodes(parent: HlsNetNodeOutAny, child: HlsNetNodeIn) -> None:
    assert isinstance(child, HlsNetNodeIn), child

    if isinstance(parent, HlsNetNodeOutLazy):
        parent.dependent_inputs.remove(child)
    else:
        assert isinstance(parent, HlsNetNodeOut), parent
        parent.obj.usedBy[parent.out_i].remove(child)

    child.obj.dependsOn[child.in_i] = None
    if isinstance(parent, HlsNetNodeOut) and isinstance(child, HlsNetNodeOut):
        assert parent.obj is not child.obj


def _getPortDrive(inPort: Optional[HlsNetNodeIn]):
    if inPort is None:
        return None
    else:
        return inPort.obj.dependsOn[inPort.in_i]


def unlink_hls_node_input_if_exists(input_: HlsNetNodeIn):
    dep = _getPortDrive(input_)
    if dep is not None:
        unlink_hls_nodes(dep, input_)
    return dep


def unlink_hls_node_input_if_exists_with_worklist(input_: HlsNetNodeIn, worklist: List["HlsNetNode"], removePort: bool):
    dep = unlink_hls_node_input_if_exists(input_)
    if dep is not None:
        worklist.append(dep.obj)
    if removePort and input_ is not None:
        input_.obj._removeInput(input_.in_i)

    return dep

