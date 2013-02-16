import binascii
import unittest

from stompest.protocol.frame import StompFrame
from stompest.protocol.spec import StompSpec

class StompFrameTest(unittest.TestCase):
    def test_frame(self):
        message = {'command': 'SEND', 'headers': {StompSpec.DESTINATION_HEADER: '/queue/world'}, 'body': 'two\nlines'}
        frame = StompFrame(**message)
        self.assertEquals(message['headers'], frame.headers)
        self.assertEquals(dict(frame), message)
        self.assertEquals(str(frame), """\
SEND
destination:/queue/world

two
lines\x00""")
        self.assertEquals(eval(repr(frame)), frame)

    def test_frame_without_headers_and_body(self):
        message = {'command': 'DISCONNECT', 'headers': {}, 'body': ''}
        frame = StompFrame(**message)
        self.assertEquals(message['headers'], frame.headers)
        self.assertEquals(dict(frame), message)
        self.assertEquals(str(frame), """\
DISCONNECT

\x00""")
        self.assertEquals(eval(repr(frame)), frame)

    def test_encoding(self):
        key = u'fen\xeatre'
        value = u'\xbfqu\xe9 tal?, s\xfc\xdf'

        message = {'command': 'DISCONNECT', 'headers': {key: value}, 'body': ''}
        frame = StompFrame(**message)
        self.assertEquals(message['headers'], frame.headers)
        self.assertEquals(dict(frame), message)

        self.assertEquals(eval(repr(frame)), frame)
        frame.version = StompSpec.VERSION_1_1
        self.assertEquals(eval(repr(frame)), frame)
        self.assertEquals(str(frame), """\
DISCONNECT
fen\xc3\xaatre:\xc2\xbfqu\xc3\xa9 tal?, s\xc3\xbc\xc3\x9f

\x00""")

        frame.version = StompSpec.VERSION_1_0
        self.assertEquals(eval(repr(frame)), frame)
        self.assertRaises(UnicodeEncodeError, frame.__str__)

    def test_binary_body(self):
        body = binascii.a2b_hex('f0000a09')
        headers = {'content-length': str(len(body))}
        frame = StompFrame('MESSAGE', headers, body)
        self.assertEquals(frame.body, body)
        self.assertEquals(str(frame), 'MESSAGE\ncontent-length:4\n\n\xf0\x00\n\t\x00')

    def test_non_string_arguments(self):
        message = {'command': 0, 'headers': {123: 456}, 'body': 789}
        frame = StompFrame(**message)
        self.assertEquals(frame.command, '0')
        self.assertEquals(frame.headers, {123: 456})
        self.assertEquals(frame.body, '789')
        self.assertEquals(dict(frame), {'command': '0', 'headers': {123: 456}, 'body': '789'})
        self.assertEquals(str(frame), """\
0
123:456

789\x00""")
        self.assertEquals(eval(repr(frame)), frame)

if __name__ == '__main__':
    unittest.main()
