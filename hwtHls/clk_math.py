import sys


epsilon = sys.float_info.epsilon


def start_clk(time: float, clk_period: float):
    """
    :return: index of clk period for start time
    """
    return int((time + epsilon) // clk_period)


def end_clk(time: float, clk_period: float):
    """
    :return: index of clk period for end time
    """
    return int((time - epsilon) // clk_period)


def start_of_next_clk_period(time: float, clk_period: float):
    """
    :return: start time of next clk period
    """
    return (start_clk(time, clk_period) + 1) * clk_period


def clk_period_diff(start: float, end: float, clk_period: float):
    """
    :return: how many clk periods is between start and end
    """
    assert start <= end, (start, end)
    d = end_clk(end, clk_period) - start_clk(start, clk_period)
    assert d >= 0.0, (start, end)
    return d
