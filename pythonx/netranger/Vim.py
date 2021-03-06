import time

import vim

_hasnvim = int(vim.eval('has("nvim")'))
gui_compaitable = int(
    vim.eval('has("gui")')) or (int(vim.eval('has("termguicolors")'))
                                and vim.options['termguicolors'])

# original api
eval = vim.eval
vars = vim.vars
error = vim.error
options = vim.options
command = vim.command
strwidth = vim.strwidth
current = vim.current
buffers = vim.buffers
tabpages = vim.tabpages

if _hasnvim:

    def walk(fn, obj, *args, **kwargs):
        return obj
else:

    def walk(fn, obj, *args, **kwargs):
        """Recursively walk an object graph applying `fn`/`args` to objects."""
        objType = type(obj)
        if objType in [list, tuple, vim.List]:
            return list(walk(fn, o, *args) for o in obj)
        elif objType in [dict, vim.Dictionary]:
            return dict((walk(fn, k, *args), walk(fn, v, *args))
                        for k, v in obj.items())
        return fn(obj, *args, **kwargs)


if vim.eval('has("timers")') == "1" and not vim.vars.get("_NETRDebug", False):

    def Timer(delay, fn, pyfn, *args):
        if len(args):
            vim.command(
                f'call timer_start({delay}, function("{fn}", {list(args)}))')
        else:
            vim.command(f'call timer_start({delay}, "{fn}")')
else:

    def Timer(delay, fn, pyfn, *args):
        pyfn(*args)


if gui_compaitable:

    def ColorMsg(msg, c, background):
        if background:
            return f'[48;2;{c}m{msg}[0m'
        else:
            return f'[38;2;{c}m{msg}[0m'
else:

    def ColorMsg(msg, c, background):
        if background:
            return f'[48;5;{c}m{msg}[0m'
        else:
            return f'[38;5;{c}m{msg}[0m'


def log(*msg):
    with open('/tmp/netrlog', 'a') as f:
        f.write(' '.join([str(m) for m in msg]) + '\n')


def decode_if_bytes(obj, mode=True):
    """Decode obj if it is bytes."""
    if mode is True:
        mode = 'strict'
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors=mode)
    return obj


def VimChansend(job_id, msg):
    vim.command(f'chansend({job_id},"{msg}\n")')


_NETRcbks = {}


def VimAsyncCallBack(job_id, event, data):
    cbk = _NETRcbks[job_id][event]
    if event == 'exit':
        cbk()
        del _NETRcbks[job_id]
    else:
        cbk(job_id, data)


def do_nothing_with_args(job_id, data):
    pass


def do_nothing():
    pass


if _hasnvim:

    def JobStart(cmd, term=False):
        if not term:
            vim.command(f'let g:NETRJobId = jobstart(\'{cmd}\',\
                    {{"on_stdout":function("netranger#asyncCallBack"),\
                      "on_stderr":function("netranger#asyncCallBack"),\
                      "on_exit":function("netranger#asyncCallBack")}})')
        else:
            vim.command('10 new')
            cmd_win_id = vim.eval('win_getid()')
            vim.command('let g:NETRJobId = termopen(\'{}\',\
                        {{"on_exit":{{j,d,e -> function("netranger#termAsyncCallBack")(j,d,e, {})}} }})'
                        .format(cmd, cmd_win_id))
        return str(vim.vars['NETRJobId'])

else:

    def JobStart(cmd, term=False):
        cur_time = str(time.time())
        if not term:
            vim.command(f'call job_start(\'{cmd}\', {{\
                    "out_cb":{{j,d-> netranger#asyncCallBack("{cur_time}",d,"stdout")}},\
                      "err_cb":{{j,d-> netranger#asyncCallBack("{cur_time}",d,"stderr")}},\
                      "exit_cb":{{j,s-> netranger#asyncCallBack("{cur_time}",s,"exit")}}\
                                                   }})')
        else:
            vim.command('10 new')
            vim.command('startinsert')
            cmd_win_id = vim.eval('win_getid()')
            vim.command('call term_start(\'{}\', {{\
                        "curwin":v:true,\
                        "exit_cb":{{j,s-> netranger#termAsyncCallBack("{}",s,"exit",{})}}\
                                                 }})'.format(
                cmd, cur_time, cmd_win_id))
        return cur_time


def AsyncRun(cmd, on_stdout=None, on_stderr=None, on_exit=None, term=False):

    if on_stdout is None:
        on_stdout = do_nothing_with_args
    if on_stderr is None:
        on_stderr = do_nothing_with_args
    if on_exit is None:
        on_exit = do_nothing

    job_id = JobStart(cmd, term=term)
    _NETRcbks[job_id] = {
        'stdout': on_stdout,
        'stderr': on_stderr,
        'exit': on_exit
    }


def Var(name, default=None):
    if name not in vim.vars:
        return default
    return walk(decode_if_bytes, vim.vars[name])


def SetVar(name, value):
    vim.vars[name] = value


def ErrorMsg(exception):
    if hasattr(exception, 'output'):
        msg = exception.output.decode('utf-8')
    else:
        msg = str(exception)
    msg = msg.strip()
    if not msg:
        return
    vim.command(
        'unsilent echohl ErrorMsg | unsilent echo "{}" | echohl None '.format(
            msg.replace('"', '\\"')))


def debug(*msg):
    vim.command('unsilent echom "{}"'.format(' '.join([str(m) for m in msg])))


def WarningMsg(msg):
    vim.command(
        'unsilent echohl WarningMsg | unsilent echo "{}" | echohl None '.
        format(msg.replace('"', '\\"')))


def Echo(msg):
    vim.command(f'unsilent echo "{msg}"')


def UserInput(hint, default=''):
    vim.command(f'let g:NETRRegister=input("{hint}: ", "{default}")')
    return decode_if_bytes(vim.vars['NETRRegister'])


class pbar(object):
    def __init__(self, objects, total=None, chunkSize=100):
        self.objects = iter(objects)
        if total is None:
            self.total = len(objects)
        else:
            self.total = total
        self.cur = 0
        self.chunkSize = chunkSize
        self.wid = vim.current.window.width
        self.st_save = vim.current.window.options['statusline']

    def __iter__(self):
        return self

    def __next__(self):
        if self.cur == self.total:
            vim.current.window.options['statusline'] = self.st_save
            vim.command("redrawstatus!")
            raise StopIteration
        else:
            self.cur += 1
            if self.cur % self.chunkSize == 0:
                vim.current.window.options[
                    'statusline'] = "%#NETRhiProgressBar#{}%##".format(
                        ' ' * int(self.cur * self.wid / self.total))
                vim.command("redrawstatus!")
            return next(self.objects)
