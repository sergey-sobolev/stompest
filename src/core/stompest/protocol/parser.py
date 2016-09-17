import collections
import re

from stompest._backwards import binaryType
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

    _LINE_DELIMITER = StompSpec.LINE_DELIMITER.encode()
    _FRAME_DELIMITER = StompSpec.FRAME_DELIMITER.encode()

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

    def _append(self):
        self._frames.append(self._frame)
        self._next()

    def _flush(self):
        self._data = bytearray()
        self._next()

    def _next(self):
        self._frame = None
        self._length = None
        self._seek = 0

    def _parse(self):
        if len(self._data) <= self._seek:
            return

        if self._frame is None:
            return self._parseHeartBeat() or self._parseHead()

        return self._parseEndOfFrame() and self._parseBody()

    def _parseBody(self):
        self._frame.body = binaryType(memoryview(self._data)[:self._length])
        self._truncate(self._length + 1)
        if self._frame.body and self._frame.command not in self._commandsBodyAllowed: # @UndefinedVariable
            self._raise('No body allowed for this command (version %s): %s' % (self.version, self._frame.command))
        self._append()
        return True

    def _parseEndOfFrame(self):
        if self._length is None:
            eof = self._data.find(self._FRAME_DELIMITER, self._seek)
            if eof == -1:
                self._seek = len(self._data)
                return
            self._length = eof
        eof = binaryType(self._data[self._length:self._length + 1])
        if eof != self._FRAME_DELIMITER:
            self._raise('Expected frame delimiter (found %r instead)' % eof)
        return True

    def _parseHead(self):
        try:
            end = self._findHead(self._data).end()
        except AttributeError:
            return
        command, rawHeaders = None, []
        for line in self._data[:end].decode(self._codec).split(StompSpec.LINE_DELIMITER):
            if self._stripLineDelimiter and line.endswith(self._stripLineDelimiter):
                line = line[:-1]
            if command is None:
                command = line
                if command not in self._commands:
                    self._raise('Invalid command (version %s): %s' % (self.version, command))
                _unescape = unescape(self.version, command)
                continue
            if not line:
                break
            try:
                name, value = line.split(StompSpec.HEADER_SEPARATOR, 1)
            except ValueError:
                self._raise('No separator in header line: %s' % line)
            rawHeaders.append((_unescape(name), _unescape(value)))
        self._truncate(end)
        self._frame = StompFrame(command=command, rawHeaders=rawHeaders, version=self.version)
        try:
            self._length = self._seek = int(self._frame.headers[StompSpec.CONTENT_LENGTH_HEADER])
        except KeyError:
            pass
        return True

    def _parseHeartBeat(self):
        if not self._data.startswith(self._LINE_DELIMITER):
            return
        self._truncate(1)
        if self.version != StompSpec.VERSION_1_0:
            self._frame = StompHeartBeat()
            self._frame.version = self.version
            self._append()
        return True

    def _raise(self, message):
        self._flush()
        raise StompFrameError(message)

    def _truncate(self, position):
        self._data[:position] = b''

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, value):
        self._version = version = StompSpec.version(value)
        self._commands = StompSpec.COMMANDS[version]
        self._commandsBodyAllowed = StompSpec.COMMANDS_BODY_ALLOWED[self.version]
        self._codec = StompSpec.codec(version).name
        self._stripLineDelimiter = StompSpec.STRIP_LINE_DELIMITER.get(version, '')
        self._findHead = re.compile(2 * ('%s?%s' % (self._stripLineDelimiter, StompSpec.LINE_DELIMITER) if self._stripLineDelimiter else StompSpec.LINE_DELIMITER).encode()).search
