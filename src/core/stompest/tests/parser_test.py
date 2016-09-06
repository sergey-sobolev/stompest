from __future__ import unicode_literals

import binascii
import unittest

from stompest._backwards import binaryType
from stompest.error import StompFrameError
from stompest.protocol import commands, StompFrame, StompParser, StompSpec
from stompest.protocol.frame import StompHeartBeat

class StompParserTest(unittest.TestCase):
    def _generate_bytes(self, stream):
        for byte in stream:
            yield byte

    def test_frame_parse_succeeds(self):
        frame = StompFrame(
            StompSpec.SEND,
            {'foo': 'bar', 'hello ': 'there-world with space ', 'empty-value':'', '':'empty-header', StompSpec.DESTINATION_HEADER: '/queue/blah'},
            b'some stuff\nand more'
        )

        parser = StompParser()
        parser.add(binaryType(frame))
        self.assertEqual(parser.get(), frame)
        self.assertEqual(parser.get(), None)

    def test_duplicate_headers(self):
        command = StompSpec.SEND
        rawFrame = '%s\nfoo:bar1\nfoo:bar2\n\nsome stuff\nand more\x00' % (command,)

        parser = StompParser()
        parser.add(rawFrame.encode())
        parsedFrame = parser.get()
        self.assertEqual(parser.get(), None)

        self.assertEqual(parsedFrame.command, command)
        self.assertEqual(parsedFrame.headers, {'foo': 'bar1'})
        self.assertEqual(parsedFrame.rawHeaders, [('foo', 'bar1'), ('foo', 'bar2')])
        self.assertEqual(parsedFrame.body, b'some stuff\nand more')

    def test_invalid_command(self):
        messages = [b'RECEIPT\nreceipt-id:message-12345\n\n\x00', b'NACK\nsubscription:0\nmessage-id:007\n\n\x00']
        parser = StompParser('1.0')
        parser.add(messages[0])
        self.assertRaises(StompFrameError, parser.add, messages[1])
        self.assertEqual(parser.get(), StompFrame(StompSpec.RECEIPT, rawHeaders=(('receipt-id', 'message-12345'),)))
        self.assertFalse(parser.canRead())
        self.assertEqual(parser.get(), None)
        parser = StompParser('1.1')
        parser.add(messages[1])
        self.assertEqual(parser.get(), StompFrame(command='NACK', rawHeaders=(('subscription', '0'), ('message-id', '007'))))

    def test_reset_succeeds(self):
        frame = StompFrame(
            command=StompSpec.SEND,
            headers={'foo': 'bar', 'hello ': 'there-world with space ', 'empty-value':'', '':'empty-header', StompSpec.DESTINATION_HEADER: '/queue/blah'},
            body=b'some stuff\nand more'
        )
        parser = StompParser()

        parser.add(binaryType(frame))
        parser.reset()
        self.assertEqual(parser.get(), None)
        parser.add(binaryType(frame)[:20])
        self.assertEqual(parser.get(), None)

    def test_frame_without_header_or_body_succeeds(self):
        parser = StompParser()
        parser.add(commands.disconnect().__str__())
        self.assertEqual(parser.get(), commands.disconnect())

    def test_frames_with_optional_newlines_succeeds(self):
        parser = StompParser()
        disconnect = commands.disconnect()
        frame = b'\n' + binaryType(disconnect) + b'\n'
        parser.add(2 * frame)
        for _ in range(2):
            self.assertEqual(parser.get(), disconnect)
        self.assertEqual(parser.get(), None)

    def test_frames_with_heart_beats_succeeds(self):
        parser = StompParser(version=StompSpec.VERSION_1_1)
        disconnect = commands.disconnect()
        frame = b'\n' + binaryType(disconnect) + b'\n'
        parser.add(2 * frame)
        frames = []
        while parser.canRead():
            frames.append(parser.get())
        self.assertEqual(frames, [StompHeartBeat(), disconnect, StompHeartBeat(), StompHeartBeat(), disconnect, StompHeartBeat()])

        self.assertEqual(parser.get(), None)

    def test_get_returns_None_if_not_done(self):
        parser = StompParser()
        self.assertEqual(None, parser.get())
        parser.add(StompSpec.CONNECT.encode())
        self.assertEqual(None, parser.get())

    def test_add_throws_FrameError_on_invalid_command(self):
        parser = StompParser()

        self.assertRaises(StompFrameError, parser.add, b'HELLO\n')
        self.assertFalse(parser.canRead())
        parser.add(('%s\n\n\x00' % StompSpec.DISCONNECT).encode())
        self.assertEqual(StompFrame(StompSpec.DISCONNECT), parser.get())
        self.assertFalse(parser.canRead())

    def test_add_throws_FrameError_on_header_line_missing_separator(self):
        parser = StompParser()
        parser.add(('%s\n' % StompSpec.SEND).encode('utf-8'))
        self.assertRaises(StompFrameError, parser.add, b'no separator\n')

    def test_colon_in_header_value(self):
        parser = StompParser()
        parser.add(('%s\nheader:with:colon\n\n\x00' % StompSpec.DISCONNECT).encode())
        self.assertEqual(parser.get().headers['header'], 'with:colon')

    def test_no_newline(self):
        headers = {'x': 'y'}
        body = b'testing 1 2 3'
        frameBytes = StompFrame(StompSpec.MESSAGE, headers, body).__str__()
        self.assertTrue(frameBytes.endswith(b'\x00'))
        parser = StompParser()
        parser.add(self._generate_bytes(frameBytes))
        frame = parser.get()
        self.assertEqual(StompSpec.MESSAGE, frame.command)
        self.assertEqual(headers, frame.headers)
        self.assertEqual(body, frame.body)
        self.assertEqual(parser.get(), None)

    def test_binary_body(self):
        body = binascii.a2b_hex('f0000a09')
        headers = {'content-length': str(len(body))}
        frameBytes = StompFrame(StompSpec.MESSAGE, headers, body).__str__()
        self.assertTrue(frameBytes.endswith(b'\x00'))
        parser = StompParser()
        parser.add(frameBytes)
        frame = parser.get()
        self.assertEqual(StompSpec.MESSAGE, frame.command)
        self.assertEqual(headers, frame.headers)
        self.assertEqual(body, frame.body)

        self.assertEqual(parser.get(), None)

    def test_body_allowed_commands(self):
        head = commands.disconnect().__str__().rstrip(StompSpec.FRAME_DELIMITER.encode())
        for (version, bodyAllowed) in [
            (StompSpec.VERSION_1_0, True),
            (StompSpec.VERSION_1_1, False),
            (StompSpec.VERSION_1_2, False)
        ]:
            parser = StompParser(version)
            parser.add(head)
            parser.add(b'ouch!')
            try:
                parser.add(StompSpec.FRAME_DELIMITER.encode())
            except StompFrameError:
                if bodyAllowed:
                    raise
            except:
                raise
            else:
                if not bodyAllowed:
                    raise

    def test_strip_line_delimiter(self):
        queue = '/queue/test'
        frame = commands.send(queue)
        rawFrameReplaced = commands.send(queue).__str__().replace(b'\n', b'\r\n')
        for (version, replace) in [
            (StompSpec.VERSION_1_0, False),
            (StompSpec.VERSION_1_1, False),
            (StompSpec.VERSION_1_2, True)
        ]:
            if replace:
                parser = StompParser(version)
                parser.add(rawFrameReplaced)
                self.assertEqual(parser.get(), frame)
            else:
                self.assertRaises(StompFrameError, StompParser(version).add, rawFrameReplaced)
        textWithCarriageReturn = 'there\rfolks'
        frame = commands.send(queue, headers={'hi': textWithCarriageReturn})
        parser = StompParser(StompSpec.VERSION_1_2)
        parser.add(binaryType(frame))
        self.assertEqual(parser.get().headers['hi'], textWithCarriageReturn)

    def test_add_multiple_frames_per_read(self):
        body1 = b'boo'
        body2 = b'hoo'
        headers = {'x': 'y'}
        frameBytes = StompFrame(StompSpec.MESSAGE, headers, body1).__str__() + StompFrame(StompSpec.MESSAGE, headers, body2).__str__()
        parser = StompParser()
        parser.add(frameBytes)

        frame = parser.get()
        self.assertEqual(StompSpec.MESSAGE, frame.command)
        self.assertEqual(headers, frame.headers)
        self.assertEqual(body1, frame.body)

        frame = parser.get()
        self.assertEqual(StompSpec.MESSAGE, frame.command)
        self.assertEqual(headers, frame.headers)
        self.assertEqual(body2, frame.body)

        self.assertEqual(parser.get(), None)

    def test_decode(self):
        key = b'fen\xc3\xaatre'.decode('utf-8')
        value = b'\xc2\xbfqu\xc3\xa9 tal?'.decode('utf-8')
        headers = {key: value}
        frameBytes = StompFrame(command=StompSpec.DISCONNECT, headers=headers, version=StompSpec.VERSION_1_1).__str__()

        parser = StompParser(version=StompSpec.VERSION_1_1)
        parser.add(frameBytes)
        frame = parser.get()
        self.assertEqual(frame.headers, headers)

        parser = StompParser(version=StompSpec.VERSION_1_0)
        self.assertRaises(UnicodeDecodeError, parser.add, frameBytes)

    def test_unescape(self):
        frameBytes = ("""%s
\\n\\\\:\\c\t\\n

\x00""" % StompSpec.DISCONNECT).encode()

        for version in (StompSpec.VERSION_1_1, StompSpec.VERSION_1_2):
            parser = StompParser(version=version)
            parser.add(frameBytes)
            frame = parser.get()
            self.assertEqual(frame.headers, {'\n\\': ':\t\n'})

        parser = StompParser(version=StompSpec.VERSION_1_0)
        parser.add(frameBytes)
        frame = parser.get()
        self.assertEqual(frame.headers, {'\\n\\\\': '\\c\t\\n'})

        frameBytes = ("""%s
\\n\\\\:\\c\\t

\x00""" % StompSpec.DISCONNECT).encode()

        for version in (StompSpec.VERSION_1_1, StompSpec.VERSION_1_2):
            self.assertRaises(StompFrameError, StompParser(version=version).add, frameBytes)

        parser = StompParser(version=StompSpec.VERSION_1_0)
        parser.add(frameBytes)
        frame = parser.get()
        self.assertEqual(frame.headers, {'\\n\\\\': '\\c\\t'})

        frameBytes = ("""%s
\\n\\\\:\\c\t\\r

\x00""" % StompSpec.DISCONNECT).encode()

        parser = StompParser(version=StompSpec.VERSION_1_2)
        parser.add(frameBytes)
        frame = parser.get()
        self.assertEqual(frame.headers, {'\n\\': ':\t\r'})

    def test_keep_first_of_repeated_headers(self):
        parser = StompParser()
        parser.add(("""
%s
repeat:1
repeat:2

\x00""" % StompSpec.CONNECT).encode())
        frame = parser.get()
        self.assertEqual(frame.headers['repeat'], '1')

if __name__ == '__main__':
    unittest.main()
