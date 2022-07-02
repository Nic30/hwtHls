

class SsaPass():

    def apply(self, hls: "HlsScope", to_ssa: "HlsAstToSsa"):
        raise NotImplementedError("Should be implemented in child class", self)
