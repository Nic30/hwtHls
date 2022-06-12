

class SsaPass():

    def apply(self, hls: "HlsStreamProc", to_ssa: "HlsAstToSsa"):
        raise NotImplementedError("Should be implemented in inheriting class", self)
