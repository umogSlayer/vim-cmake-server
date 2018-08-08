# -*- coding: utf-8 -*-


def _send_message_to_server(message):
    import vim
    send_function = vim.Function("vim_cmake_server#output_data")
    send_function(message.decode("utf-8"))


def _message_function(message):
    import vim
    assert isinstance(message, str)
    message_line_list = message.split('\n')
    buffer_number = int(vim.eval("vim_cmake_server#find_buffer()"))
    messages_buffer = vim.buffers[buffer_number]
    messages_buffer.options["modifiable"] = 1
    messages_buffer.options["readonly"] = 0
    messages_buffer.append(message_line_list)
    messages_buffer.options["modifiable"] = 0
    messages_buffer.options["readonly"] = 1
    #vim.command('echom "CMakeServer Message"')
    #vim.command('redraw')
    #with open("output.txt", "a") as output_file:
        #print('CMakeServer Message', file=output_file)


async def progress_task(response_iterator):
    import vim
    progress_function = vim.Function("vim_cmake_server#update_progress")
    error_function = vim.Function("vim_cmake_server#report_error")
    async for response in response_iterator:
        response_type = response["type"]
        if response_type == "message":
            _message_function(response["message"])
        elif response_type == "progress":
            #with open("output.txt", "a") as output_file:
                #print('Progress Message', file=output_file)
            progress_function(
                response["progressMessage"],
                response["progressMinimum"],
                response["progressMaximum"],
                response["progressCurrent"])
        elif response_type == "error":
            error_function(response["errorMessage"])


def handshake(cmake_server, generator, source_directory, build_directory):
    request = {
        "type": "handshake",
        "cookie": "vim",
        "protocolVersion": {
            "major": 1,
        },
        "generator": generator,
        "sourceDirectory": source_directory,
        "buildDirectory": build_directory,
    }
    response_iterator = cmake_server.post_cmake_server_request(
        request_object=request,
        send_message_cb=_send_message_to_server)
    return progress_task(response_iterator)


def configure(cmake_server, cache_arguments):
    request = {
        "type": "configure",
        "cookie": "vim",
        "cacheArguments": ["-D" + cache_key + "=" + cache_value
                           for cache_key, cache_value in cache_arguments.items()]
    }
    response_iterator = cmake_server.post_cmake_server_request(
        request_object=request,
        send_message_cb=_send_message_to_server)
    return progress_task(response_iterator)


def compute(cmake_server):
    request = {
        "type": "compute",
        "cookie": "vim",
    }
    response_iterator = cmake_server.post_cmake_server_request(
        request_object=request,
        send_message_cb=_send_message_to_server)
    return progress_task(response_iterator)
