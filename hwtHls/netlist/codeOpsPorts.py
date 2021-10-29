from typing import List, Union


class HlsOperationIn():

    def __init__(self, obj: "AbstractHlsOp", in_i: int):
        self.obj = obj
        self.in_i = in_i

    def __hash__(self):
        return hash((self.obj, self.in_i))

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.obj == other.obj and self.in_i == other.in_i


class HlsOperationOut():

    def __init__(self, obj: "AbstractHlsOp", out_i: int):
        self.obj = obj
        self.out_i = out_i

    def __hash__(self):
        return hash((self.obj, self.out_i))

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.obj == other.obj and self.out_i == other.out_i

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.obj} [{self.out_i:d}]>"


class HlsOperationOutLazy():
    """
    A placeholder for future HlsOperationOut.

    :ivar dependencies: information about children where new object should be replaced
    """

    def __init__(self, key_of_self_in_cache, op_cache:dict):
        self.dependencies: List[HlsOperationIn, HlsMuxElifRef] = []
        self.replaced_by = None
        self.keys_of_self_in_cache = [key_of_self_in_cache, ]
        self.op_cache = op_cache

    def register_mux_elif(self, mux: "HlsMux", elif_i:int):
        self.dependencies.append(HlsMuxElifRef(mux, elif_i, self))

    def replace(self, obj:HlsOperationOut):
        assert self.replaced_by is None, (self, self.replaced_by)
        for k in self.keys_of_self_in_cache:
            self.op_cache[k] = obj

        for c in self.dependencies:
            if isinstance(c, HlsOperationIn):
                c.obj.dependsOn[c.in_i] = obj
            else:
                c.replace(obj)

        self.replaced_by = obj


class HlsMuxElifRef():

    def __init__(self, mux: "HlsMux", elif_i: int, obj: HlsOperationOutLazy):
        self.mux = mux
        self.elif_i = elif_i
        self.obj = obj

    def replace(self, new_obj: HlsOperationOut):
        c, v = self.mux.elifs[self.elif_i]
        if c is self.obj:
            c = new_obj
        if v is self.obj:
            v = new_obj
        self.mux.elifs[self.elif_i] = (c, v)


def link_hls_nodes(parent: Union[HlsOperationOut, HlsOperationOutLazy], child: HlsOperationIn) -> None:
    if isinstance(parent, HlsOperationOutLazy):
        parent.dependencies.append(child)
    else:
        assert isinstance(parent, HlsOperationOut), parent
        parent.obj.usedBy[parent.out_i].append(child)

    assert isinstance(child, HlsOperationIn), child
    child.obj.dependsOn[child.in_i] = parent
    if isinstance(parent, HlsOperationOut) and isinstance(child, HlsOperationOut):
        assert parent.obj is not child.obj
