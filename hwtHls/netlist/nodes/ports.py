from typing import List, Union, Optional, Literal

from hwt.hdl.types.hdlType import HdlType
from hwt.constants import NOT_SPECIFIED


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
    __slots__ = ["obj", "out_i", "_dtype", "name"]

    def __init__(self, obj: "HlsNetNode", out_i: int, dtype: HdlType, name: Optional[str]):
        self.obj = obj
        self.out_i = out_i
        assert isinstance(dtype, HdlType), dtype
        self._dtype = dtype
        self.name = name

    def connectHlsIn(self, inPort: "HlsNetNodeIn", checkCycleFree=True, checkParent=True):
        assert isinstance(inPort, HlsNetNodeIn), inPort
        parentObj = self.obj
        assert not parentObj._isMarkedRemoved, self
        assert not inPort.obj._isMarkedRemoved, inPort
        if checkCycleFree:
            assert parentObj is not inPort.obj, ("Can not create cycle", self, inPort)
        if checkParent:
            assert parentObj.parent is inPort.obj.parent, ("same hierarchy level", self, inPort, parentObj.parent, inPort.obj.parent)

        removed = parentObj.getHlsNetlistBuilder()._removedNodes
        assert parentObj not in removed, self
        assert inPort.obj not in removed, inPort
        parentObj.usedBy[self.out_i].append(inPort)

        assert inPort.obj.dependsOn[inPort.in_i] is None, ("inPort is already connected to " , inPort.obj.dependsOn[inPort.in_i], "when connecting" , self, "->", inPort)
        inPort.obj.dependsOn[inPort.in_i] = self

    @classmethod
    def _reprMinified(cls, o:Union[None, "HlsNetNodeOut", "HlsNetNodeOutLazy"]) -> str:
        if o is None:
            return "None"
        elif isinstance(o, HlsNetNodeOut):
            return f"{o.obj._id:d}:{o.out_i:d}"
        else:
            return f'lazy:{o._id:d}'

    def getPrettyName(self, useParentName=True) -> str:
        obj = self.obj
        if useParentName and obj.name and self.name:
            return f"{obj.name:s}_{self.name:s}"
        elif useParentName and obj.name:
            if len(obj._outputs) == 1:
                return obj.name
            else:
                return f"{obj.name:s}_{self.out_i:d}"
        elif self.name:
            return f"n{obj._id:d}_{self.name:s}"
        else:
            if len(obj._outputs) == 1:
                return f"n{obj._id}"
            else:
                return f"n{obj._id:d}_{self.out_i:d}"

    def __repr__(self, minify=True) -> str:
        if minify:
            objStr = _reprMinify(self.obj)
        else:
            objStr = repr(self.obj)
        if self.name is None:
            return f"<{self.__class__.__name__:s} {objStr:s} [{self.out_i:d}]>"
        else:
            return f"<{self.__class__.__name__} {objStr:s} [{self.out_i:d}-{self.name:s}]>"


class HlsNetNodeOutLazy():
    """
    A placeholder for future :class:`HlsNetNodeOut`.

    :note: This is required because loop livein values on backedges can not exist when loop translation begins.

    :ivar dependent_inputs: information about children where new object should be replaced
    """

    def __init__(self, netlist: "HlsNetlistCtx", keys_of_self_in_cache: list, op_cache:"SsaToHwtHlsNetlistOpCache", dtype: HdlType, name:Optional[str]=None):
        self.netlist = netlist
        self._id = netlist.getUniqId()
        self.dependent_inputs: List[HlsNetNodeIn] = []
        self.replaced_by = None
        self.keys_of_self_in_cache = keys_of_self_in_cache
        self.op_cache = op_cache
        self._dtype = dtype
        self.name = name

    def connectHlsIn(self, inPort: "HlsNetNodeIn", checkCycleFree=True):
        assert isinstance(inPort, HlsNetNodeIn), inPort

        assert self.replaced_by is None, (self, self.replaced_by, inPort)
        self.dependent_inputs.append(inPort)

        assert inPort.obj.dependsOn[inPort.in_i] is None, ("inPort is already connected to " , inPort.obj.dependsOn[inPort.in_i], "when connecting" , self, "->", inPort)
        inPort.obj.dependsOn[inPort.in_i] = self

    def getLatestReplacement(self):
        if self.replaced_by is None:
            return self
        else:
            v = self.replaced_by
            while isinstance(v, HlsNetNodeOutLazy) and v.replaced_by:
                v = v.replaced_by
            return v

    def __repr__(self):
        if self.name:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.name:s}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d}>"


HlsNetNodeOutAny = Union[HlsNetNodeOut, HlsNetNodeOutLazy]


class HlsNetNodeIn():
    """
    A class for object which represents input of :class:`HlsNetNode` instance.
    """
    __slots__ = ["obj", "in_i", "name"]

    def __init__(self, obj: "HlsNetNode", in_i: int, name: Optional[str]):
        self.obj = obj
        self.in_i = in_i
        self.name = name

    def disconnectFromHlsOut(self, connectedOut: Union[HlsNetNodeOutAny, Literal[NOT_SPECIFIED]]=NOT_SPECIFIED) -> None:
        """
        :note: connectedOut is there as a performance optimization
        """
        if connectedOut is NOT_SPECIFIED:
            connectedOut = self.obj.dependsOn[self.in_i]

        if isinstance(connectedOut, HlsNetNodeOutLazy):
            connectedOut.dependent_inputs.remove(self)
        else:
            assert isinstance(connectedOut, HlsNetNodeOut), connectedOut
            connectedOut.obj.usedBy[connectedOut.out_i].remove(self)

        self.obj.dependsOn[self.in_i] = None

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

    def replaceDriverInInputOnly(self, o: HlsNetNodeOutAny, checkCycleFree:bool=True) -> HlsNetNodeOutAny:
        """
        :attention: does not disconnect old output if there was any
        """

        oldO = self.obj.dependsOn[self.in_i]
        assert oldO is not o, ("If the replacement is the same, this fn. should not be called in the first place.", o)
        if isinstance(o, HlsNetNodeOut):
            assert self.obj.parent is o.obj.parent, ("Ports must be on the same hierarchy level", self, o, self.obj.parent, o.obj.parent)
            assert not checkCycleFree or o.obj is not self.obj, ("Can not create cycle", o, self)
            usedBy = o.obj.usedBy[o.out_i]
            i = self.obj._inputs[self.in_i]
            if i not in usedBy:
                usedBy.append(i)
        else:
            assert isinstance(o, HlsNetNodeOutLazy), o
            o.dependent_inputs.append(self)
        self.obj.dependsOn[self.in_i] = o

        return oldO

    def getPrettyName(self, useParentName=True) -> str:
        obj = self.obj
        if useParentName and obj.name and self.name:
            return f"{obj.name:s}_{self.name:s}"
        elif useParentName and obj.name:
            if len(obj._inputs) == 1:
                return obj.name
            else:
                return f"{obj.name:s}_{self.in_i:d}"
        elif self.name:
            return f"{obj._id:d}_{self.name:s}"
        else:
            if len(obj._inputs) == 1:
                return str(obj._id)
            else:
                return f"{obj._id:d}_{self.in_i:d}"

    def __repr__(self, minify=False):
        if minify:
            objStr = _reprMinify(self.obj)
        else:
            objStr = repr(self.obj)
        if self.name is None:
            return f"<{self.__class__.__name__:s} {objStr:s} [{self.in_i:d}]>"
        else:
            return f"<{self.__class__.__name__:s} {objStr:s} [{self.in_i:d}-{self.name:s}]>"


def _getPortDrive(inPort: Optional[HlsNetNodeIn]):
    if inPort is None:
        return None
    else:
        return inPort.obj.dependsOn[inPort.in_i]


def unlink_hls_node_input_if_exists(input_: HlsNetNodeIn):
    dep = _getPortDrive(input_)
    if dep is not None:
        input_.disconnectFromHlsOut(dep)
    return dep


def unlink_hls_node_input_if_exists_with_worklist(input_: HlsNetNodeIn, worklist: List["HlsNetNode"], removePort: bool):
    dep = unlink_hls_node_input_if_exists(input_)
    if dep is not None:
        worklist.append(dep.obj)
    if removePort and input_ is not None:
        input_.obj._removeInput(input_.in_i)

    return dep

