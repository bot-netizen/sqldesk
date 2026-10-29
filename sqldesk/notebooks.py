"""
Whether what is on the screen still means anything.

A notebook has a session: `df` assigned in one cell is still there five cells
later, which is what people expect and why they reach for Jupyter. It is also
why notebooks rot. The number in cell four was computed from cell one, cell
one has been edited and re-run twice since, and nothing on the page says so.
Zeppelin has the session and no staleness tracking, and that is the whole
difference between a notebook you can believe and one you have to re-run to
believe.

So every run records which cells it read, and this works out what that makes
true now.

**Staleness carries.** If A feeds B and B feeds C, re-running A makes B stale
-- and C stale too, because C's number was computed from a B that was
computed from an older A. Stopping at the direct inputs would mark B and
quietly leave C looking trustworthy, which is the failure this exists to
prevent and the one that is hardest to notice.

Names, not numbers, throughout. A cell refers to another by name, so
inserting, deleting and reordering leave every reference pointing at what it
meant.
"""

import logging
import re

logger = logging.getLogger(__name__)

#: What a cell may be called. Letters, digits and underscores, not starting
#: with a digit -- because the name is used as a relation in SQL and as a
#: variable in Python, and anything else would need quoting in one of them and
#: be illegal in the other.
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Long enough to be descriptive, short enough to read in a reference.
MAX_NAME = 63


def name_problem(name, taken=()):
    """
    Why this cell name will not do, or None.

    A sentence rather than a boolean: the person typing it is the one who has
    to fix it, and "invalid" tells them nothing.
    """
    if not name or not name.strip():
        return "A cell needs a name. Other cells use it to refer to this one."

    name = name.strip()
    if len(name) > MAX_NAME:
        return "That name is {} characters; {} is the most.".format(len(name), MAX_NAME)

    if not NAME.match(name):
        return (
            "A cell name can hold letters, digits and underscores, and cannot start with a "
            "digit -- it is used as a table name in SQL and as a variable in Python."
        )

    if name in taken:
        return "This notebook already has a cell called {}.".format(name)

    return None


def _ran_at(cell):
    return getattr(cell, "last_run_at", None)


def staleness(cells, runs_by_cell):
    """
    `{cell id: [names of the cells that moved on under it]}`.

    `runs_by_cell` maps a cell id to the names it read when it last ran --
    what it read, not what it refers to now, because staleness is a statement
    about the number on the screen and that number came from the earlier run.

    A cell that has never run is not stale; it is unrun, which the page shows
    differently and which nobody is being misled by.
    """
    by_name = {cell.name: cell for cell in cells}
    reasons = {}
    # "being worked out" during the walk, so a reference that loops round to
    # itself ends rather than recursing until the stack gives out. A loop
    # should not be constructible, but it should not take the page down if it
    # ever is.
    state = {}

    def walk(cell):
        if cell.id in state:
            return state[cell.id]
        state[cell.id] = False  # assumed while its own inputs are examined

        mine = _ran_at(cell)
        if mine is None:
            state[cell.id] = False
            return False

        moved = []
        for input_name in runs_by_cell.get(cell.id) or []:
            upstream = by_name.get(input_name)
            if upstream is None:
                # The cell it read is gone. That is a broken reference, which
                # is reported on its own rather than as staleness -- "the
                # thing you depended on no longer exists" and "the thing you
                # depended on has changed" need different answers.
                continue
            upstream_ran = _ran_at(upstream)
            if upstream_ran is not None and upstream_ran > mine:
                moved.append(input_name)
            elif walk(upstream):
                # Carried: this cell's number came from one that is itself out
                # of date, so this number is out of date too.
                moved.append(input_name)

        state[cell.id] = bool(moved)
        if moved:
            reasons[cell.id] = moved
        return state[cell.id]

    for cell in cells:
        walk(cell)
    return reasons


def missing_inputs(cells, runs_by_cell):
    """
    `{cell id: [names it read that no longer exist]}`.

    Separate from staleness on purpose. A cell whose input was deleted is not
    showing an old number -- it is showing a number that can no longer be
    reproduced at all, and re-running it will fail rather than refresh it.
    """
    known = {cell.name for cell in cells}
    gone = {}
    for cell in cells:
        if _ran_at(cell) is None:
            continue
        absent = [one for one in (runs_by_cell.get(cell.id) or []) if one not in known]
        if absent:
            gone[cell.id] = absent
    return gone
