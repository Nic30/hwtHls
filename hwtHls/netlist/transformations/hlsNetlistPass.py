

class HlsNetlistPass():

    def apply(self, hls: "HlsStreamProc", to_hw: "SsaSegmentToHwPipeline"):
        raise NotImplementedError("Should be implemented in inheriting class", self)
