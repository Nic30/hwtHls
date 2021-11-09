from typing import List, Union


class HlsOperationOut():

    def __init__(self, obj: "AbstractHlsOp", out_i: int):
        self.obj = obj
        self.out_i = out_i

    def __hash__(self):
        return hash((self.obj, self.out_i))

    def __eq__(self, other):
        return self is other or (self.__class__ is other.__class__ and self.obj == other.obj and self.out_i == other.out_i)

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.obj} [{self.out_i:d}]>"


class HlsOperationIn():

    def __init__(self, obj: "AbstractHlsOp", in_i: int):
        self.obj = obj
        self.in_i = in_i

    def __hash__(self):
        return hash((self.obj, self.in_i))

    def __eq__(self, other):
        return self is other or (self.__class__ is other.__class__ and self.obj == other.obj and self.in_i == other.in_i)

    def replace_driver(self, obj: HlsOperationOut):
        self.obj.dependsOn[self.in_i] = obj


class HlsOperationOutLazy():
    """
    A placeholder for future HlsOperationOut.

    :ivar dependent_inputs: information about children where new object should be replaced
    """

    def __init__(self, key_of_self_in_cache, op_cache:"SsaToHwtHlsNetlistOpCache"):
        self.dependent_inputs: List[HlsOperationIn, HlsOperationOutLazyIndirect] = []
        self.replaced_by = None
        self.keys_of_self_in_cache = [key_of_self_in_cache, ]
        self.op_cache = op_cache

    def replace_driver(self, obj:HlsOperationOut):
        assert self is not obj, self
        assert self.replaced_by is None, (self, self.replaced_by)
        for k in self.keys_of_self_in_cache:
            self.op_cache._to_hls_cache[k] = obj

        for c in self.dependent_inputs:
            c.replace_driver(obj)

        self.replaced_by = obj

    def __repr__(self):
        return f"<{self.__class__.__name__:s} 0x{id(self):x}>"


class HlsOperationOutLazyIndirect(HlsOperationOutLazy):
    """
    A placeholder for HlsOperationOut.
    Once this object is resolved and replaced the original HlsOperationOutLazy is replaced with a replacement.
    However the value defined in constructor is used as a final value left in op_cache.

    :note: This object is used if we want to replace some HlsOperationOutLazy (an output which does not exist yet).
    """

    def __init__(self,
                 op_cache:"SsaToHwtHlsNetlistOpCache",
                 original_lazy_out: HlsOperationOutLazy,
                 final_value: HlsOperationOut):
        assert original_lazy_out.replaced_by is None
        self.dependent_inputs: List[HlsOperationIn] = []
        self.replaced_by = None
        self.keys_of_self_in_cache = [*original_lazy_out.keys_of_self_in_cache, ]
        self.op_cache = op_cache
        self.original_lazy_out = original_lazy_out
        self.final_value = final_value
        assert self.original_lazy_out.replaced_by is None, (self, self.original_lazy_out.replaced_by)
        for k in self.original_lazy_out.keys_of_self_in_cache:
            self.op_cache._to_hls_cache[k] = self

    def replace_driver(self, obj:HlsOperationOut):
        """
        Replace the original_lazy_out with the obj and replace self with final_value.
        """
        assert self.replaced_by is None, (self, self.replaced_by)
        # replace original HlsOperationOutLazy to a resolved value
        self.original_lazy_out.replace_driver(obj)

        # replace self to a final value
        for k in self.keys_of_self_in_cache:
            self.op_cache._to_hls_cache[k] = self.final_value

        for c in self.dependent_inputs:
            c.replace_driver(self.final_value)

        self.replaced_by = self.final_value


def link_hls_nodes(parent: Union[HlsOperationOut, HlsOperationOutLazy], child: HlsOperationIn) -> None:
    assert isinstance(child, HlsOperationIn), child

    if isinstance(parent, HlsOperationOutLazy):
        parent.dependent_inputs.append(child)
    else:
        assert isinstance(parent, HlsOperationOut), parent
        parent.obj.usedBy[parent.out_i].append(child)

    child.obj.dependsOn[child.in_i] = parent
    if isinstance(parent, HlsOperationOut) and isinstance(child, HlsOperationOut):
        assert parent.obj is not child.obj
