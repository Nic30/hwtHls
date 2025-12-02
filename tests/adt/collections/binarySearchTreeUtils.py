from collections import deque
from typing import Callable, Optional, TypeVar, Generic


# https://www.geeksforgeeks.org/properties-of-binary-tree/
# number of nodes at level = 2**level
# number of nodes in tree = (2**height) - 1
# levels required for N nodes = log2(N+1)
# levels required for L leaves = |log2(L)|+ 1
def _binaryTreeGetNumberOfItemsForHeight(height: int) -> int:
    return int(2 ** height) - 1


KeyT = TypeVar("KeyT")
ValueT = TypeVar("ValueT")


class BinTreeNode(Generic[KeyT, ValueT]):

    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None


def compute_max_index(node: BinTreeNode[KeyT, ValueT] | None, index=0):
    if not node:
        return -1
    left_max = compute_max_index(node.left, 2 * index + 1)
    right_max = compute_max_index(node.right, 2 * index + 2)
    return max(index, left_max, right_max)


def treeToTreeInArray(root: BinTreeNode[KeyT, ValueT] | None) -> list[tuple[KeyT, ValueT]]:
    if not root:
        return []

    max_index = compute_max_index(root)
    result = [None] * (max_index + 1)
    # use queue to iterate tree layer by layer, left to right
    queue = deque([(root, 0)])
    while queue:
        node, i = queue.popleft()
        result[i] = (node.key, node.value)
        if node.left:
            queue.append((node.left, 2 * i + 1))
        if node.right:
            queue.append((node.right, 2 * i + 2))

    return result


def inorder_traversal(
    root: BinTreeNode[KeyT, ValueT] | None,
    fn: Callable[[BinTreeNode[KeyT, ValueT]], None]
) -> None:
    """Iterative inorder: Left -> Root -> Right using stack."""
    stack: list[BinTreeNode[KeyT, ValueT]] = []
    current: Optional[BinTreeNode[KeyT, ValueT]] = root
    while stack or current:
        while current:
            stack.append(current)
            current = current.left
        current = stack.pop()
        fn(current)
        current = current.right


def preorder_traversal(
    root: Optional[BinTreeNode[KeyT, ValueT]],
    fn: Callable[[BinTreeNode[KeyT, ValueT]], None]
) -> None:
    """Iterative preorder: Root -> Left -> Right using stack."""
    if not root:
        return
    stack: list[BinTreeNode[KeyT, ValueT]] = [root]
    while stack:
        node: BinTreeNode[KeyT, ValueT] = stack.pop()
        fn(node)
        if node.right:
            stack.append(node.right)
        if node.left:
            stack.append(node.left)


def postorder_traversal(
    root: Optional[BinTreeNode[KeyT, ValueT]],
    fn: Callable[[BinTreeNode[KeyT, ValueT]], None]
) -> None:
    """Iterative postorder: Left -> Right -> Root using two stacks."""
    if not root:
        return
    stack1: list[BinTreeNode[KeyT, ValueT]] = [root]
    stack2: list[BinTreeNode[KeyT, ValueT]] = []
    while stack1:
        node: BinTreeNode[KeyT, ValueT] = stack1.pop()
        stack2.append(node)
        if node.left:
            stack1.append(node.left)
        if node.right:
            stack1.append(node.right)
    while stack2:
        fn(stack2.pop())


def level_order_traversal(
    root: Optional[BinTreeNode[KeyT, ValueT]],
    fn: Callable[[BinTreeNode[KeyT, ValueT]], None]
) -> None:
    """Iterative level order: BFS using queue."""
    if not root:
        return
    queue: deque[BinTreeNode[KeyT, ValueT]] = deque([root])
    while queue:
        node: BinTreeNode[KeyT, ValueT] = queue.popleft()
        fn(node)
        if node.left:
            queue.append(node.left)
        if node.right:
            queue.append(node.right)


def sortedArrayToBst(arr: list[tuple[KeyT, ValueT]]) -> Optional[BinTreeNode[KeyT, ValueT]]:
    if not arr:
        return None

    mid = len(arr) // 2
    key, value = arr[mid]
    root = BinTreeNode(key, value)
    root.left = sortedArrayToBst(arr[:mid])
    root.right = sortedArrayToBst(arr[mid + 1:])
    return root
