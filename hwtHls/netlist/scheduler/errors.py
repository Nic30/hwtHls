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
