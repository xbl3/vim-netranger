from __future__ import absolute_import

import os
import string

from netranger import Vim


class UI(object):
    """ Parent class for all uis.
    Each ui might have more than one buffer for different purposes.
    """
    @property
    def position(self):
        return Vim.Var('NETRSplitOrientation')

    def __init__(self):
        self.bufs = {}

    def map_key_reg(self, key, regval):
        """ Register a key mapping in a UI buffer.
        The mapped action is:
        1. Store regval into g:NETRRegister, which serves as the argument for
        netranger buffer's call back after UI buffer quit.
        2. Quit the UI buffer.

        See Netranger.pend_onuiquit for details.
        """
        Vim.command(f'nnoremap <nowait> <silent> <buffer> {key} '
                    f':let g:NETRRegister=["{regval}"] <cr> :quit <cr>')

    def buf_valid(self, name='default'):
        """ Return True if a UI buffer existed and not wiped out. """
        return name in self.bufs and self.bufs[name].valid

    def del_buf(self, name):
        """ Wipe out a UI buffer. """
        if name in self.bufs:
            del self.bufs[name]

    def show(self, name='default'):
        """ Show the UI buffer. """
        Vim.command(f'{self.position} {self.bufs[name].number}sb')
        Vim.command('wincmd J')

    def create_buf(self, content, mappings=None, name='default', map_cr=False):
        """ Create the UI buffer. """
        Vim.command(f'{self.position} new')
        self.set_buf_common_option()
        new_buf = Vim.current.buffer
        self.bufs[name] = new_buf

        if mappings is not None:
            for k, v in mappings:
                self.map_key_reg(k, v)

        if map_cr:
            assert mappings is not None
            ui_internal_vim_dict_name = f'g:_{type(self).__name__}Map'
            Vim.command(f'let {ui_internal_vim_dict_name}={dict(mappings)}')
            Vim.command(
                "nnoremap <nowait> <silent> <buffer> <Cr> "
                ":let g:NETRRegister=[{}[getline('.')[0]]] <cr> :quit <cr>".
                format(ui_internal_vim_dict_name))

        new_buf.options['modifiable'] = True
        new_buf[:] = content
        new_buf.options['modifiable'] = False
        Vim.command('quit')

    def set_buf_common_option(self, modifiable=False):
        """ Set common option for a UI buffer. """
        Vim.command('setlocal noswapfile')
        Vim.command('setlocal foldmethod=manual')
        Vim.command('setlocal foldcolumn=0')
        Vim.command('setlocal nofoldenable')
        Vim.command('setlocal nobuflisted')
        Vim.command('setlocal nospell')
        Vim.command('setlocal buftype=nofile')
        Vim.command('setlocal bufhidden=hide')
        Vim.command('setlocal nomodifiable')


class HelpUI(UI):
    """ The UI displaying Netranger's current key mappings. """
    def __init__(self, keymap_doc):
        UI.__init__(self)

        self.create_buf(content=[
            f'{fn:<25} {",".join(keys):<10} {desc}'
            for fn, (keys, desc) in keymap_doc.items()
        ])


class AskUI(UI):
    """ The UI asking for the method for opening the current node. """
    def __init__(self, netranger):
        UI.__init__(self)
        self.netranger = netranger
        self.options = None
        self.fullpath = None
        # 106 -> j, 107 -> k
        self.create_buf(content=[],
                        mappings=[(chr(ind), chr(ind))
                                  for ind in range(97, 123)
                                  if ind != 106 and ind != 107],
                        map_cr=True)

    def ask(self, content, fullpath):
        self.show()
        if len(content) > 24:
            Vim.WarningMsg('Ask only supports up to 24 commands.')
            content = content[:24]

        ind = 97
        self.options = content[:]
        self.options.append('vim')
        self.fullpath = fullpath
        for i, c in enumerate(content):
            content[i] = f'{chr(ind)}. {c}'
            ind += 1
        content.append(f'{chr(ind)}. vim')

        buf = self.bufs['default']
        buf.api.set_option('modifiable', True)
        buf[:] = content
        buf.api.set_option('modifiable', False)
        self.netranger.pend_onuiquit(self._ask, 1)

    def _ask(self, char):
        cmd = self.options[ord(char) - 97]
        if cmd == 'vim':
            self.netranger.NETROpen(use_rifle=False)
        else:
            self.netranger.NETROpen(rifle_cmd=cmd)


class SortUI(UI):
    """ The UI for choosing sorting method. """
    sort_fns = {
        'a': lambda n: n.stat.st_atime if n.stat is not None else -1,
        'c': lambda n: n.stat.st_ctime if n.stat is not None else -1,
        'd': lambda n: '',
        'e': lambda n: SortUI.ext_name(n.name),
        'm': lambda n: n.stat.st_ctime if n.stat is not None else -1,
        's': lambda n: SortUI.size(n.fullpath),
    }

    sort_fn_ch = 'd'
    reverse = False

    @classmethod
    def size(self, path):
        try:
            if os.path.isdir(path):
                return str(len(os.listdir(path))).rjust(18)
            else:
                return str(os.stat(path).st_size).rjust(18)
        except PermissionError:
            return -1

    @classmethod
    def ext_name(self, path):
        ind = path.rfind('.')
        if ind < 0:
            return ' '
        else:
            return path[ind + 1:]

    @classmethod
    def select_sort_fn(cls, ch):
        SortUI.sort_fn_ch = ch

    @classmethod
    def get_sort_fn(cls):
        return SortUI.sort_fns[SortUI.sort_fn_ch]

    def __init__(self):
        UI.__init__(self)
        sort_opts = ['atime', 'ctime', 'default', 'extension', 'mtime', 'size']
        content = [f'{s[0]}  {s}' for s in sort_opts]
        content.insert(
            0, 'Type keys for sorting option. Use captial letter '
            'for reverse (small to large) order')
        mappings = [(k[0], k[0])
                    for k in sort_opts] + [(k[0].upper(), k[0].upper())
                                           for k in sort_opts]
        self.create_buf(content=content, mappings=mappings, map_cr=True)


class NewUI(UI):
    """ The UI for creating directory/file. """
    def __init__(self):
        UI.__init__(self)
        content = ['d.directory', 'f.file']
        mappings = [('d', 'd'), ('f', 'f')]
        self.create_buf(content=content, mappings=mappings, map_cr=True)


class BookMarkUI(UI):
    """ The UI for bookmarks.
    It contains two buffers for set/go actions.
    """
    def __init__(self, netranger):
        UI.__init__(self)
        self.valid_mark = string.ascii_lowercase + string.ascii_uppercase
        self.netranger = netranger
        self.mark_dict = {}
        self.path_to_mark = None

        # This is to avoid a bug that I can't solve.
        # If bookmark file is initially empty. The first time
        # 'm' (set) mapping is trigger, it won't quit the buffer
        # on user input..
        if not os.path.isfile(Vim.Var('NETRBookmarkFile')):
            with open(Vim.Var('NETRBookmarkFile'), 'w') as f:
                f.write(f'~:{os.path.expanduser("~")}')

        self.load_bookmarks()

    def load_bookmarks(self):
        self.mark_dict = {}
        if os.path.isfile(Vim.Var('NETRBookmarkFile')):
            with open(Vim.Var('NETRBookmarkFile'), 'r') as f:
                for line in f:
                    kp = line.split(':')
                    if (len(kp) == 2):
                        self.mark_dict[kp[0].strip()] = kp[1].strip()

    def set(self, path):
        """ Show the buffer for setting bookmark. """
        if not self.buf_valid('set'):
            self.create_buf(
                mappings=zip(self.valid_mark, self.valid_mark),
                content=[f'{k}:{p}' for k, p in self.mark_dict.items()],
                name='set')
        self.show('set')
        self.path_to_mark = path
        self.netranger.pend_onuiquit(self._set, 1)

    def _set(self, mark):
        """ The callback for the BookMarkUI/set. """
        if mark == '':
            return
        if mark not in self.valid_mark:
            Vim.command('echo "Only a-zA-Z are valid mark!!"')
            return
        set_buf = self.bufs['set']
        set_buf.options['modifiable'] = True

        if mark in self.mark_dict:
            for i, line in enumerate(set_buf):
                if len(line) > 0 and line[0] == mark:
                    set_buf[i] = f'{mark}:{self.path_to_mark}'
                    break
        elif self.path_to_mark in self.mark_dict.values():
            for i, line in enumerate(set_buf):
                if len(line) > 0 and line[2:] == self.path_to_mark:
                    set_buf[i] = f'{mark}:{self.path_to_mark}'
                    break
        else:
            set_buf.append(f'{mark}:{self.path_to_mark}')
        set_buf.options['modifiable'] = False
        self.mark_dict[mark] = self.path_to_mark
        self.del_buf('go')
        with open(Vim.Var('NETRBookmarkFile'), 'w') as f:
            for k, p in self.mark_dict.items():
                f.write(f'{k}:{p}\n')

    def go(self):
        """ Show the buffer for going to bookmark. """
        if not self.buf_valid('go'):
            self.create_buf(
                mappings=self.mark_dict.items(),
                map_cr=True,
                content=[f'{k}:{p}' for k, p in self.mark_dict.items()],
                name='go')
        self.show('go')
        self.netranger.pend_onuiquit(self.netranger.bookmarkgo_onuiquit, 1)

    def edit(self):
        """ Show the buffer for editing the bookmark. """
        Vim.command(f'belowright split {Vim.Var("NETRBookmarkFile")}')
        Vim.command('wincmd J')
        Vim.command('setlocal bufhidden=wipe')
        self.del_buf('set')
        self.del_buf('go')
        self.netranger.pend_onuiquit(self.load_bookmarks)
