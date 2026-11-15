class CraftpipeError(Exception):
    """Base class for every error craftpipe reports to the user."""


class UnsupportedFormatError(CraftpipeError):
    """The input is not a schematic format craftpipe can read."""


class UnmappedBlocksError(CraftpipeError):
    """The schematic contains blocks with no Mineclonia mapping."""

    def __init__(self, report):
        self.report = report
        n = sum(e.count for e in report.unmapped.values())
        super().__init__(f"{n} block(s) in {len(report.unmapped)} state(s) have no mapping")
