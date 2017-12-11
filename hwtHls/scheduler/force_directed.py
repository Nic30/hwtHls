from hwtHls.scheduler.scheduler import HlsScheduler
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

        start, end = node.earliest, node.latest
        for i in range(start, end + 1):
            usage += self.resource_usage(node.operator, i)

        self.average_usage[node.operator] = usage / (end - start + 1)

    def self_force(self, node, cstep):
        if cstep < node.earliest or cstep > node.latest:
            return 0.0
        if isinstance(node, (HlsRead, HlsWrite)):
            return 0.0
        return self.resource_usage(node.operator, cstep) \
            - self.average_usage.get(node.operator, 0)

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


class ForceDirectedScheduler(HlsScheduler):

    def __init__(self, *args, **kwargs):
        super(ForceDirectedScheduler, self).__init__(*args, **kwargs)

        self.succ_list = {}
        self.pred_list = {}
        self.__operations = None

    def get_operations(self):
        if self.__operations is None:
            nodes = []
            for node in self.parentHls.nodes:
                if isinstance(node, HlsOperation):
                    nodes.append(node)
            self.__operations = nodes
        return self.__operations

    def get_unscheduled_operations(self):
        nodes = []
        for op in self.get_operations():
            if op.fixed_schedulation or op.mobility <= 1:
                continue
            nodes.append(op)
        return nodes

    def update_time_frames(self):
        self.alap(self.asap())

    def traverse(self, node):
        self.succ_list.setdefault(node, set())
        self.succ_list[node].update(
            (n for n in node.usedBy
             if isinstance(n, HlsOperation)))

        self.pred_list.setdefault(node, set())
        self.pred_list[node].update(
            (n for n in node.dependsOn
             if isinstance(n, HlsOperation)))

        for child in node.usedBy:
            self.succ_list[node].add(child)
            self.traverse(child)

    def force_scheduling(self, step_limit=400):
        step_limit = int(step_limit)

        operations = self.get_operations()
        for i in self.parentHls.inputs:
            self.traverse(i)

        #map(self.traverse, self.parentHls.inputs)
        unresolved = []
        for op in operations:
            if not op.fixed_schedulation and op.earliest != op.latest:
                unresolved.append(op)

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
            print(step_limit, "step_limit")
            self.update_time_frames()

            unresolved = self.get_unscheduled_operations()
            if not unresolved:
                break

            min_op = None
            min_force = None
            scheduled_step = -1
            # print(list(unresolved))
            for node in unresolved:
                # print(node)
                for step in range(node.earliest, node.latest + 1):
                    self_force = dgs[node.operator].self_force(node, step)
                    succ_force = pred_force = 0.0

                    # print("Usage: {} {}".format(step,
                    #                            dgs[node.operator]
                    #                           .resource_usage(node.operator,
                    #                                           step)))
                    for succ in self.succ_list[node]:
                        succ_force += dgs[node.operator].succ_force(succ, step)

                    for pred in self.pred_list[node]:
                        pred_force += dgs[node.operator].pred_force(pred, step)

                    total_force = self_force + succ_force + pred_force

                    if min_force is None or total_force < min_force:
                        min_force = total_force
                        scheduled_step = step
                        min_op = node

            self._reschedule(min_op, scheduled_step)
            min_op.fixed_schedulation = True
            step_limit -= 1

        return {
            n: (n.alap_start, n.alap_end)
            for n in self.parentHls.nodes
        }

    def _reschedule(self, node, scheduled_step):
        step_diff = scheduled_step - node.earliest
        if not step_diff:
            return
        clk_period = step_diff * self.parentHls.clk_period
        time_diff = step_diff * clk_period

        scheduled_start = node.asap_start + time_diff
        node.asap_start = node.alap_start = scheduled_start
        node.asap_end = node.alap_end = scheduled_start + node.latency_pre

        for parent in node.dependsOn:
            if isinstance(parent, HlsConst):
                continue
            parent.alap_start -= time_diff
            parent.alap_end -= time_diff

    def schedule(self):
        # discover time interval where operations can be schedueled
        maxTime = self.asap()
        self.alap(maxTime)
        sched = self.force_scheduling()
        self.apply_scheduelization_dict(sched)
