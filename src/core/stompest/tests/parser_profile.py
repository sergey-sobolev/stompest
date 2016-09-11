from __future__ import unicode_literals

import string
from random import choice, randrange

from stompest._backwards import binaryType, makeBytesFromSequence
from stompest.protocol import StompFrame, StompParser, StompSpec
from stompest.protocol.frame import StompHeartBeat

M = 1000
N = 1000

def createRange(n):
    j = 0
    while j < n:
        yield j
        j += 1

textFrame = StompFrame(
    command='MESSAGE'
    , headers=dict(('some key %d' % j, 'some value %d' % j) for j in createRange(10))
    , body=''.join(choice(string.printable) for _ in createRange(M)).encode()
    , version=StompSpec.VERSION_1_1
)
binaryFrame = StompFrame(
    command='MESSAGE'
    , headers={StompSpec.CONTENT_LENGTH_HEADER: M}
    , body=makeBytesFromSequence(randrange(256) for _ in createRange(M))
)
heartBeatFrame = StompHeartBeat()

def testText():
    pass

def main():
    parser = StompParser(version=StompSpec.VERSION_1_1)
    for _ in createRange(M):
        parser.add(binaryType(binaryFrame))
        while parser.canRead():
            parser.get()

if __name__ == '__main__':
    import cProfile
    import pstats
    cProfile.run('main()', 'parserstats')
    pstats.Stats('parserstats').strip_dirs().sort_stats(-1).print_stats()

