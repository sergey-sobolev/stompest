import sys

try:
    import unittest.mock as mock
except ImportError:
    import mock

_IS_PYTHON_2 = sys.version_info[0] == 2

def makeCharacter(byte):
    return byte if _IS_PYTHON_2 else chr(byte)

def makeBytes(bytestring):
    return bytestring if _IS_PYTHON_2 else bytes(ord(c) for c in bytestring)

def makeBytesFromSequence(sequence):
    return b''.join(sequence) if _IS_PYTHON_2 else bytes(sequence)

def nextMethod(iterator):
    return getattr(iterator, 'next' if _IS_PYTHON_2 else '__next__')

toText = unicode if _IS_PYTHON_2 else str # @UndefinedVariable
