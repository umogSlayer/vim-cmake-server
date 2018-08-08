" MIT License. Copyright (c) 2013-2016 Bailey Ling.
" vim: et ts=2 sts=2 sw=2

scriptencoding utf-8

" Due to some potential rendering issues, the use of the `space` variable is
" recommended.
let s:spc = g:airline_symbols.space

" Extension specific variables can be defined the usual fashion.
if !exists('g:airline#extensions#vim_cmake_server#airline_progress_message')
  let g:airline#extensions#vim_cmake_server#airline_progress_message = ''
endif

" First we define an init function that will be invoked from extensions.vim
function! airline#extensions#vim_cmake_server#init(ext)
  " Here we define a new part for the plugin.  This allows users to place this
  " extension in arbitrary locations.
  call airline#parts#define_raw('cmake_server_progress', '%{g:airline#extensions#vim_cmake_server#airline_progress_message}')

  " Next up we add a funcref so that we can run some code prior to the
  " statusline getting modifed.
  call a:ext.add_statusline_func('airline#extensions#vim_cmake_server#apply')
endfunction

" This function will be invoked just prior to the statusline getting modified.
function! airline#extensions#vim_cmake_server#apply(...)
  " First we check if this is our plugin buffer.
  if &filetype ==# 'cmake_server_messages'
    " We want to append to section_c, first we check if there's
    " already a window-local override, and if not, create it off of the global
    " section_c.
    let w:airline_section_c = get(w:, 'airline_section_c', g:airline_section_c)

    " Then we just append this extenion to it, optionally using separators.
    let w:airline_section_c .= s:spc . g:airline_left_alt_sep . s:spc . '%{g:airline#extensions#vim_cmake_server#airline_progress_message}'
  endif
endfunction
