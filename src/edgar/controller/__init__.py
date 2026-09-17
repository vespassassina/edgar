# edgar.controller is v3, and removable: nothing in Core, v1 or v2 imports it, a test
# proves it, and CI deletes the package and runs the suite below it [NFR-12].
#
# The public surface is filled in as M13 lands; `controller/triggers.py` is the
# deterministic half and has no dependency on the rest.

from __future__ import annotations
