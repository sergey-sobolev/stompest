import re
from functools import partial

from stompest.error import StompFrameError
from stompest.protocol.spec import StompSpec

class _HeadersTransformer(object):
    _ESCAPE_CHARACTER = StompSpec.ESCAPE_CHARACTER

    @classmethod
    def get(cls, *args):
        try:
            return cls._INSTANCES[args]
        except KeyError:
            return cls._INSTANCES.setdefault(args, cls(*args))

    def __init__(self, version, command):
        self.version = version
        if command in StompSpec.COMMANDS_ESCAPE_EXCLUDED[version]:
            self._sub = lambda text: text
        else:
            escapeSequences = self._escapeSequences
            self._sub = partial(re.compile(self._regex).sub, lambda match: escapeSequences[match.group(1)])

    def __call__(self, text):
        try:
            return self._sub(text)
        except Exception as e:
            raise StompFrameError('No escape sequence defined for this character (version %s): %s [text=%s]' % (self.version, e, repr(text)))

    @property
    def _escapedCharacters(self):
        return StompSpec.ESCAPED_CHARACTERS[self.version]

class _HeadersEscaper(_HeadersTransformer):
    _INSTANCES = {} # each class needs its own instance cache

    @property
    def _escapeSequences(self):
        return dict((escapeSequence, '%s%s' % (self._ESCAPE_CHARACTER, character)) for (character, escapeSequence) in self._escapedCharacters.items())

    @property
    def _regex(self):
        return '(%s)' % '|'.join(map(re.escape, self._escapeSequences))

class _HeadersUnescaper(_HeadersTransformer):
    _INSTANCES = {} # each class needs its own instance cache

    @property
    def _escapeSequences(self):
        return dict(('%s%s' % (self._ESCAPE_CHARACTER, character), escapeSequence) for (character, escapeSequence) in self._escapedCharacters.items())

    @property
    def _regex(self):
        return '(%s)' % '|'.join(['%s.' % re.escape(self._ESCAPE_CHARACTER)] + [re.escape(c) for c in self._escapedCharacters.values() if c != self._ESCAPE_CHARACTER])

escape = _HeadersEscaper.get
unescape = _HeadersUnescaper.get
