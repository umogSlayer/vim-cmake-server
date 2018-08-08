# -*- coding: utf-8 -*-
from collections import namedtuple

__MESSAGE_PROLOG = """[== "CMake Server" ==["""
__MESSAGE_EPILOG = """]== "CMake Server" ==]"""


class InvalidMessageError(Exception):
    pass


class UnexpectedEOFError(Exception):
    pass


class UnsupportedProtocolVersion(Exception):
    pass


class RequestAlreadySentError(Exception):
    pass


class MessageErrorResponse(Exception):
    pass


class DeserializationResult(object):
    __slots__ = ("read_chars", "message_found", "message_object", "reason")

    def __init__(self, read_chars=0, message_found=False, message_object=dict(), reason=""):
        self.read_chars = read_chars
        self.message_found = message_found
        self.message_object = message_object
        self.reason = reason


SupportedVersion = namedtuple('SupportedVersion', ['isExperimental', 'major', 'minor'])
HelloMessage = namedtuple('HelloMessage', ['supported_versions'])


def serialize_message(message):
    import json
    assert isinstance(message, dict)
    json_contents_string = json.dumps(message, ensure_ascii=False)
    return (__MESSAGE_PROLOG + "\r\n" + json_contents_string + "\r\n" + __MESSAGE_EPILOG + "\r\n").encode("utf-8")


def deserialize_message(message):
    assert isinstance(message, str)
    message_prolog_start = message.find(__MESSAGE_PROLOG)
    message_epilog_start = message.find(__MESSAGE_EPILOG)
    if message_prolog_start < 0:
        return DeserializationResult(message_found=False,
                                     reason="message prolog not found")
    if message_epilog_start < 0:
        return DeserializationResult(read_chars=message_prolog_start,
                                     message_found=False,
                                     reason="message epilog not found")

    message_body = message[message_prolog_start + len(__MESSAGE_PROLOG):message_epilog_start]
    from json import loads
    message_object = loads(message_body)
    assert isinstance(message_object, dict)
    return DeserializationResult(message_found=True,
                                 read_chars=message_epilog_start + len(__MESSAGE_EPILOG),
                                 message_object=message_object)


class CMakeServerMessagesIterator(object):
    __slots__ = ("stream_reader", "event_to_signal", "internal_buffer")

    def __init__(self, stream_reader, event_to_signal):
        import asyncio
        self.stream_reader = stream_reader
        assert isinstance(self.stream_reader, asyncio.StreamReader)
        self.event_to_signal = event_to_signal
        assert isinstance(self.event_to_signal, asyncio.Event)
        self.internal_buffer = ""

    def __aiter__(self):
        return self

    async def __anext__(self):
        message_complete = False
        while not message_complete:
            if self.stream_reader.at_eof():
                raise StopAsyncIteration
            bytes_read = await self.stream_reader.readline()
            if self.event_to_signal is not None:
                self.event_to_signal.set()
            self.internal_buffer += bytes_read.decode("utf-8")
            deserialization_result = deserialize_message(self.internal_buffer)
            message_complete = deserialization_result.message_found

        self.internal_buffer = str(self.internal_buffer[deserialization_result.read_chars:])
        return deserialization_result.message_object


async def read_hello_message(messages_iterator):
    try:
        message_content = await messages_iterator.__anext__()
    except StopAsyncIteration:
        raise UnexpectedEOFError("End of stream when reading \"hello\" message")
    if message_content['type'] != 'hello':
        raise InvalidMessageError("Invalid message type")
    supported_versions = [SupportedVersion(**supported_protocol)
                          for supported_protocol in message_content['supportedProtocolVersions']]
    return HelloMessage(supported_versions=supported_versions)


RegisteredRequestKeyBase = namedtuple("RegisteredRequestKey", ["type", "cookie"])


class RegisteredRequestKey(RegisteredRequestKeyBase):
    def __hash__(self):
        return hash(self.type) + hash(self.cookie)


RegisteredRequestValue = namedtuple("RegisteredRequestValue", ["success_cb", "failure_cb", "progress_cb", "message_cb"])


class ResponseMessageIterator(object):
    def __init__(self, loop_object):
        import asyncio
        self.message_event = asyncio.Event(loop=loop_object)
        self.messages = []
        self.response_received = False
        self.error_received = False

    def success_cb(self, message):
        self.messages.append(message)
        self.message_event.set()
        self.response_received = True

    def failure_cb(self, message):
        self.messages.append(message)
        self.message_event.set()
        self.error_received = True

    def other_cb(self, message):
        self.messages.append(message)
        self.message_event.set()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages and \
                (self.response_received or self.error_received):
            raise StopAsyncIteration
        if not self.messages:
            self.message_event.clear()
            await self.message_event.wait()
        assert self.messages
        return self.messages.pop(0)


class CMakeServer(object):
    import logging
    logger = logging.getLogger("CMakeServer")

    def __init__(self, loop_object, signal_cb):
        import asyncio
        self.loop_object = loop_object
        self.input_message_reader = asyncio.StreamReader(loop=self.loop_object)
        self.message_data_processed_event = asyncio.Event(loop=self.loop_object)
        self.loop_object.create_task(self._message_loop())
        self.registered_requests = dict()
        self.signal_cb = signal_cb

    def _form_and_register_cmake_server_request(self, request_object, success_cb, failure_cb, progress_cb, message_cb):
        request_type = request_object["type"]
        request_cookie = request_object.get("cookie", "")
        key = RegisteredRequestKey(type=request_type, cookie=request_cookie)
        if key in self.registered_requests:
            raise RequestAlreadySentError("Request (type=%s, cookie=%s) is already registered"
                                          % (request_type, request_cookie))
        self.registered_requests[key] = RegisteredRequestValue(success_cb=success_cb,
                                                               failure_cb=failure_cb,
                                                               progress_cb=progress_cb,
                                                               message_cb=message_cb)
        return serialize_message(request_object)

    async def _message_loop(self):
        import logging
        cmake_messages_iterator = CMakeServerMessagesIterator(self.input_message_reader,
                                                              self.message_data_processed_event)
        hello_message = await read_hello_message(cmake_messages_iterator)
        CMakeServer.logger.log(logging.DEBUG, "CMake server hello message: %s" % repr(hello_message))
        if not any((supported_version.major == 1 and supported_version.minor >= 0
                    for supported_version in hello_message.supported_versions)):
            raise UnsupportedProtocolVersion("Server doesn't support protocol version: 1.x")
        async for message_read in cmake_messages_iterator:
            CMakeServer.logger.log(logging.DEBUG, "Server message: %s" % repr(message_read))
            message_type = message_read["type"]

            def final_response(callback_name):
                request_type = message_read["inReplyTo"]
                request_cookie = message_read["cookie"]
                key = RegisteredRequestKey(type=request_type, cookie=request_cookie)
                if key in self.registered_requests:
                    getattr(self.registered_requests[key], callback_name)(message_read)
                    del self.registered_requests[key]
                else:
                    CMakeServer.logger.log(logging.ERROR,
                                           "%s to unregistered request: %s" % (callback_name, repr(message_read)))

            def message_response(callback_name):
                request_type = message_read["inReplyTo"]
                request_cookie = message_read["cookie"]
                key = RegisteredRequestKey(type=request_type, cookie=request_cookie)
                if key in self.registered_requests:
                    getattr(self.registered_requests[key], callback_name)(message_read)
                else:
                    CMakeServer.logger.log(logging.ERROR,
                                           "%s to unregistered request: %s" % (callback_name, repr(message_read)))
            if message_type == "signal":
                self.signal_cb(message_read)
            elif message_type == "reply":
                final_response("success_cb")
            elif message_type == "error":
                final_response("failure_cb")
            elif message_type == "message":
                message_response("message_cb")
            elif message_type == "progress":
                message_response("progress_cb")
            else:
                print("Unknown server message type: %s (message: %s)" % (message_type, repr(message_read)))

    async def async_report_cmake_server_message(self, input_message):
        self.message_data_processed_event.clear()
        self.input_message_reader.feed_data(input_message)
        await self.message_data_processed_event.wait()

    async def async_stop_execution(self):
        self.message_data_processed_event.clear()
        self.input_message_reader.feed_eof()
        await self.message_data_processed_event.wait()

    async def async_post_cmake_server_request(self, async_send_message_cb, request_object) -> ResponseMessageIterator:
        response_iterator = ResponseMessageIterator(self.loop_object)
        message_to_send = self._form_and_register_cmake_server_request(
            request_object,
            success_cb=lambda x: response_iterator.success_cb(x),
            failure_cb=lambda x: response_iterator.failure_cb(x),
            progress_cb=lambda x: response_iterator.other_cb(x),
            message_cb=lambda x: response_iterator.other_cb(x))
        await async_send_message_cb(message_to_send)
        return response_iterator

    def post_cmake_server_request(self, send_message_cb, request_object) -> ResponseMessageIterator:
        response_iterator = ResponseMessageIterator(self.loop_object)
        message_to_send = self._form_and_register_cmake_server_request(
            request_object,
            success_cb=lambda x: response_iterator.success_cb(x),
            failure_cb=lambda x: response_iterator.failure_cb(x),
            progress_cb=lambda x: response_iterator.other_cb(x),
            message_cb=lambda x: response_iterator.other_cb(x))
        send_message_cb(message_to_send)
        return response_iterator

    def report_cmake_server_message(self, input_message):
        self.loop_object.run_until_complete(self.async_report_cmake_server_message(input_message))

    def stop_execution(self):
        self.loop_object.run_until_complete(self.async_stop_execution())


def create_cmake_server_controller(signal_cb, loop_object=None):
    import asyncio
    if loop_object is None:
        loop_object = asyncio.get_event_loop()
    return CMakeServer(loop_object=loop_object,
                       signal_cb=signal_cb)
