"""The asynchronous client is based on `Twisted <http://twistedmatrix.com/>`_, a very mature and powerful asynchronous programming framework. It supports destination specific message and error handlers (with default "poison pill" error handling), concurrent message processing, graceful shutdown, and connect and disconnect timeouts.

.. seealso:: `STOMP protocol specification <http://stomp.github.com/>`_, `Twisted API documentation <http://twistedmatrix.com/documents/current/api/>`_, `Apache ActiveMQ - Stomp <http://activemq.apache.org/stomp.html>`_

Examples
--------

.. automodule:: stompest.async.examples
    :members:

Producer
^^^^^^^^

.. literalinclude:: ../../src/async/stompest/async/examples/producer.py

Transformer
^^^^^^^^^^^

.. literalinclude:: ../../src/async/stompest/async/examples/transformer.py

Consumer
^^^^^^^^

.. literalinclude:: ../../src/async/stompest/async/examples/consumer.py

API
---
"""
import logging

from twisted.internet import defer, task

from stompest.error import StompCancelledError, StompConnectionError, StompFrameError
from stompest.protocol import StompSession, StompSpec
from stompest.util import checkattr

from .listener import ConnectListener, DisconnectListener
from .protocol import StompProtocolCreator
from .util import InFlightOperations, exclusive

LOG_CATEGORY = __name__

connected = checkattr('_protocol')

# TODO: is it ensured that the DISCONNECT frame is the last frame we send?

class Stomp(object):
    """An asynchronous STOMP client for the Twisted framework.

    :param config: A :class:`~.StompConfig` object.
    :param receiptTimeout: When a STOMP frame was sent to the broker and a **RECEIPT** frame was requested, this is the time (in seconds) to wait for the **RECEIPT** frame to arrive. If :obj:`None`, we will wait indefinitely.
    
    .. note :: All API methods which may request a **RECEIPT** frame from the broker -- which is indicated by the **receipt** parameter -- will wait for the **RECEIPT** response until this client's **receiptTimeout**. Here, "wait" is to be understood in the asynchronous sense that the method's :class:`twisted.internet.defer.Deferred` result will only call back then. If **receipt** is :obj:`None`, no such header is sent, and the callback will be triggered earlier.

    .. seealso :: :class:`~.StompConfig` for how to set configuration options, :class:`~.StompSession` for session state, :mod:`.protocol.commands` for all API options which are documented here.
    """
    _protocolCreatorFactory = StompProtocolCreator

    def __init__(self, config, receiptTimeout=None):
        self._config = config
        self._receiptTimeout = receiptTimeout

        self._session = StompSession(self._config.version, self._config.check)
        self._protocol = None
        self._protocolCreator = self._protocolCreatorFactory(self._config.uri)

        self.log = logging.getLogger(LOG_CATEGORY)

        self._disconnecting = False

        # keep track of active handlers for graceful disconnect
        self._messages = InFlightOperations('Handler for message')
        self._receipts = InFlightOperations('Waiting for receipt')

        self._handlers = {
            'MESSAGE': self._onMessage,
            'CONNECTED': self._onConnected,
            'ERROR': self._onError,
            'RECEIPT': self._onReceipt,
        }

        self._listeners = []

    def add(self, listener):
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove(self, listener):
        self._listeners.remove(listener)

    @property
    def disconnected(self):
        """This :class:`twisted.internet.defer.Deferred` calls back when the connection to the broker was lost. It will err back when the connection loss was unexpected or caused by another error.
        """
        return self._disconnected

    @property
    def session(self):
        """The :class:`~.StompSession` associated to this client.
        """
        return self._session

    def sendFrame(self, frame):
        """Send a raw STOMP frame.

        .. note :: If we are not connected, this method, and all other API commands for sending STOMP frames except :meth:`~.async.client.Stomp.connect`, will raise a :class:`~.StompConnectionError`. Use this command only if you have to bypass the :class:`~.StompSession` logic and you know what you're doing!
        """
        for listener in list(self._listeners):
            listener.onSend(self, frame)
        self._protocol.send(frame)

    #
    # STOMP commands
    #
    @exclusive
    @defer.inlineCallbacks
    def connect(self, headers=None, versions=None, host=None, heartBeats=None, connectTimeout=None, connectedTimeout=None):
        """connect(headers=None, versions=None, host=None, heartBeats=None, connectTimeout=None, connectedTimeout=None)

        Establish a connection to a STOMP broker. If the wire-level connect fails, attempt a failover according to the settings in the client's :class:`~.StompConfig` object. If there are active subscriptions in the :attr:`~.async.client.Stomp.session`, replay them when the STOMP connection is established. This method returns a :class:`twisted.internet.defer.Deferred` object which calls back with :obj:`self` when the STOMP connection has been established and all subscriptions (if any) were replayed. In case of an error, it will err back with the reason of the failure.

        :param versions: The STOMP protocol versions we wish to support. The default behavior (:obj:`None`) is the same as for the :func:`~.commands.connect` function of the commands API, but the highest supported version will be the one you specified in the :class:`~.StompConfig` object. The version which is valid for the connection about to be initiated will be stored in the :attr:`~.async.client.Stomp.session`.
        :param connectTimeout: This is the time (in seconds) to wait for the wire-level connection to be established. If :obj:`None`, we will wait indefinitely.
        :param connectedTimeout: This is the time (in seconds) to wait for the STOMP connection to be established (that is, the broker's **CONNECTED** frame to arrive). If :obj:`None`, we will wait indefinitely.

        .. note :: Only one connect attempt may be pending at a time. Any other attempt will result in a :class:`~.StompAlreadyRunningError`.

        .. seealso :: The :mod:`.protocol.failover` and :mod:`~.protocol.session` modules for the details of subscription replay and failover transport.
        """
        frame = self.session.connect(self._config.login, self._config.passcode, headers, versions, host, heartBeats)

        try:
            self._protocol
        except:
            pass
        else:
            raise StompConnectionError('Already connected')

        try:
            self._protocol = yield self._protocolCreator.connect(connectTimeout, self._onFrame, self._onConnectionLost)
        except Exception as e:
            self.log.error('Endpoint connect failed')
            raise

        # disconnect listener must be added first (it must handle connect errors)
        self.add(DisconnectListener()) # TODO: pass DisconnectListener parameter to self.connect()
        self.add(ConnectListener(connectedTimeout)) # TODO: pass ConnectListener parameter to self.connect()
        try:
            self.sendFrame(frame)
            for listener in list(self._listeners):
                yield listener.onConnect(self, frame)
        except Exception as e:
            yield self.disconnect(failure=e)
            yield self.disconnected

        self._replay()

        defer.returnValue(self)

    @connected
    @defer.inlineCallbacks
    def disconnect(self, receipt=None, failure=None, timeout=None):
        """disconnect(self, receipt=None, failure=None, timeout=None)
        
        Send a **DISCONNECT** frame and terminate the STOMP connection.

        :param failure: A disconnect reason (a :class:`Exception`) to err back. Example: ``versions=['1.0', '1.1']``
        :param timeout: This is the time (in seconds) to wait for a graceful disconnect, that is, for pending message handlers to complete. If receipt is :obj:`None`, we will wait indefinitely.

        .. note :: The :attr:`~.async.client.Stomp.session`'s active subscriptions will be cleared if no failure has been passed to this method. This allows you to replay the subscriptions upon reconnect. If you do not wish to do so, you have to clear the subscriptions yourself by calling the :meth:`~.StompSession.close` method of the :attr:`~.async.client.Stomp.session`. Only one disconnect attempt may be pending at a time. Any other attempt will result in a :class:`~.StompAlreadyRunningError`. The result of any (user-requested or not) disconnect event is available via the :attr:`disconnected` property.
        """
        for listener in list(self._listeners):
            yield listener.onDisconnect(self, failure, timeout)
        protocol = self._protocol
        try:
            # notify that we are ready to disconnect after outstanding messages are ack'ed
            if self._messages:
                self.log.info('Waiting for outstanding message handlers to finish ... [timeout=%s]' % timeout)
                try:
                    yield task.cooperate(iter([handler.wait(timeout, StompCancelledError('Going down to disconnect now')) for handler in self._messages.values()])).whenDone()
                except StompCancelledError as e:
                    self._disconnectReason = StompCancelledError('Handlers did not finish in time.')
                else:
                    self.log.info('All handlers complete. Resuming disconnect ...')

            if self.session.state == self.session.CONNECTED:
                frame = self.session.disconnect(receipt)
                try:
                    self.sendFrame(frame)
                except Exception as e:
                    self._disconnectReason = StompConnectionError('Could not send %s. [%s]' % (frame.info(), e))

                try:
                    yield self._waitForReceipt(receipt)
                except StompCancelledError:
                    self._disconnectReason = StompCancelledError('Receipt for disconnect command did not arrive on time.')
        except Exception as e:
            self._disconnectReason = e
        finally:
            protocol.loseConnection()

    @connected
    @defer.inlineCallbacks
    def send(self, destination, body='', headers=None, receipt=None):
        """send(destination, body='', headers=None, receipt=None)

        Send a **SEND** frame.
        """
        frame = self.session.send(destination, body, headers, receipt)
        self.sendFrame(frame)
        yield self._waitForReceipt(receipt)

    @connected
    @defer.inlineCallbacks
    def ack(self, frame, receipt=None):
        """ack(frame, receipt=None)

        Send an **ACK** frame for a received **MESSAGE** frame.
        """
        frame = self.session.ack(frame, receipt)
        self.sendFrame(frame)
        yield self._waitForReceipt(receipt)

    @connected
    @defer.inlineCallbacks
    def nack(self, frame, receipt=None):
        """nack(frame, receipt=None)

        Send a **NACK** frame for a received **MESSAGE** frame.
        """
        frame = self.session.nack(frame, receipt)
        self.sendFrame(frame)
        yield self._waitForReceipt(receipt)

    @connected
    @defer.inlineCallbacks
    def begin(self, transaction=None, receipt=None):
        """begin(transaction=None, receipt=None)

        Send a **BEGIN** frame to begin a STOMP transaction.
        """
        frame = self.session.begin(transaction, receipt)
        self.sendFrame(frame)
        yield self._waitForReceipt(receipt)

    @connected
    @defer.inlineCallbacks
    def abort(self, transaction=None, receipt=None):
        """abort(transaction=None, receipt=None)

        Send an **ABORT** frame to abort a STOMP transaction.
        """
        frame = self.session.abort(transaction, receipt)
        self.sendFrame(frame)
        yield self._waitForReceipt(receipt)

    @connected
    @defer.inlineCallbacks
    def commit(self, transaction=None, receipt=None):
        """commit(transaction=None, receipt=None)

        Send a **COMMIT** frame to commit a STOMP transaction.
        """
        frame = self.session.commit(transaction, receipt)
        self.sendFrame(frame)
        yield self._waitForReceipt(receipt)

    @connected
    @defer.inlineCallbacks
    def subscribe(self, destination, headers=None, receipt=None, listener=None):
        """subscribe(destination, headers=None, receipt=None, listener=None)

        :param listener: An optional :class:`~.Listener` object which will be added to this connection to handle events associated to this subscription.
        
        Send a **SUBSCRIBE** frame to subscribe to a STOMP destination. This method returns a :class:`twisted.internet.defer.Deferred` object which will fire with a token when a possibly requested **RECEIPT** frame has arrived. The callback value is a token which is used internally to match incoming **MESSAGE** frames and must be kept if you wish to :meth:`~.async.client.Stomp.unsubscribe` later.
        """
        frame, token = self.session.subscribe(destination, headers, receipt, listener)
        if listener:
            self.add(listener)
        for listener in list(self._listeners):
            listener.onSubscribe(self, frame, listener)
        self.sendFrame(frame)
        yield self._waitForReceipt(receipt)
        defer.returnValue(token)

    @connected
    @defer.inlineCallbacks
    def unsubscribe(self, token, receipt=None):
        """unsubscribe(token, receipt=None)

        Send an **UNSUBSCRIBE** frame to terminate an existing subscription.

        :param token: The result of the :meth:`~.async.client.Stomp.subscribe` command which initiated the subscription in question.
        """
        context = self.session.subscription(token)
        frame = self.session.unsubscribe(token, receipt)
        for listener in list(self._listeners):
            listener.onUnsubscribe(self, frame, context)
        self.sendFrame(frame)
        yield self._waitForReceipt(receipt)

    #
    # callbacks for received STOMP frames
    #
    @defer.inlineCallbacks
    def _onFrame(self, frame):
        for listener in list(self._listeners):
            yield listener.onFrame(self, frame)
        if not frame:
            return
        try:
            handler = self._handlers[frame.command]
        except KeyError:
            raise StompFrameError('Unknown STOMP command: %s' % repr(frame))
        yield handler(frame)

    @defer.inlineCallbacks
    def _onConnected(self, frame):
        self.session.connected(frame)
        self.log.info('Connected to stomp broker [session=%s, version=%s]' % (self.session.id, self.session.version))
        self._protocol.setVersion(self.session.version)
        for listener in list(self._listeners):
            yield listener.onConnected(self, frame)

    @defer.inlineCallbacks
    def _onError(self, frame):
        for listener in list(self._listeners):
            yield listener.onError(self, frame)

    @defer.inlineCallbacks
    def _onMessage(self, frame):
        headers = frame.headers
        messageId = headers[StompSpec.MESSAGE_ID_HEADER]

        try:
            token = self.session.message(frame)
        except:
            self.log.error('[%s] Ignoring message (no handler found): %s' % (messageId, frame.info()))
            defer.returnValue(None)
        context = self.session.subscription(token)

        with self._messages(messageId, self.log):
            try:
                for listener in list(self._listeners):
                    yield listener.onMessage(self, frame, context)
            except Exception as e:
                self.disconnect(failure=e)

    def _onReceipt(self, frame):
        receipt = self.session.receipt(frame)
        self._receipts[receipt].callback(None)

    #
    # private properties
    #
    @property
    def _protocol(self):
        protocol = self.__protocol
        if not protocol:
            raise StompConnectionError('Not connected')
        return protocol

    @_protocol.setter
    def _protocol(self, protocol):
        self.__protocol = protocol

    @property
    def _disconnectReason(self):
        return self.__disconnectReason

    @_disconnectReason.setter
    def _disconnectReason(self, reason):
        if reason:
            self.log.error(str(reason))
            reason = self._disconnectReason or reason # existing reason wins
        self.__disconnectReason = reason

    #
    # private helpers
    #

    def _onConnectionLost(self, reason):
        self._protocol = None
        for operations in (self._messages, self._receipts):
            for waiting in operations.values():
                if not waiting.called:
                    waiting.errback(StompCancelledError('In-flight operation cancelled (connection lost)'))
                    waiting.addErrback(lambda _: None)
        for listener in list(self._listeners):
            listener.onConnectionLost(self, reason)

    def _replay(self):
        for (destination, headers, receipt, context) in self.session.replay():
            self.log.info('Replaying subscription: %s' % headers)
            self.subscribe(destination, headers=headers, receipt=receipt, listener=context)

    @defer.inlineCallbacks
    def _waitForReceipt(self, receipt):
        if receipt is None:
            defer.returnValue(None)
        with self._receipts(receipt, self.log) as receiptArrived:
            timeout = self._receiptTimeout
            yield receiptArrived.wait(timeout, StompCancelledError('Receipt did not arrive on time: %s [timeout=%s]' % (receipt, timeout)))

