"""Repository paths without workstation-specific assumptions."""

import os


PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(PACKAGE_DIR)
REPO_ROOT = os.path.dirname(SRC_DIR)


def repo_path(*parts):
    """Return an absolute path rooted at this repository checkout."""
    return os.path.join(REPO_ROOT, *parts)

