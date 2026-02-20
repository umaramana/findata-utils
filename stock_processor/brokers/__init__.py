"""
Broker-specific parsers for stock transaction processing.
Each broker module exports a process() function that takes a file path or file-like object
and returns a standardized DataFrame ready for Drake mapping.
"""

from . import fidelity
from . import schwab
from . import robinhood
from . import merrill
from . import apex_clearing

__all__ = ['fidelity', 'schwab', 'robinhood', 'merrill', 'apex_clearing']
