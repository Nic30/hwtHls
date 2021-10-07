from typing import List, Union


class OperationIn():

    def __init__(self, obj: "AbstractHlsOp", in_i: int):
        self.obj = obj
        self.in_i = in_i

    def __hash__(self):
        return hash((self.obj, self.in_i))

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.obj == other.obj and self.in_i == other.in_i


class OperationOut():

    def __init__(self, obj: "AbstractHlsOp", out_i: int):
        self.obj = obj
        self.out_i = out_i

    def __hash__(self):
        return hash((self.obj, self.out_i))

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self.obj == other.obj and self.out_i == other.out_i


class OperationOutLazy():
    """
    A placeholder for future OperationOut.

    :ivar dependencies: information about children where new object should be replaced
    """

    def __init__(self):
        self.dependencies: List[OperationIn, HlsMuxElifRef] = []

    def register_mux_elif(self, mux: "HlsMux", elif_i:int):
        self.dependencies.append(HlsMuxElifRef(mux, elif_i, self))

    def replace(self, obj:OperationOut):
        for c in self.dependencies:
            if isinstance(c, OperationIn):
                c.obj.dependsOn[c.in_i] = obj
            else:
                c.replace(obj)


class HlsMuxElifRef():

    def __init__(self, mux: "HlsMux", elif_i: int, obj: OperationOutLazy):
        self.mux = mux
        self.elif_i = elif_i
        self.obj = obj

    def replace(self, new_obj: OperationOut):
        c, v = self.mux.elifs[self.elif_i]
        if c is self.obj:
            c = new_obj
        if v is self.obj:
            v = new_obj
        self.mux.elifs[self.elif_i] = (c, v)


def link_hls_nodes(parent: Union[OperationOut, OperationOutLazy], child: OperationIn) -> None:
    if isinstance(parent, OperationOutLazy):
        parent.dependencies.append(child)
    else:
        assert isinstance(parent, OperationOut), parent
        parent.obj.usedBy[parent.out_i].append(child)

    assert isinstance(child, OperationIn), child
    child.obj.dependsOn[child.in_i] = parent
