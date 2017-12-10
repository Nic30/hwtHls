from math import ceil

from hwt.hdl.operator import isConst
from hwtHls.codeOps import HlsConst
from hwtHls.hls import Hls
from hwtHls.clk_math import start_clk, end_clk


class UnresolvedChild(Exception):
    """
    Exception raised when children should be lazyloaded first
    """
    pass


class TimeConstraintError(Exception):
    """
    Exception raised when it is not possble to satisfy timing constraints
    """
    pass


def child_asap_time(ch):
    if ch.asap_end is None:
        if isinstance(ch, HlsConst):
            return 0
        else:
            raise UnresolvedChild()
    else:
        return ch.asap_end


def parent_alap_time(ch):
    if ch.alap_start is None:
        if isinstance(ch, HlsConst):
            return 0
        else:
            raise UnresolvedChild()
    else:
        return ch.alap_start


class HlsScheduler():
    def __init__(self, parentHls: Hls):
        self.parentHls = parentHls

    def asap(self):
        """
        As Soon As Possible scheduler

        :return: maximum schedueled timme, decorate nodes
            with asap_start,end time
        """
        # [TODO] pre-post latencies
        # [TODO] cycle delays/latencies

        maxTime = 0
        unresolved = set()
        clk_period = self.parentHls.clk_period
        # init start times
        for node in self.parentHls.inputs:
            node.asap_start = node.asap_end = 0
            unresolved.update(
                [n for n in node.usedBy if not n.fixed_schedulation])

        # walk from inputs to outputs and decorate nodes with time
        while unresolved:
            nextUnresolved = set()
            for node in unresolved:
                try:
                    node_t = max(map(child_asap_time, node.dependsOn))
                except UnresolvedChild:
                    # skip this node because we will find it
                    # after its dependency will be completed
                    # (unresolved children will be resolved and it will
                    # run resolution for this node again)
                    continue
                else:
                    # Remaining time until clock tick
                    remaining_time = clk_period - (node_t % clk_period)
                    if node.latency_pre > remaining_time:
                        # Operation would exceed clock cycle -> align to clock
                        # rising edge
                        node_t += remaining_time
                        if node.latency_pre + node.latency_post >= clk_period:
                            raise TimeConstraintError(
                                "Impossible scheduling, clk_period too low for ",
                                node.latency_pre, node.latency_post, node)

                node.asap_start = node_t
                node.asap_end = node_t + node.latency_pre

                nextUnresolved.update(
                    [n for n in node.usedBy if not n.fixed_schedulation])

                for prev in node.dependsOn:
                    if prev.asap_end is None and isinstance(prev, HlsConst):
                        prev.asap_start = prev.asap_end = node.asap_start

                maxTime = max(maxTime, node.asap_end)

            unresolved = nextUnresolved

        # some of nodes does not have to be discovered because
        # they have no connection
        for node in self.parentHls.outputs:
            if node.asap_start is None:
                assert isConst(node.what), node
                node.asap_start = 0
                node.asap_end = 0
                node.what.asap_start = 0
                node.what.asap_end = 0

        return maxTime

    def alap(self, minimum_latency):
        """
        As Late As Possible scheduler + remove nodes which are not effecting
        any output

        :param minimum_latency: Minimum hls latency returned by ASAP
        """
        # [TODO] pre-post latencies
        # [TODO] cycle delays/latencies
        unresolved = set()

        for node in self.parentHls.outputs:
            # has no predecessors
            # [TODO] input read latency
            node.alap_end = minimum_latency
            node.alap_start = node.alap_end - node.latency_pre
            unresolved.update(
                [n for n in node.dependsOn if not n.fixed_schedulation])

        clk_period = self.parentHls.clk_period
        # walk from outputs to inputs and note time
        while unresolved:
            nextUnresolved = set()

            for node in unresolved:
                if isinstance(node, HlsConst):
                    continue
                try:
                    if node.usedBy:
                        node_end_t = min(map(parent_alap_time, node.usedBy))
                    else:
                        node_end_t = minimum_latency
                except UnresolvedChild:
                    # skip this node because we will find it
                    # after its dependency will be completed
                    # (unresolved children will be resolved and it will
                    # run resolution for this node again)
                    continue
                else:
                    if node.latency_pre != 0:
                        clk_start = start_clk(
                            node_end_t - node.latency_pre, clk_period)
                        clk_end = end_clk(node_end_t, clk_period)

                        if clk_start != clk_end:
                            assert clk_end > clk_start and clk_end - clk_start <= 1, (
                                clk_start, clk_end, node)
                            node_end_t = clk_end * clk_period

                node.alap_end = node_end_t
                node.alap_start = node_end_t - node.latency_pre
                nextUnresolved.update(
                    [n for n in node.dependsOn if not n.fixed_schedulation])

            unresolved = nextUnresolved

    def schedule(self):
        # discover time interval where operations can be schedueled
        maxTime = self.asap()
        self.alap(maxTime)

        if maxTime == 0:
            clk_count = 1
        else:
            clk_count = ceil(maxTime / self.parentHls.clk_period)

        schedulization = [[] for _ in range(clk_count)]
        # [DEBUG] scheduele by asap only
        for node in self.parentHls.nodes:
            time = node.alap_start
            assert time is not None, node
            schedulization[int(time * self.parentHls.clk_period)].append(node)
            node.scheduledIn = time
            node.scheduledInEnd = node.alap_end

        self.schedulization = schedulization


class ForceDirectedScheduler(HlsScheduler):
    class DistributionGraph():
        def __init__(self, op_type):
            self.operator = op_type
            self.nodes = []
            self.average_usage = {}

        def resource_usage(self, op_type, cstep):
            if op_type != self.operator or not self.nodes:
                return 0.0

            return sum([node.get_probability(cstep) for node in self.nodes])

        def set_average_resource_usage(self, node):
            usage = 0

            start, end = node.earliest, node.latest
            for i in range(start, end + 1):
                usage += self.resource_usage(node.operator, i)

            self.average_usage[node.operator] = usage / (end - start + 1)

        def self_force(self, node, cstep):
            if cstep < node.earliest or cstep > node.latest:
                return 0.0

            return self.resource_usage(node.operator, cstep) - self.average_usage.get(node.operator, 0)

        def succ_force(self, node, cstep):
            if node.mobility == 1:
                return 0.0

            node.earliest += 1
            force = self.self_force(node, cstep)
            node.earliest -= 1

            return force

        def pred_force(self, node, cstep):
            if node.mobility == 1:
                return 0.0

            node.earliest -= 1
            force = self.self_force(node, cstep)
            node.earliest += 1

            return force

    def __init__(self, *args, **kwargs):
        super(ForceDirectedScheduler, self).__init__(*args, **kwargs)

        self.succ_list = {}
        self.pred_list = {}

    @property
    def operators(self):
        nodes = []
        for node in self.parentHls.nodes:
            if hasattr(node, 'operator'):
                nodes.append(node)
        return nodes

    @property
    def unscheduled_operators(self):
        nodes = []
        for op in self.operators:
            if op.fixed_schedulation or op.mobility <= 1:
                continue
            nodes.append(op)
        return nodes

    def update_time_frames(self):
        self.alap(self.asap())

    def traverse(self, node):
        self.succ_list.setdefault(node, set())
        self.succ_list[node].update(
            [n for n in node.usedBy if hasattr(n, 'operator')])

        self.pred_list.setdefault(node, set())
        self.pred_list[node].update(
            [n for n in node.dependsOn if hasattr(n, 'operator')])

        for child in node.usedBy:
            self.succ_list[node].add(child)
            self.traverse(child)

    def force_scheduling(self):
        operators = self.operators
        for i in self.parentHls.inputs:
            self.traverse(i)

        #map(self.traverse, self.parentHls.inputs)
        unresolved = []
        for op in operators:
            if not op.fixed_schedulation and op.earliest != op.latest:
                unresolved.append(op)

        # distribution graphs
        print(unresolved)
        dgs = {}
        for node in unresolved:
            op = node.operator
            if op not in dgs:
                dgs[op] = self.DistributionGraph(op)
            dgs[op].set_average_resource_usage(node)

        for op in operators:
            if op.operator in dgs:
                dgs[op.operator].nodes.append(op)

        while True:
            self.update_time_frames()

            unresolved = list(self.unscheduled_operators)

            if not unresolved:
                break

            min_op = None
            min_force = 100
            scheduled_step = -1
            # print(list(unresolved))
            for node in unresolved:
                print(node)
                for step in range(node.earliest, node.latest + 1):
                    self_force = dgs[node.operator].self_force(node, step)
                    succ_force = pred_force = 0.0

                    #print("Usage: {} {}".format(step, dgs[node.operator].resource_usage(node.operator, step)))
                    for succ in self.succ_list[node]:
                        succ_force += dgs[node.operator].succ_force(succ, step)
                    for pred in self.pred_list[node]:
                        pred_force += dgs[node.operator].pred_force(pred, step)

                    total_force = self_force + succ_force + pred_force

                    if total_force < min_force:
                        min_force = total_force
                        scheduled_step = step
                        min_op = node

            self._reschedule(min_op, scheduled_step)
            min_op.fixed_schedulation = True

    def _reschedule(self, node, scheduled_step):
        step_diff = scheduled_step - node.earliest
        if not step_diff:
            return

        scheduled_start = node.asap_start + step_diff * self.parentHls.clk_period
        node.asap_start = node.alap_start = scheduled_start
        node.asap_end = node.alap_end = scheduled_start + node.latency_pre

        for parent in node.dependsOn:
            if isinstance(parent, HlsConst):
                continue
            parent.alap_start -= step_diff * self.parentHls.clk_period
            parent.alap_end -= step_diff * self.parentHls.clk_period

    def schedule(self):
        # discover time interval where operations can be schedueled
        maxTime = self.asap()
        self.alap(maxTime)
        self.force_scheduling()

        if maxTime == 0:
            clk_count = 1
        else:
            clk_count = ceil(maxTime / self.parentHls.clk_period)

        schedulization = [[] for _ in range(clk_count)]
        # [DEBUG] scheduele by asap only
        for node in self.parentHls.nodes:
            time = node.alap_start
            assert time is not None, node
            schedulization[int(time * self.parentHls.clk_period)].append(node)
            node.scheduledIn = time
            node.scheduledInEnd = node.alap_end

        self.schedulization = schedulization
