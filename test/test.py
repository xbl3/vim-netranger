import argparse
import os
import re
import subprocess
import sys
import time

from neovim import attach

from netranger import default
from netranger.colortbl import colorname2ind
from netranger.config import (rclone_rcd_port, test_dir, test_local_dir,
                              test_remote_cache_dir, test_remote_dir,
                              test_remote_name)
from tshell import Shell


def color_str(hi_key):
    hi = default.color[hi_key]
    if type(hi) is str:
        hi = colorname2ind[hi]
    return str(hi)


def assert_content(expected, level=None, ind=None, hi=None, hi_fg=False):
    if ind is None:
        line = nvim.current.line
    else:
        ind += 1
        line = nvim.current.buffer[ind]

    m = re.search(r'\[([34])8;5;([0-9]+)?m( *)([^ ]+)', line)

    assert m.group(4) == expected, 'expected:"{}", real: "{}"'.format(
        expected, m.group(4))
    if level is not None:
        assert m.group(
            3) == '  ' * level, "level mismatch: expected: {}, real:{}".format(
                '"{}"'.format('  ' * level), '"{}"'.format(m.group(3)))

    if hi is not None:
        expected_hi = color_str(hi)
        assert m.group(2) == expected_hi, 'expected_hi: "{}", '
        'real_hi: "{}"'.format(expected_hi, m.group(2))

        if hi_fg:
            assert m.group(1) == '4', 'Expect a foreground highlight'

    cLineNo = nvim.eval("line('.')") - 1
    if ind is None or ind == cLineNo:
        assert m.group(1) == '4', 'Background highlight mismatch. '
        'ind: {}, curLine: {}'.format(ind, cLineNo)
    else:
        assert m.group(1) == '3', 'Background highlight mismatch. '
        'ind: {}, curLine: {}'.format(ind, cLineNo)


def assert_highlight(expected, ind=None):
    if ind is None:
        line = nvim.current.line
    else:
        ind += 1
        line = nvim.current.buffer[ind]

    m = re.search(r'\[38;5;([0-9]+)(;7)?m', line)
    expected = color_str(expected)
    assert m.group(1) == expected, 'expected: "{}", real: "{}"'.format(
        expected, m.group(1))
    if ind == nvim.current.buffer.number:
        assert m.group(2) is not None
    else:
        assert m.group(2) is None


def assert_num_content_line(numLine):
    assert numLine == len(nvim.current.buffer
                          ) - 2, 'expected line #: {}, real line #: {}'.format(
                              numLine,
                              len(nvim.current.buffer) - 1)


def assert_fs(d, expected, root=None):
    """
    Test whether 'expected' exists in directory cwd/d, where
    cwd is /tmp/netrtest/local when testing local functions and
    cwd is /tmp/netrtest/remote when testing remote functions.
    """

    if root:
        old_cwd = os.getcwd()
        os.chdir(root)

    real = None
    for i in range(10):
        real = Shell.run('ls --group-directories-first ' + d).split()
        if real == expected:
            return
        time.sleep(0.05)

    assert real == expected, 'expected: {}, real: {}'.format(expected, real)

    if root:
        os.chdir(old_cwd)


def assert_fs_cache(d, expected):
    assert_fs(d, expected, root=test_remote_cache_dir)


def assert_fs_local(d, expected):
    assert_fs(d, expected, root=test_local_dir)


def assert_fs_remote(d, expected):
    assert_fs(d, expected, root=test_remote_dir)


def do_test(fn=None, fn_remote=None):
    """
    Note on the mecahnism of testing rclone on localhost:
    1. Tester run rclone to create a "local" remote named netrtest (must be
       exact this name)
    2. In default.py, the vim variable 'NETRemoteRoots' is set to
       {test_remote_name: test_remote_dir}, which defaults to
       {'netrtest', '/tmp/netrtest/remote'}.
    3. 'NETRemoteRoots' is passed to Rclone constructor, so that the rpath
       of the netrtest remote is mapped to '/tmp/netrtest/remote'.
    4. This just works in netranger. In cmd line, running
       'rclone lsl netrtest:/' still shows you the content of the root
       directory of the localhost.
    """
    old_cwd = os.getcwd()
    Shell.run('rm -rf {}'.format(test_dir))

    def prepare_test_dir(dirname):
        Shell.mkdir(dirname)
        os.chdir(dirname)
        Shell.mkdir('dir/subdir')
        Shell.mkdir('dir/subdir/subsubdir')
        Shell.mkdir('dir/subdir2')
        Shell.touch('dir/a')
        Shell.touch('.a')
        Shell.mkdir('dir2/')

        # The following should be removed when rclone fix "not copying empty
        # directories" bug.
        Shell.touch('dir/subdir/subsubdir/placeholder')
        Shell.touch('dir/subdir2/placeholder')
        Shell.touch('dir/subdir2/placeholder')

    prepare_test_dir(test_local_dir)
    if fn is not None:
        nvim.command('silent tabe {}'.format(test_local_dir))
        ensure_buf_no_expand()
        fn()
        print('== {} success =='.format(str(fn.__name__)))

    prepare_test_dir(test_remote_dir)
    Shell.run('rm -rf {}/*'.format(test_remote_cache_dir))
    if fn_remote is not None:
        nvim.command('NETRemoteList')
        found_remote = False
        for i, line in enumerate(nvim.current.buffer):
            if re.findall('.+(netrtest)', line):
                nvim.command('call cursor({}, 1)'.format(i + 1))
                found_remote = True
                break

        assert found_remote, 'You must set up an rclone remote named "{}" \
            to test remote function'.format(test_remote_name)
        nvim.input('l')
        nvim.command('NETRemotePull')
        nvim.command('call cursor(2, 1)')
        ensure_buf_no_expand()
        fn_remote()
        print('== {} success =='.format(str(fn_remote.__name__)))

    while nvim.eval('&ft') == 'netranger':
        nvim.command('bwipeout')
    os.chdir(old_cwd)


def test_on_cursormoved():
    nvim.input('j')
    assert_content('dir', ind=0, hi='dir')
    assert_content('dir2', ind=1, hi='dir', hi_fg=True)

    nvim.input('k')
    assert_content('dir', ind=0, hi='dir', hi_fg=True)
    assert_content('dir2', ind=1, hi='dir')

    # should test header footer


def test_NETROpen():
    nvim.input('l')
    assert_content('subdir', ind=0, hi='dir', hi_fg=True)
    assert_content('subdir2', ind=1, hi='dir')


def test_NETRParent():
    nvim.input('h')
    assert_content('local', ind=0, hi='dir', hi_fg=True)


def test_NETRGoPrevSibling():
    # Test both NETRGoPrevSibling and NETRGoNextSibling
    nvim.input('zA')
    nvim.input('j')
    nvim.input('}')
    assert_content('subdir2', hi='dir', hi_fg=True)
    nvim.input('}')
    assert_content('a', hi='file', hi_fg=True)
    nvim.input('{')
    assert_content('subdir2', hi='dir', hi_fg=True)
    nvim.input('{')
    assert_content('subdir', hi='dir', hi_fg=True)
    nvim.input('{')
    assert_content('dir', hi='dir', hi_fg=True)


def test_on_bufenter_cursor_stay_the_same_pos():
    nvim.input('ljhl')
    assert_content('subdir', ind=0, hi='dir')
    assert_content('subdir2', ind=1, hi='dir', hi_fg=True)


def test_on_bufenter_content_stay_the_same():
    nvim.input('zalh')
    assert_content('dir', ind=0, hi='dir', hi_fg=True)
    assert_content('subdir', level=1, ind=1, hi='dir')
    assert_content('dir2', ind=4, hi='dir')


def test_on_bufenter_fs_change():
    nvim.input('lh')
    Shell.touch('dir/b')
    Shell.mkdir('dir3')
    nvim.command('split new')
    nvim.command('quit')
    nvim.input('zA')
    assert_content('dir', ind=0, hi='dir', hi_fg=True)
    assert_content('b', ind=7, level=1, hi='file')
    assert_content('dir3', ind=9, hi='dir')
    assert_num_content_line(10)

    Shell.rm('dir/subdir2/placeholder')
    nvim.input('lh')
    assert_num_content_line(9)


def test_NETRToggleExpand():
    nvim.input('za')
    assert_content('dir', ind=0, hi='dir', hi_fg=True)
    assert_content('subdir', level=1, ind=1, hi='dir')
    assert_content('subdir2', ind=2, level=1, hi='dir')
    assert_content('a', ind=3, level=1, hi='file')
    assert_content('dir2', ind=4, hi='dir')
    nvim.input('za')
    assert_content('dir', ind=0, hi='dir', hi_fg=True)
    assert_content('dir2', ind=1, hi='dir')


def test_NETRToggleExpandRec():
    nvim.input('zA')
    assert_content('dir', ind=0, hi='dir', hi_fg=True)
    assert_content('subdir', level=1, ind=1, hi='dir')
    assert_content('subsubdir', level=2, ind=2, hi='dir')
    assert_content('placeholder', level=3, ind=3, hi='file')
    assert_content('subdir2', level=1, ind=4, hi='dir')
    assert_content('placeholder', level=2, ind=5, hi='file')
    assert_content('a', level=1, ind=6, hi='file')
    assert_content('dir2', level=0, ind=7, hi='dir')
    nvim.input('zA')
    assert_content('dir', ind=0, hi='dir', hi_fg=True)
    assert_content('dir2', ind=1, hi='dir')


def test_NETRVimCD():
    nvim.input('<Cr>')
    assert os.path.basename(
        nvim.command_output('pwd')) == 'dir', os.path.basename(
            nvim.command_output('pwd'))


def test_NETREdit():
    nvim.input('za')
    nvim.input('iiz<Left><Down>')
    nvim.input('y<Left><Down>')
    nvim.input('x<Left><Down>')
    nvim.input('w')
    nvim.input('<esc>:w<cr>')
    assert_content('dir2', ind=0, hi='dir')
    assert_content('zdir', ind=1, hi='dir')
    assert_content('xsubdir2', ind=2, level=1, hi='dir')
    assert_content('ysubdir', ind=3, level=1, hi='dir')
    assert_content('wa', ind=4, level=1, hi='file')

    assert_fs('', ['dir2', 'zdir'])
    assert_fs('zdir', ['xsubdir2', 'ysubdir', 'wa'])


def test_NETRNew():
    nvim.input('odzd<CR>')
    nvim.input('ofzf<CR>')
    assert_content('zd', ind=2, hi='dir', level=0)
    assert_content('zf', ind=3, hi='file', level=0)
    assert_fs('', ['dir', 'dir2', 'zd', 'zf'])
    nvim.input('<CR>odzd<CR>')
    nvim.input('ofzf<CR>')
    assert_fs('dir', ['subdir', 'subdir2', 'zd', 'a', 'zf'])


def test_NETRTogglePick():
    nvim.input('vjvklh')
    assert_content('dir', ind=0, hi='pick', hi_fg=True)
    assert_content('dir2', ind=1, hi='pick', hi_fg=False)
    nvim.input('v')
    assert_content('dir', ind=0, hi='dir', hi_fg=True)


def test_NETRTogglePickVisual():
    nvim.input('vVjv')
    assert_content('dir', ind=0, level=0, hi='dir', hi_fg=True)
    assert_content('dir2', ind=1, level=0, hi='pick', hi_fg=False)


def test_NETRCut():
    nvim.input('zajvjjvjd')
    assert_content('dir', ind=0, hi='dir')
    assert_content('subdir', ind=1, level=1, hi='cut')
    assert_content('subdir2', ind=2, level=1, hi='dir')
    assert_content('a', ind=3, level=1, hi='cut')


def test_NETRCutSingle():
    nvim.input('ddjdd')
    assert_content('dir', ind=0, hi='cut')
    assert_content('dir2', ind=1, hi='cut', hi_fg=True)


def test_NETRCopy():
    nvim.input('zajvjjvjy')
    assert_content('dir', ind=0, hi='dir')
    assert_content('subdir', ind=1, level=1, hi='copy')
    assert_content('subdir2', ind=2, level=1, hi='dir')
    assert_content('a', ind=3, level=1, hi='copy')


def test_NETRCopySingle():
    nvim.input('yyjyy')
    assert_content('dir', ind=0, hi='copy')
    assert_content('dir2', ind=1, hi='copy', hi_fg=True)


def test_NETRPaste_by_cut():
    nvim.input('zajddjjddkkkzajlp')
    wait_for_fs_free()
    assert_content('subdir', ind=0, hi='dir')
    assert_content('a', ind=1, hi='file')
    assert_fs('dir', ['subdir2'])
    assert_fs('dir2', ['subdir', 'a'])


def test_NETRPaste_by_copy():
    nvim.input('zajyyjjyykkkzajlp')
    wait_for_fs_free()
    assert_content('subdir', ind=0, hi='dir')
    assert_content('a', ind=1, hi='file')
    assert_fs('dir', ['subdir', 'subdir2', 'a'])
    assert_fs('dir2', ['subdir', 'a'])


def test_NETRPaste_sided_by_side():
    nvim.input('zajyyjjddkkkza')
    nvim.command('vsplit')
    nvim.input('jlp')
    wait_for_fs_free()
    assert_content('subdir', ind=0, hi='dir')
    assert_content('a', ind=1, hi='file')
    assert_fs('dir', ['subdir', 'subdir2'])
    assert_fs('dir2', ['subdir', 'a'])


def wait_for_fs_free():
    while nvim.command_output(
            'python3 print(ranger.cur_buf._num_fs_op)') != '0':
        pass
    return


def lock_fs():
    nvim.command('python3 ranger.cur_buf._num_fs_op=1')


def unlock_fs():
    nvim.command('python3 ranger.cur_buf._num_fs_op=0')


def ensure_buf_no_expand():
    nvim.input('2G')
    m2 = re.search(r'\[48;5;[0-9]+mdir.*', nvim.eval('getline(2)'))
    assert m2, "Assumes line2 is dir"

    m3 = re.search(r'\[38;5;[0-9]+mdir2.*', nvim.eval('getline(3)'))
    if not m3:
        nvim.input('za')


def test_NETRDelete():
    nvim.input('zajvjjvD')
    wait_for_fs_free()
    assert_fs('dir', ['subdir2'])
    assert_content('dir', ind=0, hi='dir')
    assert_content('subdir2', ind=1, level=1, hi='dir')
    assert_content('dir2', ind=2, hi='dir', hi_fg=True)


def test_NETRDeleteSingle():
    nvim.input('DD')
    wait_for_fs_free()
    assert_content('dir2', ind=0, hi='dir', hi_fg=True)


def test_delete_fail_if_fs_lock():
    nvim.input('v')
    lock_fs()
    nvim.input('D')
    assert_content('dir', ind=0, hi='pick', hi_fg=True)
    unlock_fs()


def test_delete_single_fail_if_fs_lock():
    lock_fs()
    nvim.input('DD')
    assert_content('dir', ind=0, hi='dir', hi_fg=True)
    unlock_fs()


def test_NETRForceDelete():
    Shell.run('chmod u-w dir/a')
    nvim.input('zajjjvX')
    wait_for_fs_free()
    assert_content('dir2', ind=3, hi='dir', hi_fg=True)


def test_NETRForceDeleteSingle():
    Shell.run('chmod u-w dir/a')
    nvim.input('zajjjXX')
    wait_for_fs_free()
    assert_content('dir2', ind=3, hi='dir', hi_fg=True)


def test_force_delete_fail_if_fs_lock():
    nvim.input('v')
    lock_fs()
    nvim.input('X')
    assert_content('dir', ind=0, hi='pick', hi_fg=True)
    unlock_fs()


def test_force_delete_single_fail_if_fs_lock():
    lock_fs()
    nvim.input('XX')
    assert_content('dir', ind=0, hi='dir', hi_fg=True)
    unlock_fs()


def test_bookmark():
    Shell.run('rm -f {}'.format(nvim.vars['NETRBookmarkFile']))

    nvim.input('mal')
    nvim.input("'a")
    assert_content('dir')

    nvim.input('lemjrb')
    nvim.command('exit')
    time.sleep(0.5)
    nvim.input("'b")
    assert_content('dir')


def test_help():
    nvim.input('?')
    nvim.command('quit')


def test_NETRToggleShowHidden():
    nvim.input('zh')
    assert_content('.a', ind=2, hi='file')
    nvim.input('zh')
    assert_num_content_line(2)


def test_NETRTogglePreview():
    #TODO
    pass


def cLine_ends_with(s):
    return nvim.current.line[:-4].endswith(s)


def test_size_display():
    # This vsplit is a rather ad-hoc work around in case of the screen is too
    # wide such that the following echo command failed because of too long
    # file name
    nvim.command('vsplit')

    width = nvim.current.window.width

    Shell.run('echo {} > {}'.format('a' * 1035, 'a' * width + '.pdf'))
    Shell.run('echo {} > {}'.format('b' * 1024, 'b' * width))

    nvim.command('edit .')
    nvim.input('Gk')
    assert cLine_ends_with(
        '~.pdf 1.01 K'), 'size display abbreviation fail: a~.pdf {}'.format(
            nvim.current.line[-10:])
    nvim.input('j')
    assert cLine_ends_with(
        'b~    1 K'), 'size display abbreviation fail: b~ {}'.format(
            nvim.current.line[-10:])

    # close the vsplit
    nvim.command('quit')


def test_size_wide_char_display():
    # This vsplit is a rather ad-hoc work around in case of the screen is too
    # wide such that the following echo command failed because of too long
    # file name
    nvim.command('vsplit')

    width = nvim.current.window.width

    Shell.run('echo {} > {}'.format('a' * 1035, '測' * width + '.pdf'))
    Shell.run('echo {} > {}'.format('b' * 1024, '試' * width))

    nvim.command('edit .')
    nvim.input('Gk')
    assert cLine_ends_with(
        '~.pdf 1.01 K'), 'size display abbreviation fail: a~.pdf {}'.format(
            nvim.current.line[-10:])
    nvim.input('j')
    assert cLine_ends_with(
        '試~    1 K'), 'size display abbreviation fail: b~ {}'.format(
            nvim.current.line[-10:])

    # close the vsplit
    nvim.command('quit')


def test_sort():
    # only test extension, mtime, size
    # extension: [a, a.a, a.b]
    # size: [a.b, a.a, a]
    # mtime: [a, a.b, a.a]
    Shell.run('echo {} > dir/{}'.format('a' * 3, 'a'))
    Shell.run('echo {} > dir/{}'.format('a' * 2, 'a.a'))
    Shell.run('echo {} > dir/{}'.format('a' * 1, 'a.b'))
    time.sleep(0.01)
    Shell.run('touch dir/a.a')

    nvim.input('zaSe')
    assert_content('dir', ind=0, hi='dir', level=0)
    assert_content('a', ind=3, hi='file', level=1)
    assert_content('a.a', ind=4, hi='file', level=1)
    assert_content('a.b', ind=5, hi='file', level=1)
    assert_content('dir2', ind=6, hi='dir', level=0)

    nvim.input('SE')
    assert_content('dir2', ind=0, hi='dir', level=0)
    assert_content('dir', ind=1, hi='dir', level=0)
    assert_content('a.b', ind=2, hi='file', level=1)
    assert_content('a.a', ind=3, hi='file', level=1)
    assert_content('a', ind=4, hi='file', level=1)

    nvim.input('Ss')
    assert_content('dir2', ind=0, hi='dir', level=0)
    assert_content('dir', ind=1, hi='dir', level=0)
    assert_content('a.b', ind=4, hi='file', level=1)
    assert_content('a.a', ind=5, hi='file', level=1)
    assert_content('a', ind=6, hi='file', level=1)

    nvim.input('SS')
    assert_content('dir', ind=0, hi='dir', level=0)
    assert_content('a', ind=1, hi='file', level=1)
    assert_content('a.a', ind=2, hi='file', level=1)
    assert_content('a.b', ind=3, hi='file', level=1)
    assert_content('dir2', ind=6, hi='dir', level=0)

    nvim.input('Sm')
    assert_content('dir2', ind=0, hi='dir', level=0)
    assert_content('dir', ind=1, hi='dir', level=0)
    assert_content('a', ind=4, hi='file', level=1)
    assert_content('a.b', ind=5, hi='file', level=1)
    assert_content('a.a', ind=6, hi='file', level=1)

    nvim.input('SM')
    assert_content('dir', ind=0, hi='dir', level=0)
    assert_content('a.a', ind=1, hi='file', level=1)
    assert_content('a.b', ind=2, hi='file', level=1)
    assert_content('a', ind=3, hi='file', level=1)
    assert_content('dir2', ind=6, hi='dir', level=0)
    nvim.input('Sd')


def test_opt_Autochdir():
    default_value = nvim.vars['NETRAutochdir']

    pwd = nvim.eval('getcwd()')
    nvim.vars['NETRAutochdir'] = True
    nvim.input('l')
    assert nvim.eval('getcwd()') != pwd
    nvim.input('h')

    nvim.vars['NETRAutochdir'] = False
    nvim.input('l')
    assert nvim.eval('getcwd()') == pwd

    nvim.vars['NETRAutochdir'] = default_value


def test_rifle():
    # TODO
    pass


def test_NETRDelete_remote():
    nvim.input('zajvjjvD')
    wait_for_fs_free()
    assert_fs('dir', ['subdir2'])
    assert_fs_cache('dir', ['subdir2'])


def test_NETRPaste_by_cut_remote2local():
    nvim.input('zajvjjvd')
    nvim.command('vsplit {}'.format(test_local_dir))
    nvim.input('jlp')
    wait_for_fs_free()
    assert_content('subdir', ind=0, hi='dir')
    assert_content('a', ind=1, hi='file')
    nvim.command('bwipeout')

    assert_fs_remote('dir', ['subdir2'])
    assert_fs_cache('dir', ['subdir2'])
    assert_fs_local('dir2', ['subdir', 'a'])


def test_NETRPaste_by_cut_local2remote():
    nvim.command('vsplit {}'.format(test_local_dir))
    ensure_buf_no_expand()
    nvim.input('zajvjjvd')
    nvim.command('wincmd w')
    nvim.input('jlp')
    wait_for_fs_free()
    assert_content('subdir', ind=0, hi='dir')
    assert_content('a', ind=1, hi='file')
    nvim.command('bwipeout')
    assert_fs_local('dir', ['subdir2'])
    assert_fs_remote('dir2', ['subdir', 'a'])
    assert_fs_cache('dir2', ['subdir', 'a'])


def test_NETRPaste_by_cut_remote2remote():
    nvim.input('zajvjjvd')
    nvim.input('Glp')
    wait_for_fs_free()
    assert_content('subdir', ind=0, hi='dir')
    assert_content('a', ind=1, hi='file')

    assert_fs_remote('dir', ['subdir2'])
    assert_fs_remote('dir2', ['subdir', 'a'])

    assert_fs_cache('dir', ['subdir2'])
    assert_fs_cache('dir2', ['subdir', 'a'])


def test_NETRPaste_by_copy_remote2local():
    nvim.input('zajvjjvy')
    nvim.command('vsplit {}'.format(test_local_dir))
    ensure_buf_no_expand()
    nvim.input('jlp')
    wait_for_fs_free()
    assert_content('subdir', ind=0, hi='dir')
    assert_content('a', ind=1, hi='file')
    nvim.command('bwipeout')

    assert_fs_remote('dir', ['subdir', 'subdir2', 'a'])
    assert_fs_cache('dir', ['subdir', 'subdir2', 'a'])
    assert_fs_local('dir2', ['subdir', 'a'])


def test_NETRPaste_by_copy_local2remote():
    nvim.command('vsplit {}'.format(test_local_dir))
    ensure_buf_no_expand()
    nvim.input('zajvjjvy')
    nvim.command('wincmd w')
    nvim.input('jlp')
    wait_for_fs_free()
    assert_content('subdir', ind=0, hi='dir')
    assert_content('a', ind=1, hi='file')
    nvim.command('bwipeout')
    assert_fs_local('dir', ['subdir', 'subdir2', 'a'])
    assert_fs_remote('dir2', ['subdir', 'a'])
    assert_fs_cache('dir2', ['subdir', 'a'])


def test_NETRPaste_by_copy_remote2remote():
    nvim.input('zajvjjvy')
    nvim.input('Glp')
    wait_for_fs_free()
    assert_content('subdir', ind=0, hi='dir')
    assert_content('a', ind=1, hi='file')

    assert_fs_remote('dir', ['subdir', 'subdir2', 'a'])
    assert_fs_remote('dir2', ['subdir', 'a'])

    assert_fs_cache('dir', ['subdir', 'subdir2', 'a'])
    assert_fs_cache('dir2', ['subdir', 'a'])


def test_api_cur_node_name():
    assert nvim.call('netranger#cur_node_name') == 'dir'


def test_api_cur_node_path():
    assert nvim.call('netranger#cur_node_path') == os.path.abspath('dir')


def test_api_cp():
    nvim.input('za')
    nvim.call('netranger#cp', 'dir/subdir', './')
    nvim.call('netranger#cp', 'dir/a', './')
    wait_for_fs_free()
    assert_content('subdir', ind=5, hi='dir')
    assert_content('a', ind=6, hi='file')
    assert_fs('', ['dir', 'dir2', 'subdir', 'a'])


def test_api_cp_remote():
    nvim.input('za')
    vimcwd = nvim.call('getcwd')
    nvim.call('netranger#cp', f'{vimcwd}/dir/subdir', vimcwd)
    nvim.call('netranger#cp', f'{vimcwd}/dir/a', vimcwd)
    wait_for_fs_free()
    assert_content('subdir', ind=5, hi='dir')
    assert_content('a', ind=6, hi='file')
    assert_fs_cache('', ['dir', 'dir2', 'subdir', 'a'])
    assert_fs_remote('', ['dir', 'dir2', 'subdir', 'a'])


def test_api_mv():
    nvim.input('za')
    nvim.call('netranger#mv', 'dir/subdir', './')
    nvim.call('netranger#mv', 'dir/a', './')
    wait_for_fs_free()
    assert_content('subdir', ind=3, hi='dir')
    assert_content('a', ind=4, hi='file')
    assert_fs('', ['dir', 'dir2', 'subdir', 'a'])
    assert_fs('dir', ['subdir2'])


def test_api_mv_remote():
    nvim.input('za')
    vimcwd = nvim.call('getcwd')
    nvim.call('netranger#mv', f'{vimcwd}/dir/subdir', vimcwd)
    nvim.call('netranger#mv', f'{vimcwd}/dir/a', vimcwd)
    wait_for_fs_free()
    assert_content('subdir', ind=3, hi='dir')
    assert_content('a', ind=4, hi='file')
    assert_fs_cache('', ['dir', 'dir2', 'subdir', 'a'])
    assert_fs_cache('dir', ['subdir2'])
    assert_fs_remote('', ['dir', 'dir2', 'subdir', 'a'])
    assert_fs_remote('dir', ['subdir2'])


def test_api_rm():
    nvim.input('za')
    nvim.call('netranger#rm', 'dir/subdir')
    nvim.call('netranger#rm', 'dir/a')
    wait_for_fs_free()
    assert_content('subdir2', ind=1, hi='dir', level=1)
    assert_content('dir2', ind=2, hi='dir')
    assert_fs('dir', ['subdir2'])


def test_api_rm_remote():
    nvim.input('za')
    vimcwd = nvim.call('getcwd')
    nvim.call('netranger#rm', f'{vimcwd}/dir/subdir')
    nvim.call('netranger#rm', f'{vimcwd}/dir/a')
    wait_for_fs_free()
    assert_content('subdir2', ind=1, hi='dir', level=1)
    assert_content('dir2', ind=2, hi='dir')
    assert_fs_cache('dir', ['subdir2'])
    assert_fs_remote('dir', ['subdir2'])


def parse_arg(argv):
    parser = argparse.ArgumentParser(description='')
    parser.add_argument(
        '-m',
        '--manual',
        action='store_true',
        help='Only setting up testing directories. Used for testing manually')
    parser.add_argument(
        '--listen_address',
        default=None,
        help='NVIM_LISTEN_ADDRESS for an open neovim. If set to none, open a \
        headless neovim instead.')
    return parser.parse_args(argv[1:])


if __name__ == '__main__':
    args = parse_arg(sys.argv)
    if args.manual:
        nvim = attach(
            'child',
            argv=['nvim', '-u', './test_init.vim', '--embed', '--headless'])
        do_test()
    else:
        if args.listen_address:
            nvim = attach('socket', path=args.listen_address)
        else:
            nvim = attach('child',
                          argv=[
                              'nvim', '-u', './test_init.vim', '--embed',
                              '--headless'
                          ])

        def do_test_navigation():
            do_test(test_on_cursormoved)
            do_test(test_NETROpen)
            do_test(test_NETRParent)
            do_test(test_NETRGoPrevSibling)
            do_test(test_on_bufenter_cursor_stay_the_same_pos)
            do_test(test_on_bufenter_content_stay_the_same)
            do_test(test_on_bufenter_fs_change)
            do_test(test_NETRToggleExpand)
            do_test(test_NETRToggleExpandRec)
            do_test(test_NETRVimCD)

        def do_test_delete():
            do_test(test_NETRDelete)
            do_test(test_NETRDeleteSingle)
            do_test(test_NETRForceDelete)
            do_test(test_NETRForceDeleteSingle)

            # # Can't pass on travis, don't know why
            # do_test(test_delete_fail_if_fs_lock)
            # do_test(test_delete_single_fail_if_fs_lock)
            # do_test(test_force_delete_fail_if_fs_lock)
            # do_test(test_force_delete_single_fail_if_fs_lock)

        def do_test_pickCopyCutPaste():
            do_test(test_NETRTogglePick)
            do_test(test_NETRTogglePickVisual)
            do_test(test_NETRCut)
            do_test(test_NETRCopy)
            do_test(test_NETRCutSingle)
            do_test(test_NETRCopySingle)

            # reset pick,cut,copy sets because previous tests do not paste to
            # reset them
            nvim.command('python3 ranger._reset_pick_cut_copy()')
            do_test(test_NETRPaste_by_cut)
            do_test(test_NETRPaste_by_copy)
            do_test(test_NETRPaste_sided_by_side)

        def do_test_delete_remote():
            do_test(fn_remote=test_NETRDelete_remote)

        def do_test_pickCopyCutPaste_remote():
            do_test(fn_remote=test_NETRPaste_by_cut_local2remote)
            do_test(fn_remote=test_NETRPaste_by_cut_remote2local)
            do_test(fn_remote=test_NETRPaste_by_cut_remote2remote)

            do_test(fn_remote=test_NETRPaste_by_copy_local2remote)
            do_test(fn_remote=test_NETRPaste_by_copy_remote2local)
            do_test(fn_remote=test_NETRPaste_by_copy_remote2remote)

        def do_test_UI():
            do_test(test_bookmark)
            do_test(test_help)

        def do_test_api():
            do_test(test_api_cur_node_name)
            do_test(test_api_cur_node_path)

            do_test(test_api_cp)
            do_test(test_api_mv)
            do_test(test_api_rm)

            do_test(fn_remote=test_api_cp_remote)
            do_test(fn_remote=test_api_mv_remote)
            do_test(fn_remote=test_api_rm_remote)

        do_test_api()
        do_test(test_NETRTogglePreview)
        do_test_navigation()
        do_test(test_NETREdit)
        do_test(test_NETRNew)
        do_test_delete()
        do_test_pickCopyCutPaste()
        do_test(test_NETRToggleShowHidden)
        do_test(test_size_display)
        do_test(test_size_wide_char_display)
        do_test(test_sort)
        do_test(test_opt_Autochdir)
        do_test_UI()

        do_test_delete_remote()
        do_test_pickCopyCutPaste_remote()

        do_test(test_rifle)

        # do_test(fn_remote=test_edit_remote)
        # # TODO
        # # add SORT test for broken link #issue 21

        # TODO
        # test abbrev_cwd

        # TODO
        # test toggle sudo
        nvim.close()

        try:
            # Force down rclone server down
            subprocess.check_output(
                f'rclone rc core/quit --rc-addr=localhost:{rclone_rcd_port}',
                shell=True)
        except Exception:
            pass
