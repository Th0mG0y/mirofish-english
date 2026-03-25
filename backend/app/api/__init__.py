"""
API routing module
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
search_bp = Blueprint('search', __name__)
deliberation_bp = Blueprint('deliberation', __name__)

from . import graph  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401
from . import search  # noqa: E402, F401
from . import deliberation  # noqa: E402, F401

