" vim: ts=4 sw=4 et

" This is basic vim plugin boilerplate
let s:save_cpo = &cpo
set cpo&vim

function! s:restore_cpo()
  let &cpo = s:save_cpo
  unlet s:save_cpo
endfunction

if exists("g:loaded_vim_cmake_server")
  call s:restore_cpo()
  finish
endif

let g:loaded_vim_cmake_server = 1

if has('vim_starting') " Loading at startup.
  " We defer loading until after VimEnter to allow the gui to fork (see
  " `:h gui-fork`) and avoid a deadlock situation, as explained here:
  " https://github.com/Valloric/YouCompleteMe/pull/2473#issuecomment-267716136
  augroup vim_cmake_server_start
    autocmd!
    autocmd VimEnter * call vim_cmake_server#init_server_handle()
  augroup END
else " Manual loading with :packadd.
  call vim_cmake_server#init_server_handle()
endif

command! -nargs=+ -complete=file
      \ CMakeServerInit call vim_cmake_server#initialize_communication(<f-args>)

command! -nargs=0
      \ CMakeServerConfigure call vim_cmake_server#configure_and_generate()

" This is basic vim plugin boilerplate
call s:restore_cpo()
