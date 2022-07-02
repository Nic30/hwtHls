from hwt.hdl.types.array import HArray
from hwt.synthesizer.interface import Interface
from hwtHls.frontend.ast.statementsRead import HlsReadAddressed
from hwtHls.frontend.ast.statementsWrite import HlsWriteAddressed


class AddressedIoProxy():
    """
    An base class for object which allow to use memory mapped interface as if it was an array.
    """
    READ_CLS = HlsReadAddressed
    WRITE_CLS = HlsWriteAddressed

    def __init__(self, hls: "HlsScope", interface: Interface, nativeType: HArray):
        self.hls = hls
        self.interface = interface
        self.nativeType = nativeType

#    def __getitem__(self, addr):
#        return self.hls.read(AddressedIoProxyRef(self, addr))
#  
#    def __setitem__(self, key, newvalue):
#        raise NotImplementedError()
#
#        
# class AddressedIoProxyRef():
#    """
#    Reference to some item behind the proxy
#    """
#
#    def __init__(self, proxy: AddressedIoProxy, index):
#        self.proxy = proxy
#        self.index = index
    
