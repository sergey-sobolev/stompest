import copy
import functools

from stompest.protocol import StompSpec
from stompest.protocol.util import ispy2

_RESERVED_HEADERS = set([StompSpec.MESSAGE_ID_HEADER, StompSpec.DESTINATION_HEADER, u'timestamp', u'expires', u'priority'])

def filterReservedHeaders(headers):
    return dict((header, value) for (header, value) in headers.items() if header not in _RESERVED_HEADERS)

def checkattr(attribute):
    def _checkattr(f):
        @functools.wraps(f)
        def __checkattr(self, *args, **kwargs):
            getattr(self, attribute)
            return f(self, *args, **kwargs)
        return __checkattr
    return _checkattr

def cloneFrame(frame, persistent=None):
    frame = copy.deepcopy(frame)
    frame.unraw()
    headers = filterReservedHeaders(frame.headers)
    if persistent is not None:
        cast = unicode if ispy2() else str
        headers[u'persistent'] = cast(bool(persistent)).lower()
    frame.headers = headers
    return frame
