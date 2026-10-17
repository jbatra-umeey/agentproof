from .codefix import run as codefix
from .reports import run as reports
from .research import run as research
from .support import run as support

WORKFLOWS = {"research": research, "codefix": codefix, "support": support, "reports": reports}
