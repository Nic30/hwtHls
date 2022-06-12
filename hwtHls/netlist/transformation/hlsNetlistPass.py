

class HlsNetlistPass():

    def apply(self, hls: "HlsScope", to_hw: "SsaSegmentToHwPipeline"):
        raise NotImplementedError("Should be implemented in inheriting class", self)
