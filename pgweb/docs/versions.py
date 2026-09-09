"""The upstream development manual uses tree 0 and the /devel/ URL."""

DEVEL_MAJOR_VERSION = 20


def manual_major(tree):
    return DEVEL_MAJOR_VERSION if tree == 0 else int(tree)


def manual_tree(major):
    return 0 if major == DEVEL_MAJOR_VERSION else major
