from hwtHls.scheduler.scheduler import HlsScheduler, asap, alap
from hwtHls.codeOps import HlsOperation, HlsConst, HlsRead, HlsWrite


class DistributionGraph():
    def __init__(self, op_type):
        self.operator = op_type
        self.nodes = []
        self.average_usage = {}

    def resource_usage(self, op_type, cstep):
        if op_type != self.operator or not self.nodes:
            return 0.0

        return sum(node.get_probability(cstep)
                   for node in self.nodes)

    def set_average_resource_usage(self, node):
        usage = 0
        op = node.operator
        start, end = node.get_earliest_clk(), node.get_latest_clk()
        for i in range(start, end + 1):
            usage += self.resource_usage(op, i)

        self.average_usage[op] = usage / (end - start + 1)

    def self_force(self, node, cstep):
        if cstep < node.get_earliest_clk() or cstep > node.get_latest_clk():
            return 0.0

        if isinstance(node, (HlsRead, HlsWrite)):
            return 0.0

        return self.resource_usage(node.operator, cstep) \
            - self.average_usage.get(node.operator, 0)


class ForceDirectedScheduler(HlsScheduler):
    """
    Force directed schedueler

    Force pulls operatoins betwee clk periods to specified clk_period
    Alg. places node with smallest force first, because this node is probably
    where it should be
    """

    def __init__(self, *args, **kwargs):
        super(ForceDirectedScheduler, self).__init__(*args, **kwargs)

        self.succ_list = {}
        self.pred_list = {}
        self.__operations = None

    def get_operations(self):
        if self.__operations is None:
            nodes = []
            for node in self.parentHls.nodes:
                if not isinstance(node, HlsConst):
                    nodes.append(node)
            self.__operations = nodes
        return self.__operations

    def get_unscheduled_operations(self):
        for node in self.get_operations():
            if node.fixed_schedulation or not node.get_mobility():
                continue
            yield node

    def update_time_frames(self):
        hls = self.parentHls
        maxTime = asap(hls.inputs, hls.outputs, hls.clk_period)
        alap(hls.outputs, self.parentHls.clk_period, maxTime)

    def traverse(self, node):
        if node in self.succ_list:
            return

        succ = self.succ_list.setdefault(node, set())
        for n in node.usedBy:
            if isinstance(n, HlsOperation):
                succ.add(n)
                self.traverse(n)

        pred = self.pred_list.setdefault(node, set())
        for n in node.dependsOn:
            if isinstance(n, HlsOperation):
                pred.add(n)

    def force_scheduling(self, step_limit=400):
        step_limit = int(step_limit)
        nodes = self.parentHls.nodes

        operations = self.get_operations()
        for n in nodes:
            self.traverse(n)

        self.update_time_frames()
        unresolved = []
        for node in nodes:
            # if isinstance(node, HlsConst):
            #    node.fixed_schedulation = True
            # elif isinstance(node, HlsRead):
            #    node.alap_start = node.asap_start = 0
            #    node.alap_end = node.asap_end = node.latency_pre + node.latency_post
            #    node.fixed_schedulation = True
            # elif isinstance(node, HlsWrite):
            #    node.asap_start = node.alap_start
            #    node.asap_end = node.alap_end
            #    node.fixed_schedulation = True
            # elif not node.fixed_schedulation:
            print(node.get_mobility(), node.__class__.__name__)

            if node.get_mobility():
                unresolved.append(node)
            else:
                node.fixed_schedulation = True
            # else:
            #    raise ValueError(node)

        # distribution graphs
        dgs = {}
        for node in unresolved:
            op = node.operator
            try:
                g = dgs[op]
            except KeyError:
                g = DistributionGraph(op)
                dgs[op] = g
            g.set_average_resource_usage(node)

        for node in operations:
            op = node.operator
            if op in dgs:
                dgs[op].nodes.append(node)

        while step_limit:
            print(step_limit, "step_limit", [
                  n.__class__.__name__ for n in unresolved])

            min_op = None
            min_force = None
            scheduled_step = None
            for node in self.get_unscheduled_operations():
                latest_clk = node.get_latest_clk()
                mobility = node.get_mobility()

                if not mobility:
                    node.fixed_schedulation = True
                    continue

                # for succ in self.succ_list[node]:
                #    succ_force += dgs[node.operator].succ_force(succ, step)
                #
                # for pred in self.pred_list[node]:
                #    pred_force += dgs[node.operator].pred_force(pred, step)

                # iterate over possible clks and choose that with lowest force
                force = 0.0
                for step in range(node.get_earliest_clk(), latest_clk + 1):
                    force = dgs[node.operator].self_force(node, step)

                    if min_force is None or force < min_force:
                        min_force = force
                        scheduled_step = step
                        min_op = node

            if min_op is None:
                # all nodes are placed
                break

            self._reschedule(min_op, scheduled_step)
            min_op.fixed_schedulation = True
            self.update_time_frames()
            step_limit -= 1

        t_offset = -min(n.alap_start for n in nodes)

        sched = {}
        for n in nodes:
            if isinstance(n, (HlsRead, HlsWrite)):
                sched[n] = (n.alap_start, n.alap_end)
            else:
                sched[n] = (n.alap_start + t_offset, n.alap_end + t_offset)
        return sched

    def _reschedule(self, node, scheduled_step):
        step_diff = scheduled_step - node.get_earliest_clk()
        if not step_diff:
            return
        clk_period = step_diff * self.parentHls.clk_period
        time_diff = step_diff * clk_period

        scheduled_start = node.asap_start + time_diff
        node.asap_start = node.alap_start = scheduled_start
        node.asap_end = node.alap_end = scheduled_start + node.latency_pre
        node.fixed_schedulation = True

        # for parent in node.dependsOn:
        #    if isinstance(parent, HlsConst):
        #        continue
        #    parent.alap_start -= time_diff
        #    parent.alap_end -= time_diff

    def schedule(self):
        # discover time interval where operations can be schedueled
        hls = self.parentHls
        maxTime = asap(hls.inputs, hls.outputs, hls.clk_period)
        alap(hls.outputs, hls.clk_period, maxTime)
        sched = self.force_scheduling()
        self.apply_scheduelization_dict(sched)
