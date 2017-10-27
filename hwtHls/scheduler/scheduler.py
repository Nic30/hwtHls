

class HlsScheduler():
    def __init__(self, parentHls):
        self.parentHls = parentHls

    def asap(self):
        """
        :return: maximum schedueled timme
        """
        # [TODO] fine grained latency

        maxTime = 0
        unresolved = []
        for node in self.parentHls.inputs:
            node.asap = 0
            unresolved.extend(node.usedBy)

        while unresolved:
            nextUnresolved = []
            for node in unresolved:
                try:
                    node_t = max(map(lambda n: n.asap, node.dependsOn))
                except AttributeError:
                    # skip this node because we will find it
                    # after its dependency will be completed
                    continue

                node.asap = node_t + 1
                nextUnresolved.extend(node.usedBy)
                maxTime = max(maxTime, node.asap)

            unresolved = nextUnresolved

        return maxTime

    def alap(self):
        """
        :return: maximum schedueled timme
        """
        # [TODO] fine grained latency
        t = 0
        unresolved = []
        for node in self.parentHls.outputs:
            # has no predecessors
            # [TODO] input read latency
            node.alap = t
            unresolved.extend(node.dependsOn)

        while unresolved:
            t -= 1
            nextUnresolved = []

            for o in unresolved:
                o.alap = t
                nextUnresolved.extend(o.dependsOn)

            unresolved = nextUnresolved

        timeOffset = -t
        for node in self.parentHls.nodes:
            node.alap += timeOffset

        return timeOffset

    def schedule(self):
        maxTime = self.asap()
        self.alap()

        schedulization = [[] for _ in range(maxTime + 1)]
        # [DEBUG] scheduele by asap only
        for node in self.parentHls.nodes:
            schedulization[node.asap].append(node)
            node.scheduledIn = node.asap

        self.schedulization = schedulization
