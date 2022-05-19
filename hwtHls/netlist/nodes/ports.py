from typing import List, Union
from hwt.hdl.types.hdlType import HdlType


def _reprMinify(o):
    try:
        return o.__repr__(minify=True)
    except:
        return o.__repr__()


class HlsNetNodeOut():
    """
    A class for object which do represents output of HlsNetNode instance.
    """

    def __init__(self, obj: "HlsNetNode", out_i: int, dtype: HdlType):
        self.obj = obj
        self.out_i = out_i
        self._dtype = dtype

    def __hash__(self):
        return hash((self.obj, self.out_i))

    def __eq__(self, other):
        return self is other or (self.__class__ is other.__class__ and self.obj == other.obj and self.out_i == other.out_i)

    def __repr__(self, minify=True):
        if minify:
            objStr = _reprMinify(self.obj)
        else:
            objStr = repr(self.obj)
        return f"<{self.__class__.__name__} {objStr:s} [{self.out_i:d}]>"


class HlsNetNodeIn():
    """
    A class for object which do represents input of HlsNetNode instance.
    """

    def __init__(self, obj: "HlsNetNode", in_i: int):
        self.obj = obj
        self.in_i = in_i

    def __hash__(self):
        return hash((self.obj, self.in_i))

    def __eq__(self, other):
        return self is other or (self.__class__ is other.__class__ and self.obj == other.obj and self.in_i == other.in_i)

    def replace_driver(self, o: HlsNetNodeOut):
        self.obj.dependsOn[self.in_i] = o
        if isinstance(o, HlsNetNodeOut):
            usedBy = o.obj.usedBy[o.out_i]
            i = self.obj._inputs[self.in_i]
            if i not in usedBy:
                usedBy.append(i)

    def __repr__(self, minify=False):
        if minify:
            objStr = _reprMinify(self.obj)
        else:
            objStr = repr(self.obj)
        return f"<{self.__class__.__name__} {objStr:s} [{self.in_i:d}]>"


class HlsNetNodeOutLazy():
    """
    A placeholder for future HlsNetNodeOut.

    :ivar dependent_inputs: information about children where new object should be replaced
    """

    def __init__(self, key_of_self_in_cache, op_cache:"SsaToHwtHlsNetlistOpCache", dtype: HdlType):
        self.dependent_inputs: List[HlsNetNodeIn, HlsNetNodeOutLazyIndirect] = []
        self.replaced_by = None
        self.keys_of_self_in_cache = [key_of_self_in_cache, ]
        self.op_cache = op_cache
        self._dtype = dtype

    def replace_driver(self, o:HlsNetNodeOut):
        assert self is not o, self
        assert self.replaced_by is None, (self, self.replaced_by)
        assert self._dtype == o._dtype,  (self, o, self._dtype, o._dtype)
        for k in self.keys_of_self_in_cache:
            self.op_cache._to_hls_cache[k] = o

        for c in self.dependent_inputs:
            c.replace_driver(o)

        self.replaced_by = o

    def __repr__(self):
        return f"<{self.__class__.__name__:s} 0x{id(self):x}>"


class HlsNetNodeOutLazyIndirect(HlsNetNodeOutLazy):
    """
    A placeholder for HlsNetNodeOut.
    Once this object is resolved and replaced the original HlsNetNodeOutLazy is replaced with a replacement.
    However the value defined in constructor is used as a final value left in op_cache.

    :note: This object is used if we want to replace some HlsNetNodeOutLazy (an output which does not exist yet).
    """

    def __init__(self,
                 op_cache:"SsaToHwtHlsNetlistOpCache",
                 original_lazy_out: HlsNetNodeOutLazy,
                 final_value: HlsNetNodeOut):
        assert original_lazy_out.replaced_by is None
        self.dependent_inputs: List[HlsNetNodeIn] = []
        self.replaced_by = None
        self.keys_of_self_in_cache = [*original_lazy_out.keys_of_self_in_cache, ]
        self.op_cache = op_cache
        self.original_lazy_out = original_lazy_out
        self.final_value = final_value
        assert self.original_lazy_out.replaced_by is None, (self, self.original_lazy_out.replaced_by)
        for k in self.original_lazy_out.keys_of_self_in_cache:
            self.op_cache._to_hls_cache[k] = self

    def replace_driver(self, obj:HlsNetNodeOut):
        """
        Replace the original_lazy_out with the obj and replace self with final_value.
        """
        assert self.replaced_by is None, (self, self.replaced_by)
        # replace original HlsNetNodeOutLazy to a resolved value
        self.original_lazy_out.replace_driver(obj)

        # replace self to a final value
        for k in self.keys_of_self_in_cache:
            self.op_cache._to_hls_cache[k] = self.final_value

        for c in self.dependent_inputs:
            c.replace_driver(self.final_value)

        self.replaced_by = self.final_value


def link_hls_nodes(parent: Union[HlsNetNodeOut, HlsNetNodeOutLazy], child: HlsNetNodeIn) -> None:
    assert isinstance(child, HlsNetNodeIn), child

    if isinstance(parent, HlsNetNodeOutLazy):
        parent.dependent_inputs.append(child)
    else:
        assert isinstance(parent, HlsNetNodeOut), parent
        parent.obj.usedBy[parent.out_i].append(child)

    child.obj.dependsOn[child.in_i] = parent
    if isinstance(parent, HlsNetNodeOut) and isinstance(child, HlsNetNodeOut):
        assert parent.obj is not child.obj

