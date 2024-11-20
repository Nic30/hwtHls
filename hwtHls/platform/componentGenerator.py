

class ComponentGenerator():

    def __init__(self, platform: "DefaultHlsPlatform"):
        self.platform = platform

    def resolveRealizationOfNode(self, node: "HlsNetNode") -> None:
        """
        Get OpRealizationMeta which is used during scheduling.
        """
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    def toRtlForNode(self, node: "HlsNetNode") -> None:
        """
        Translate from HlsNetNode to hwt RTL netlist.

        :attention: this function may mutate properties of node in order to inject generated RLT
        """
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)
        
