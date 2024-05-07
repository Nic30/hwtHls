from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class RtlArchPass(HlsNetlistPass):
    """
    A base class for passes which are working on architectural level.
    Passes of this type are used late in translation process to optimize usually optimizes communication
    between ArchElement instances or elements them self.
    
    :note: RtlArchPass is HlsNetlistPass which works on netlist where nodes are scheduled and only ArchElement
    instances are at to top level.
    """
