from .spec import StompSpec
from .util import escape

class StompFrame(object):
    """This object represents a STOMP frame.
    
    :param command: A valid STOMP command.
    :param headers: The STOMP headers (represented as a :class:`dict`), or :obj:`None` (no headers).
    :param body: The frame body.
    :param rawHeaders: The raw STOMP headers (represented as a collection of (header, value) tuples), or :obj:`None` (no raw headers).
    :param version: A valid STOMP protocol version, or :obj:`None` (equivalent to the :attr:`DEFAULT_VERSION` attribute of the :class:`~.StompSpec` class).
        
    .. note :: The frame's attributes are internally stored as arbitrary Python objects. The frame's :attr:`version` attribute controls the wire-level encoding of its :attr:`command` and :attr:`headers` (depending on STOMP protocol version, this may be ASCII or UTF-8), while its :attr:`body` is not encoded at all (it's just cast as a :class:`str`).
    """
    INFO_LENGTH = 20
    _KEYWORDS_AND_FIELDS = [('headers', '_headers', {}), ('body', 'body', ''), ('rawHeaders', 'rawHeaders', None), ('version', 'version', StompSpec.DEFAULT_VERSION)]

    def __init__(self, command, headers=None, body='', rawHeaders=None, version=None):
        self.version = version

        self.command = command
        self.headers = headers
        self.body = body
        self.rawHeaders = rawHeaders

    def __eq__(self, other):
        """Two frames are considered equal if, and only if, they render the same wire-level frame, that is, if their string representation is identical."""
        return str(self) == str(other)

    def __iter__(self):
        yield ('command', self.command)
        for (keyword, field, default) in self._KEYWORDS_AND_FIELDS:
            value = getattr(self, field)
            if value != default:
                yield (keyword, getattr(self, field))

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, ', '.join(
            ('%s=%s' % (keyword, repr(getattr(self, field))))
            for (keyword, field)
            in ([('command', 'command')] + [(k, f) for (k, f, _) in self._KEYWORDS_AND_FIELDS])
        ))

    def __str__(self):
        """Render the wire-level representation of a STOMP frame."""
        headers = sorted(self.headers.iteritems()) if self.rawHeaders is None else self.rawHeaders
        headers = ''.join('%s:%s%s' % (self._encode(self._escape(unicode(key))), self._encode(self._escape(unicode(value))), StompSpec.LINE_DELIMITER) for (key, value) in headers)
        return StompSpec.LINE_DELIMITER.join([self._encode(unicode(self.command)), headers, '%s%s' % (self.body, StompSpec.FRAME_DELIMITER)])

    def info(self):
        """Produce a log-friendly representation of the frame (show only non-trivial content, and truncate the message to INFO_LENGTH characters)."""
        headers = self.headers and 'headers=%s' % self.headers
        body = self.body[:self.INFO_LENGTH]
        if body not in self.body:
            body = '%s...' % body
        body = body and ('body=%s' % repr(body))
        version = 'version=%s' % self.version
        info = ', '.join(i for i in (headers, body, version) if i)
        return '%s frame [%s]' % (self.command, info)

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, value):
        self._version = StompSpec.version(value)

    def _encode(self, text):
        return StompSpec.CODECS[self.version].encode(text)[0]

    def _escape(self, text):
        return escape(self.version)(self.command, text)

    @property
    def headers(self):
        return self._headers if (self.rawHeaders is None) else dict(reversed(self.rawHeaders))

    @headers.setter
    def headers(self, value):
        self._headers = dict(value or {})

    def unraw(self):
        """If the frame has raw headers, copy their deduplicated version to the :attr:`headers` attribute, and remove the raw headers afterwards."""
        if self.rawHeaders is None:
            return
        self.headers = self.headers
        self.rawHeaders = None

class StompHeartBeat(object):
    """This object represents a STOMP heart-beat. Its string representation (via :meth:`__str__`) renders the wire-level STOMP heart-beat."""
    __slots__ = ('version',)

    def __eq__(self, other):
        return isinstance(other, StompHeartBeat)

    def __nonzero__(self):
        return False

    def __repr__(self):
        return '%s()' % self.__class__.__name__

    def __str__(self):
        return StompSpec.LINE_DELIMITER

    def info(self):
        return 'heart-beat'
