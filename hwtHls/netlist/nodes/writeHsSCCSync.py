from typing import Optional

from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class HlsNetNodeWriteHsSccSync(HlsNetNodeWrite):
    """
    Specialized version of write used to implement sync for Handshake SCCs
    :note: originally meant for better netlist readability and visualization
    """

    def __init__(self, netlist:"HlsNetlistCtx", hsSccIndex: int, name:Optional[str]=None):
        HlsNetNodeWrite.__init__(self, netlist, None, name=name)
        self.hsSccIndex = hsSccIndex
