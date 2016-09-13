import collections
import re

from stompest.error import StompFrameError

from stompest.protocol.frame import StompFrame, StompHeartBeat
from stompest.protocol.spec import StompSpec
from stompest.protocol.util import unescape

class StompParser(object):
    """This is a parser for a wire-level byte-stream of STOMP frames.
    
    :param version: A valid STOMP protocol version, or :obj:`None` (equivalent to the :attr:`DEFAULT_VERSION` attribute of the :class:`~.StompSpec` class).
    
    Example:

    >>> from stompest.protocol import StompParser
    >>> parser = StompParser('1.0') # STOMP 1.0 does not support the NACK command.
    >>> messages = [b'RECEIPT\\nreceipt-id:message-12345\\n\\n\\x00', b'NACK\\nsubscription:0\\nmessage-id:007\\n\\n\\x00']
    >>> for message in messages:
    ...     parser.add(message)
    ... 
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    stompest.error.StompFrameError: Invalid command: 'NACK'
    >>> parser.get()
    StompFrame(command='RECEIPT', rawHeaders=[('receipt-id', 'message-12345')])
    >>> parser.canRead()
    False
    >>> parser.get()
    None
    >>> parser = StompParser('1.1')
    >>> parser.add(messages[1])
    >>> parser.get()
    StompFrame(command='NACK', rawHeaders=[('subscription', '0'), ('message-id', '007')], version='1.1')    
    
    """
    SENTINEL = None

    _REGEX_LINE_DELIMITER = re.compile(StompSpec.LINE_DELIMITER.encode())

    def __init__(self, version=None):
        self.version = version
        self.reset()

    def add(self, data):
        """Add a byte-stream of wire-level data.
        
        :param data: A byte-stream, i.e., a :class:`str`-like (Python 2) or :class:`bytes`-like (Python 3) object.
        """
        self._data += data
        while self._parse():
            pass

    def canRead(self):
        """Indicates whether there are frames available.
        """
        return bool(self._frames)

    def get(self):
        """Return the next frame as a :class:`~.frame.StompFrame` object (if any), or :obj:`None` (otherwise).
        """
        if self.canRead():
            return self._frames.popleft()
        return self.SENTINEL

    def reset(self):
        """Reset internal state, including all fully or partially parsed frames.
        """
        self._frames = collections.deque()
        self._flush()
        self._next()

    def _append(self):
        if self._frame is not None:
            self._frame.version = self.version
            self._frames.append(self._frame)
        self._next()

    def _decode(self, data):
        text = StompSpec.codec(self.version).decode(data)[0]
        stripLineDelimiter = StompSpec.STRIP_LINE_DELIMITER.get(self.version, '')
        if stripLineDelimiter and text.endswith(stripLineDelimiter):
            return text[:-1]
        return text

    def _flush(self):
        self._data = bytearray()

    def _next(self):
        self._frame = None
        self._seek = 0
        self._length = -1

    def _parse(self):
        if len(self._data) <= self._seek:
            return

        if (self._frame is None) and (self._data[:1] == StompSpec.LINE_DELIMITER.encode()):
            self._data.pop(0)
            if self.version != StompSpec.VERSION_1_0:
                self._frame = StompHeartBeat()
                self._append()
            return bool(self._data)

        eof = self._data.find(StompSpec.FRAME_DELIMITER.encode(), self._seek)
        if eof == -1:
            if self._length != -1:
                self._raise('Expected frame delimiter (found %s instead)' % repr(bytes([self._data[self._seek]])))
            self._seek = len(self._data)
            return

        if self._frame is None:
            self._seek = self._length = self._parseHead(eof)
            return True

        self._parseBody()
        self._append()

        return bool(self._data)

    def _parseBody(self):
        self._frame.body = self._data[:self._length]
        self._truncate(self._length + 1)
        if self._frame.body and (self._frame.command not in StompSpec.COMMANDS_BODY_ALLOWED.get(self.version, [self._frame.command])): # @UndefinedVariable
            self._raise('No body allowed for this command: %s' % self._frame.command)

    def _parseCommand(self, line):
        if line not in StompSpec.COMMANDS[self.version]:
            self._raise('Invalid command: %s' % repr(line))
        self._frame = StompFrame(command=line, rawHeaders=[], version=self.version)

    def _parseHead(self, eof):
        start = 0
        for match in self._REGEX_LINE_DELIMITER.finditer(self._data):
            line = self._decode(self._data[start:match.start()])
            start = match.end()
            if self._frame is None:
                self._parseCommand(line)
            elif line:
                self._parseHeader(line)
            else:
                break
        self._truncate(start)
        return int(self._frame.headers.get(StompSpec.CONTENT_LENGTH_HEADER, eof - start))

    def _parseHeader(self, line):
        try:
            name, value = line.split(StompSpec.HEADER_SEPARATOR, 1)
        except ValueError:
            self._raise('No separator in header line: %s' % line)
        self._frame.rawHeaders.append(tuple(self._unescape(text) for text in (name, value)))

    def _raise(self, message):
        self._flush()
        raise StompFrameError(message)

    def _truncate(self, position):
        self._data[:position] = b''

    def _unescape(self, text):
        try:
            return unescape(self.version)(self._frame.command, text)
        except KeyError as e:
            self._raise('No escape sequence defined for this character: %s [text=%s]' % (e, repr(text)))

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, value):
        self._version = StompSpec.version(value)
