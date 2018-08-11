" MIT License. Copyright (c) 2018 Vladimir Bayrashevskiy.
" vim: ts=4 sts=4 sw=4 et

" This is basic vim plugin boilerplate
let s:save_cpo = &cpo
set cpo&vim

let s:script_folder_path = escape( expand( '<sfile>:p:h' ), '\' )
let s:output_buffer_name = '(CMakeServer) Output'
let s:cmake_cache_variable_current_overwrites = {}
let s:cmake_cache_variable_all_overwrites = {}
let s:communication_is_initialized = 0

function! vim_cmake_server#init_server_handle() abort
    python3 <<EOF
import vim
import sys
import os

script_folder = vim.eval('s:script_folder_path')
sys.path.insert(0, os.path.join(script_folder, '..', 'python'))

import vimadapter

cmake_server_adapter = None

import request
EOF
endfunction

function! vim_cmake_server#vim_leave_callback() abort
    python3 <<EOF
if cmake_server_adapter is not None:
    cmake_server_adapter.close()
del cmake_server_adapter

import asyncio
loop_object = asyncio.get_event_loop()
loop_object.stop()
loop_object.close()
del loop_object
del asyncio
EOF
endfunction

function! vim_cmake_server#input_data(channel, message) abort
    python3 << EOF
current_server_message = vim.eval('a:message')
cmake_server_adapter.cmake_server.report_cmake_server_message(
    current_server_message.encode("utf-8"))
EOF
endfunction

function! vim_cmake_server#output_data(message) abort
    call ch_sendraw(s:cmake_server_channel, a:message)
endfunction

function! vim_cmake_server#find_buffer() abort
    return bufnr(s:output_buffer_name)
endfunction

function! vim_cmake_server#open_buffer() abort
    let l:bufnr = s:find_or_create_buffer()
    if bufwinnr(l:bufnr) == -1
        let save_switchbuf = &switchbuf
        let &switchbuf = 'split'
        silent exec 'belowright sbuffer ' . fnameescape(s:output_buffer_name)
        let &switchbuf = save_switchbuf
        wincmd p
    endif
endfunction

function! s:create_buffer() abort
    silent exec 'belowright new ' . fnameescape(s:output_buffer_name)
    setlocal buftype=nofile bufhidden=hide noswapfile readonly nomodifiable filetype=cmake_server_messages
    wincmd p
endfunction

function! s:find_or_create_buffer() abort
    let output_buffer_nr = vim_cmake_server#find_buffer()
    if output_buffer_nr == -1
        call s:create_buffer()
    endif
    return vim_cmake_server#find_buffer()
endfunction

function! vim_cmake_server#report_error(error_message) abort
    echohl ErrorMsg
        echomsg a:error_message
    echohl None
endfunction

function! vim_cmake_server#update_progress(progress_message, progress_min, progress_max, progress_current) abort
    if exists('g:airline#extensions#vim_cmake_server#airline_progress_message')
        let g:airline#extensions#vim_cmake_server#airline_progress_message = a:progress_message . ' ' . a:progress_current . '/' . a:progress_max
    endif
endfunction

function! s:reset_current_overwrites() abort
    let s:cmake_cache_variable_current_overwrites = {}
endfunction

function! s:reset_overwrites() abort
    let s:cmake_cache_variable_current_overwrites = {}
    let s:cmake_cache_variable_all_overwrites = {}
endfunction

function! vim_cmake_server#initialize_communication(source_dir, build_dir, ...) abort
    let l:source_dir = fnamemodify(a:source_dir, ':p')
    let l:build_dir = fnamemodify(a:build_dir, ':p')
    let s:cmake_server_job = job_start("cmake -E server --experimental --debug", {
        \ "in_io": "pipe",
        \ "out_io": "pipe",
        \ "err_io": "buffer",
        \ "in_mode": "raw",
        \ "out_mode": "raw",
        \ "out_cb": "vim_cmake_server#input_data",
        \ })
    let s:cmake_server_channel = job_getchannel(s:cmake_server_job)
    call s:reset_overwrites()
    if exists("g:cmake_server_generator")
        let l:generator = g:cmake_server_generator
    else
        let l:generator = "Ninja"
    endif
    call s:find_or_create_buffer()
    let s:communication_is_initialized = 1
    python3 <<EOF

if cmake_server_adapter is not None:
    cmake_server_adapter.close()

cmake_server_adapter = vimadapter.Adapter()

source_dir = vim.eval("l:source_dir")
build_dir = vim.eval("l:build_dir")
generator = vim.eval("l:generator")
cmake_server_adapter.post_task(
    request.handshake(cmake_server_adapter.cmake_server,
                      source_directory=source_dir,
                      build_directory=build_dir,
                      generator=generator))
EOF
endfunction

function! vim_cmake_server#set_cache_value(cache_variable, value, ...) abort
    let s:cmake_cache_variable_current_overwrites[a:cache_variable] = a:value
    let s:cmake_cache_variable_all_overwrites[a:cache_variable] = a:value
endfunction

function! vim_cmake_server#save_cache_overrides(filepath) abort
    python3 <<EOF
cache_variables = vim.eval("s:cmake_cache_variable_all_overwrites")
with open(vim.eval("a:filepath"), "wb") as output_file:
    import json
    output_file.write(json.dumps(cache_variables, sort_keys=True, ensure_ascii=False, indent=4).encode('utf-8'))
EOF
endfunction

function! vim_cmake_server#load_cache_overrides(filepath) abort
    call s:reset_overwrites()
    python3 <<EOF
with open(vim.eval("a:filepath"), "rb") as input_file:
    import json
    cache_variables = json.load(input_file, encoding='utf-8')
    set_cache_override_function = vim.Function("vim_cmake_server#set_cache_value")
    for cache_variable, value in cache_variables.items():
        set_cache_override_function(cache_variable, value)
EOF
endfunction

function! vim_cmake_server#configure() abort
    if s:communication_is_initialized == 1
        python3 <<EOF
cache_variables = vim.bindeval("s:cmake_cache_variable_current_overwrites")
cmake_server_adapter.post_task(
    request.configure(cmake_server_adapter.cmake_server,
                      cache_variables))
EOF
        call s:reset_current_overwrites()
        call vim_cmake_server#open_buffer()
    else
        let v:errmsg = 'CMakeServer communication is not initialized'
        throw v:errmsg
    endif
endfunction

function! vim_cmake_server#generate() abort
    if s:communication_is_initialized == 1
        python3 <<EOF
cmake_server_adapter.post_task(
    request.compute(cmake_server_adapter.cmake_server))
EOF
        call vim_cmake_server#open_buffer()
    else
        let v:errmsg = 'CMakeServer communication is not initialized'
        throw v:errmsg
    endif
endfunction

function! vim_cmake_server#configure_and_generate() abort
    call vim_cmake_server#configure()
    call vim_cmake_server#generate()
endfunction

" This is basic vim plugin boilerplate
let &cpo = s:save_cpo
unlet s:save_cpo
