from __future__ import unicode_literals

import unittest

from stompest._backwards import binaryType
from stompest.protocol import StompFrame, StompSpec

class StompFrameTest(unittest.TestCase):
    def test_frame(self):
        message = {'command': StompSpec.SEND, 'headers': {StompSpec.DESTINATION_HEADER: '/queue/world'}, 'body': b'two\nlines'}
        frame = StompFrame(**message)
        self.assertEqual(message['headers'], frame.headers)
        self.assertEqual(dict(frame), message)
        self.assertEqual(frame.__unicode__(), """\
%s
%s:/queue/world

two
lines\x00""" % (StompSpec.SEND, StompSpec.DESTINATION_HEADER))
        self.assertEqual(eval(repr(frame)), frame)

    def test_frame_without_headers_and_body(self):
        message = {'command': StompSpec.DISCONNECT}
        frame = StompFrame(**message)
        self.assertEqual(frame.headers, {})
        self.assertEqual(dict(frame), message)
        self.assertEqual(frame.__unicode__(), """\
%s

\x00""" % StompSpec.DISCONNECT)
        self.assertEqual(eval(repr(frame)), frame)

    def test_encoding(self):
        key = b'fen\xc3\xaatre'.decode('utf-8')
        value = b'\xc2\xbfqu\xc3\xa9 tal?'.decode('utf-8')
        command = StompSpec.DISCONNECT
        message = {'command': command, 'headers': {key: value}, 'version': StompSpec.VERSION_1_1}
        frame = StompFrame(**message)
        self.assertEqual(message['headers'], frame.headers)
        self.assertEqual(dict(frame), message)

        self.assertEqual(eval(repr(frame)), frame)
        frame.version = StompSpec.VERSION_1_1
        self.assertEqual(eval(repr(frame)), frame)
        expectedResult = command + '\n' + key + ':' + value + '\n\n\x00'
        self.assertEqual(frame.__unicode__(), expectedResult)

        otherFrame = StompFrame(**message)
        self.assertEqual(frame, otherFrame)

        frame.version = StompSpec.VERSION_1_0
        self.assertRaises(UnicodeEncodeError, frame.__str__)

    def test_binary_body(self):
        body = b'\xf0\x00\x0a\x09'
        headers = {'content-length': str(len(body))}
        frame = StompFrame('MESSAGE', headers, body)
        self.assertEqual(frame.body, body)
        self.assertEqual(binaryType(frame), b'MESSAGE\ncontent-length:4\n\n\xf0\x00\n\t\x00')

    def test_duplicate_headers(self):
        rawHeaders = (('foo', 'bar1'), ('foo', 'bar2'))
        headers = dict(reversed(rawHeaders))
        message = {
            'command': 'SEND',
            'body': b'some stuff\nand more',
            'rawHeaders': rawHeaders
        }
        frame = StompFrame(**message)
        self.assertEqual(frame.headers, headers)
        self.assertEqual(frame.rawHeaders, rawHeaders)
        rawFrame = b'SEND\nfoo:bar1\nfoo:bar2\n\nsome stuff\nand more\x00'
        self.assertEqual(binaryType(frame), rawFrame)

        frame.unraw()
        self.assertEqual(frame.headers, headers)
        self.assertEqual(frame.rawHeaders, None)
        rawFrame = b'SEND\nfoo:bar1\n\nsome stuff\nand more\x00'
        self.assertEqual(binaryType(frame), rawFrame)

    def test_non_string_arguments(self):
        message = {'command': 0, 'headers': {123: 456}}
        frame = StompFrame(**message)
        self.assertEqual(frame.command, '0')
        self.assertEqual(frame.headers, {123: 456})
        self.assertEqual(dict(frame), {'command': '0', 'headers': {123: 456}})
        self.assertEqual(binaryType(frame), b'0\n123:456\n\n\x00')

        message = {'command': 'bla', 'headers': {123: 456}}
        frame = StompFrame(**message)
        self.assertEqual(binaryType(frame), b'bla\n123:456\n\n\x00')
        self.assertEqual(eval(repr(frame)), frame)

    def test_unescape(self):
        frameString = """%s
\\n\\\\:\\c\t\\n

\x00""" % StompSpec.DISCONNECT

        frame = StompFrame(command=StompSpec.DISCONNECT, headers={'\n\\': ':\t\n'}, version=StompSpec.VERSION_1_1)
        self.assertEqual(frame.__unicode__(), frameString)

        frameString = """%s
\\n\\\\:\\c\t\\r

\x00""" % StompSpec.DISCONNECT

        frame = StompFrame(command=StompSpec.DISCONNECT, headers={'\n\\': ':\t\r'}, version=StompSpec.VERSION_1_2)
        self.assertEqual(frame.__unicode__(), frameString)

        frameString = """%s
\\n\\\\:\\c\t\r

\x00""" % StompSpec.DISCONNECT

        frame = StompFrame(command=StompSpec.DISCONNECT, headers={'\n\\': ':\t\r'}, version=StompSpec.VERSION_1_1)
        self.assertEqual(frame.__unicode__(), frameString)

        frameString = """%s

\\::\t\r


\x00""" % StompSpec.DISCONNECT

        frame = StompFrame(command=StompSpec.DISCONNECT, headers={'\n\\': ':\t\r\n'}, version=StompSpec.VERSION_1_0)
        self.assertEqual(frame.__unicode__(), frameString)

        frameString = """%s

\\::\t\r


\x00""" % StompSpec.CONNECT

        frame = StompFrame(command=StompSpec.CONNECT, headers={'\n\\': ':\t\r\n'})
        for version in StompSpec.VERSIONS:
            frame.version = version
            self.assertEqual(frame.__unicode__(), frameString)

if __name__ == '__main__':
    unittest.main()
