

class SsaPass():

    def apply(self, hls: "HlsScope", toSsa: "HlsAstToSsa"):
        raise NotImplementedError("Should be implemented in child class", self)
