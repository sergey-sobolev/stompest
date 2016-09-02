import binascii
import unittest

from stompest.protocol import StompFrame, StompSpec
from stompest.protocol.util import ispy2
import codecs

class StompFrameTest(unittest.TestCase):
    def test_frame(self):
        message = {'command': StompSpec.SEND, 'headers': {StompSpec.DESTINATION_HEADER: '/queue/world'}, 'body': 'two\nlines'}
        frame = StompFrame(**message)
        self.assertEqual(message['headers'], frame.headers)
        self.assertEqual(dict(frame), message)
        self.assertEqual(str(frame), """\
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
        self.assertEqual(str(frame), """\
%s

\x00""" % StompSpec.DISCONNECT)
        self.assertEqual(eval(repr(frame)), frame)

    def test_encoding(self):
        key = u'fen\xeatre'
        value = u'\xbfqu\xe9 tal?, s\xfc\xdf'
        command = StompSpec.DISCONNECT
        message = {'command': command, 'headers': {key: value}, 'version': StompSpec.VERSION_1_1}
        frame = StompFrame(**message)
        self.assertEqual(message['headers'], frame.headers)
        self.assertEqual(dict(frame), message)

        self.assertEqual(eval(repr(frame)), frame)
        frame.version = StompSpec.VERSION_1_1
        self.assertEqual(eval(repr(frame)), frame)
        if ispy2():
            self.assertEqual(str(frame), codecs.lookup('utf-8').encode(command + u'\n' + key + u':' + value + u'\n\n\x00')[0])
        else:
            self.assertEqual(str(frame), codecs.lookup('utf-8').encode(command + u'\n' + key + u':' + value + u'\n\n\x00')[0].decode())

        otherFrame = StompFrame(**message)
        self.assertEqual(frame, otherFrame)

        frame.version = StompSpec.VERSION_1_0
        self.assertRaises(UnicodeEncodeError, frame.__str__)

    def test_binary_body(self):
        body = binascii.a2b_hex('f0000a09')
        headers = {'content-length': str(len(body))}
        frame = StompFrame('MESSAGE', headers, body)
        self.assertEqual(frame.body, body)
        if ispy2():
            self.assertEqual(str(frame), 'MESSAGE\ncontent-length:4\n\n\xf0\x00\n\t\x00')

    def test_duplicate_headers(self):
        rawHeaders = (('foo', 'bar1'), ('foo', 'bar2'))
        headers = dict(reversed(rawHeaders))
        message = {
            'command': 'SEND',
            'body': 'some stuff\nand more',
            'rawHeaders': rawHeaders
        }
        frame = StompFrame(**message)
        self.assertEqual(frame.headers, headers)
        self.assertEqual(frame.rawHeaders, rawHeaders)
        rawFrame = 'SEND\nfoo:bar1\nfoo:bar2\n\nsome stuff\nand more\x00'
        self.assertEqual(str(frame), rawFrame)

        frame.unraw()
        self.assertEqual(frame.headers, headers)
        self.assertEqual(frame.rawHeaders, None)
        rawFrame = 'SEND\nfoo:bar1\n\nsome stuff\nand more\x00'
        self.assertEqual(str(frame), rawFrame)

    def test_non_string_arguments(self):
        message = {'command': 0, 'headers': {123: 456}, 'body': 789}
        frame = StompFrame(**message)
        self.assertEqual(frame.command, 0)
        self.assertEqual(frame.headers, {123: 456})
        self.assertEqual(frame.body, 789)
        self.assertEqual(dict(frame), message)
        self.assertEqual(str(frame), """\
0
123:456

789\x00""")
        self.assertEqual(eval(repr(frame)), frame)

    def test_unescape(self):
        frameBytes = """%s
\\n\\\\:\\c\t\\n

\x00""" % StompSpec.DISCONNECT

        frame = StompFrame(command=StompSpec.DISCONNECT, headers={'\n\\': ':\t\n'}, version=StompSpec.VERSION_1_1)
        self.assertEqual(str(frame), frameBytes)

        frameBytes = """%s
\\n\\\\:\\c\t\\r

\x00""" % StompSpec.DISCONNECT

        frame = StompFrame(command=StompSpec.DISCONNECT, headers={'\n\\': ':\t\r'}, version=StompSpec.VERSION_1_2)
        self.assertEqual(str(frame), frameBytes)

        frameBytes = """%s
\\n\\\\:\\c\t\r

\x00""" % StompSpec.DISCONNECT

        frame = StompFrame(command=StompSpec.DISCONNECT, headers={'\n\\': ':\t\r'}, version=StompSpec.VERSION_1_1)
        self.assertEqual(str(frame), frameBytes)

        frameBytes = """%s

\\::\t\r


\x00""" % StompSpec.DISCONNECT

        frame = StompFrame(command=StompSpec.DISCONNECT, headers={'\n\\': ':\t\r\n'}, version=StompSpec.VERSION_1_0)
        self.assertEqual(str(frame), frameBytes)

        frameBytes = """%s

\\::\t\r


\x00""" % StompSpec.CONNECT

        frame = StompFrame(command=StompSpec.CONNECT, headers={'\n\\': ':\t\r\n'})
        for version in StompSpec.VERSIONS:
            frame.version = version
            self.assertEqual(str(frame), frameBytes)

if __name__ == '__main__':
    unittest.main()
