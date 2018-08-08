# -*- coding: utf-8 -*-
import vim
import proto

class Adapter(object):
    def __init__(self):
        import asyncio
        self._loop_object = asyncio.get_event_loop()
        self._changed_files = set()
        self._renamed_files = set()
        self._is_dirty = True

        self.cmake_server = proto.CMakeServer(self._loop_object, self._signal_cb)

    def _signal_cb(self, signal_message):
        assert isinstance(signal_message, dict)
        if signal_message["name"] == "dirty":
            self._is_dirty = True
        elif signal_message["name"] == "fileChange":
            file_path = signal_message["path"]
            for type_of_change in signal_message["properties"]:
                if type_of_change == "change":
                    self._changed_files.add(file_path)
                elif type_of_change == "rename":
                    self._renamed_files.add(file_path)

    def post_task(self, coroutine_task):
        self._loop_object.create_task(coroutine_task)
