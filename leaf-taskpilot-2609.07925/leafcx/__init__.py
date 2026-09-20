"""LeafCX — Leaf + TaskPilot (arXiv:2609.07925) ported to self-serve account management.

The paper post-trains a 4B policy on SWE tasks inside a five-tool harness called
Leaf, with an online curriculum called TaskPilot.  This package keeps the parts
that are reproducible without 8x B200s:

  * the Leaf harness (five file tools, "reply with no tool call" termination,
    hidden tests the agent cannot see, binary F2P/P2P reward), and
  * the TaskPilot control loop (estimate the current policy's solve rate on a
    candidate task, admit only tasks on the learnability frontier, refine the
    rest).

The domain is a used-car marketplace's self-serve account-management surface
instead of a git repository.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
