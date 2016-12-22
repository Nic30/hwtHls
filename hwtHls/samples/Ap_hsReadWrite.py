from hwt.interfaces.std import Handshaked
from hwt.synthesizer.interfaceLevel.unit import Unit
from hwtHls.baseSynthesizer import hls
from hwtHls.codeObjs import FsmNode
from hwt.synthesizer.shortcuts import toRtl


class HlsHs(Handshaked):
    def __init__(self, *args, **kwargs):
        super(HlsHs, self).__init__(*args, **kwargs)
        self._hlsNodes = []
        
    def read(self):
        rNode = FsmNode()
        rNode.lReady = self.rd
        rNode.lValid = self.vld
        rNode.ldata = self.data
        return rNode
        
    def write(self, fsmReadNode):
        assert fsmReadNode.rValid is None
        assert fsmReadNode.rReady is None
        
        fsmReadNode.rValid = self.vld
        fsmReadNode.rReady = self.rd
        fsmReadNode.rData = self.data
        self._hlsNodes.append(fsmReadNode)
        

class TestHlsUnit(Unit):
    a = HlsHs()
    b = HlsHs()
    
    @hls
    def readAndWrite(self):
        c = self.a.read()
        self.b.write(c) 
    


if __name__ == "__main__":
    u = TestHlsUnit()
    print(toRtl(u))

