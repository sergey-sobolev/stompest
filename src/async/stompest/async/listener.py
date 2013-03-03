import time

from twisted.internet import defer, reactor

from stompest.error import StompConnectionError, StompCancelledError, \
    StompProtocolError
from stompest.protocol.spec import StompSpec

from .util import sendToErrorDestination
from stompest.async.util import WaitingDeferred

class Listener(object):
    # TODO: add more events to this interface

    def onConnect(self, connection, frame):
        pass

    def onConnected(self, connection, frame):
        pass

    def onConnectionLost(self, connection, reason):
        pass

    def onError(self, connection, frame):
        pass

    def onFrame(self, connection, frame):
        pass

    def onMessage(self, connection, frame, context):
        pass

    def onSend(self, connection, frame):
        pass

    def onSubscribe(self, connection, frame, context):
        pass

    def onUnsubscribe(self, connection, frame, context):
        pass

class ConnectListener(Listener):
    def __init__(self, connectedTimeout=None):
        self._connectedTimeout = connectedTimeout

    @defer.inlineCallbacks
    def onConnect(self, connection, frame): # @UnusedVariable
        self._waiting = WaitingDeferred()
        yield self._waiting.wait(self._connectedTimeout, StompCancelledError('STOMP broker did not answer on time [timeout=%s]' % self._connectedTimeout))

    def onConnected(self, connection, frame): # @UnusedVariable
        connection.remove(self)
        connection.add(ErrorListener())
        self._waiting.callback(None)

    def onConnectionLost(self, connection, reason):
        connection.remove(self)
        if not self._waiting.called:
            self._waiting.errback(reason)

    def onError(self, connection, frame):
        self.onConnectionLost(connection, StompProtocolError('While trying to connect, received %s' % frame.info()))

class ErrorListener(Listener):
    def onError(self, connection, frame):
        connection.disconnect(failure=StompProtocolError('Received %s' % frame.info()))

    def onConnectionLost(self, connection, reason): # @UnusedVariable
        connection.remove(self)

class SubscriptionListener(Listener):
    """This event handler corresponds to a STOMP subscription.
    
    :param handler: A callable :obj:`f(client, frame)` which accepts a :class:`~.async.client.Stomp` connection and the received :class:`~.StompFrame`.
    :param ack: Check this option if you wish to automatically ack **MESSAGE** frames after they were handled (successfully or not).
    :param errorDestination: If a frame was not handled successfully, forward a copy of the offending frame to this destination. Example: ``errorDestination='/queue/back-to-square-one'``
    :param onMessageFailed: You can specify a custom error handler which must be a callable with signature :obj:`f(connection, failure, frame, errorDestination)`. Note that a non-trivial choice of this error handler overrides the default behavior (forward frame to error destination and ack it).
    
    .. seealso :: The unit tests in the module :mod:`.tests.async_client_integration_test` cover a couple of usage scenarios.

    """
    DEFAULT_ACK_MODE = 'client-individual'

    def __init__(self, handler, ack=True, errorDestination=None, onMessageFailed=None):
        if not callable(handler):
            raise ValueError('Handler is not callable: %s' % handler)
        self._handler = handler
        self._ack = ack
        self._errorDestination = errorDestination
        self._onMessageFailed = onMessageFailed or sendToErrorDestination
        self._headers = None

    @defer.inlineCallbacks
    def onMessage(self, connection, frame, context):
        """onMessage(connection, frame, context)
        
        Handle a message originating from this listener's subscription."""
        if context is not self:
            return
        try:
            yield self._handler(connection, frame)
        except Exception as e:
            yield self._onMessageFailed(connection, e, frame, self._errorDestination)
        finally:
            if self._ack and (self._headers[StompSpec.ACK_HEADER] in StompSpec.CLIENT_ACK_MODES):
                connection.ack(frame)

    def onSubscribe(self, connection, frame, context): # @UnusedVariable
        """Set the **ack** header of the **SUBSCRIBE** frame initiating this listener's subscription to the value of the class atrribute :attr:`DEFAULT_ACK_MODE` (if it isn't set already). Keep a copy of the headers for handling messages originating from this subscription."""
        if context is not self:
            return
        frame.headers.setdefault(StompSpec.ACK_HEADER, self.DEFAULT_ACK_MODE)
        self._headers = frame.headers

    def onUnsubscribe(self, connection, frame, context): # @UnusedVariable
        """onUnsubscribe(connection, frame, context)
        
        Forget everything about this listener's subscription and unregister from the **connection**."""
        if context is not self:
            return
        self._headers = None
        connection.remove(self)

    def onConnectionLost(self, connection, reason): # @UnusedVariable
        """onConnectionLost(connection, reason)
        
        Forget everything about this listener's subscription and unregister from the **connection**."""
        self.onUnsubscribe(connection, None, self)

class HeartBeatListener(Listener):
    """Add this event handler to a :class:`~.async.client.Stomp` connection to automatically handle heart-beating.
    
    :param thresholds: tolerance thresholds (relative to the negotiated heart-beat periods). The default :obj:`None` is equivalent to the content of the class atrribute :attr:`DEFAULT_HEART_BEAT_THRESHOLDS`. Example: ``{'client': 0.6, 'server' 2.5}`` means that the client will send a heart-beat if it had shown no activity for 60 % of the negotiated client heart-beat period and that the client will disconnect if the server has shown no activity for 250 % of the negotiated server heart-beat period.

    **Example**:
    
    >>> client.add(HeartBeatListener())
    >>> client.connect(heartBeats=(250, 250))

    """
    DEFAULT_THRESHOLDS = {'client': 0.8, 'server': 2.0}

    def __init__(self, thresholds=None):
        self._thresholds = thresholds or self.DEFAULT_THRESHOLDS
        self._heartBeats = {}

    def onConnected(self, connection, frame): # @UnusedVariable
        self._beats(connection)

    def onConnectionLost(self, connection, reason): # @UnusedVariable
        self._beats(connection)

    def onFrame(self, connection, frame): # @UnusedVariable
        connection.session.received()

    def onSend(self, connection, frame): # @UnusedVariable
        connection.session.sent()

    def _beats(self, connection):
        for which in ('client', 'server'):
            self._beat(connection, which)

    def _beat(self, connection, which):
        try:
            self._heartBeats.pop(which).cancel()
        except:
            pass
        remaining = self._beatRemaining(connection.session, which)
        if remaining < 0:
            return
        if not remaining:
            if which == 'client':
                connection.sendFrame(connection.session.beat())
                remaining = self._beatRemaining(connection.session, which)
            else:
                connection.disconnect(failure=StompConnectionError('Server heart-beat timeout'))
                return
        self._heartBeats[which] = reactor.callLater(remaining, self._beat, connection, which) # @UndefinedVariable

    def _beatRemaining(self, session, which):
        heartBeat = {'client': session.clientHeartBeat, 'server': session.serverHeartBeat}[which]
        if not heartBeat:
            return -1
        last = {'client': session.lastSent, 'server': session.lastReceived}[which]
        elapsed = time.time() - last
        return max((self._thresholds[which] * heartBeat / 1000.0) - elapsed, 0)
