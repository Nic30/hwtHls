

class RtlArchPass():

    def apply(self, hls: "HlsScope", to_hw: "SsaSegmentToHwPipeline"):
        raise NotImplementedError("Should be implemented in child class", self)
