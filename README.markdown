stomp, stomper, stompest!
=========================

stompest is a full-featured [STOMP](http://stomp.github.com/) [1.0](http://stomp.github.com//stomp-specification-1.0.html) and [1.1](http://stomp.github.com//stomp-specification-1.1.html) implementation for Python including both synchronous and asynchronous clients:

* The `sync.Stomp` client is dead simple. It does not assume anything about your concurrency model (thread vs process) or force you to use it any particular way. It gets out of your way and lets you do what you want.
* The `async.Stomp` client is based on [Twisted](http://twistedmatrix.com/), a very mature and powerful asynchronous programming framework. It supports destination specific message and error handlers (with default "poison pill" error handling), concurrent message processing, graceful shutdown, and connect and disconnect timeouts.

Both clients make use of a generic set of components in the `protocol` module each of which can be used independently to roll your own STOMP client:

* a wire-level STOMP frame parser `protocol.StompParser` and compiler `protocol.StompFrame`,

* a faithful implementation of the syntax of the STOMP 1.0 and 1.1 protocols with a simple stateless function API in the `protocol.commands` module,

* a generic implementation of the STOMP 1.0 and 1.1 session state semantics in `protocol.StompSession`, such as protocol version negotiation at connect time, transaction and subscription handling (including a generic subscription replay scheme which may be used to reconstruct the session's subscription state after a forced disconnect),

* and `protocol.StompFailoverTransport`, a [failover transport](http://activemq.apache.org/failover-transport-reference.html) URI scheme akin to the one used in ActiveMQ.

This module is thoroughly unit tested and (in version 1.x) production hardened for the functionality used by [Mozes](http://www.mozes.com/) --- persistent queueing on [ActiveMQ](http://activemq.apache.org/). Minor enhancements may be required to use this STOMP adapter with other brokers.

The current maintainer also deploys stompest in serious production environments. The substantially redesigned stompest 2 is probably even better tested but should be considered (mature) alpha: Some features to come (in particular heartbeating and STOMP 1.2) may still require minor changes of the API. 

Documentation & Code Examples
=============================
The stompest API is fully documented [here](http://nikipore.github.com/stompest/).

Features
========

Commands layer
--------------
* Transport and client agnostic.
* Full-featured implementation of all STOMP 1.0 and 1.1 client commands.
* Client-side handling of STOMP 1.0 and 1.1 commands received from the broker.
* Stateless and simple function API.

Session layer
-------------
* Manages the state of a connection.
* Replays subscriptions upon reconnect.
* Not yet fully client agnostic (currently only works on top of the simple client; support for the Twisted client is planned).
* Heartbeat handling (not yet implemented).

Failover layer
--------------
* Mimics the [failover transport](http://activemq.apache.org/failover-transport-reference.html) behavior of the native ActiveMQ Java client.
* Produces a (possibly infinite) sequence of broker network addresses and connect delay times.

Parser layer
------------
* Abstract frame definition.
* Transformation between these abstract frames and a wire-level byte stream of STOMP frames.

Clients
=======

`sync`
------
* Built on top of the abstract layers, the synchronous client adds a TCP connection and a synchronous API.
* The concurrency scheme (synchronous, threaded, ...) is free to choose by the user.

`async`
-------
* Based on the Twisted asynchronous framework.
* Fully unit-tested including a simulated STOMP broker.
* Graceful shutdown: on disconnect or error, the client stops processing new messages and waits for all outstanding message handlers to finish before issuing the `DISCONNECT` command.
* Error handling - fully customizable on a per-subscription level:
    * Disconnect: if you do not configure an errorDestination and an exception propagates up from a message handler, then the client will gracefully disconnect. This is effectively a `NACK` for the message (actually, disconnecting is the only way to `NACK` in STOMP 1.0). You can [configure ActiveMQ](http://activemq.apache.org/message-redelivery-and-dlq-handling.html) with a redelivery policy to avoid the "poison pill" scenario where the broker keeps redelivering a bad message infinitely.
    * Default error handling: passing an error destination parameter at subscription time will cause unhandled messages to be forwarded to that destination and then `ACK`ed.
    * Custom hook: you can override the default behavior with any customized error handling scheme.
* Separately configurable timeouts for wire-level connection, the broker's `CONNECTED` reply frame, and graceful disconnect (in-flight handlers that do not finish in time).

Acknowledgements
================
* Version 1.x of stompest was written by [Roger Hoover (@theduderog)](http://github.com/theduderog) at [Mozes](http://www.mozes.com/) and deployed in their production environment.
* Kudos to [Oisin Mulvihill](https://github.com/oisinmulvihill), the developer of [stomper] (http://code.google.com/p/stomper/)! His idea of an abstract representation of the STOMP protocol lives on in stompest.

Caveats
=======
* Requires Python 2.6 or higher. Not yet tested with Python 3.x.
* This module is thoroughly unit tested and (in version 1.x) production hardened for the functionality used by the current maintainer and [Mozes](http://www.mozes.com/) --- persistent queueing on [ActiveMQ](http://activemq.apache.org/). It is also planned to make the integration tests pass against [RabbitMQ](http://www.rabbitmq.com/) and [Apollo](http://activemq.apache.org/apollo/). Minor enhancements may be required to use this STOMP adapter with other brokers. The substantially redesigned stompest 2 is probably even better tested but should be considered (mature) alpha: Some features to come (in particular heartbeating and STOMP 1.2) may still require minor changes of the API.

To Do
=====
* `async` client only: heartbeating.
* The URI scheme supports only TCP, no SSL (the authors don't need it because the client is run in "safe" production environments). For the `async` client, however, it should be straightforward to enhance the URI scheme by means of the [Endpoint API](http://twistedmatrix.com/documents/current/api/twisted.internet.endpoints.html). Contributions are welcome!
* [STOMP 1.2 protocol](http://stomp.github.com/stomp-specification-1.2.html) (not before there is a reference broker implementation available).

Changes
=======
* 1.0.4 - Bug fix thanks to [Njal Karevoll](https://github.com/nkvoll).  No longer relies on newline after the null-byte frame separator.  Library is now compatible with RabbitMQ stomp adapter.
* 1.1.1 - Thanks to [nikipore](https://github.com/nikipore) for adding support for binary messages.
* 1.1.2 - Fixed issue with stomper adding a space in ACK message-id header. ActiveMQ 5.6.0 no longer tolerates this.
* 2.0a1 - Complete redesign: feature-complete implementation of STOMP 1.0 and 1.1 (except heartbeating). Broker failover. Decoupled from [stomper](http://code.google.com/p/stomper/).