#!/usr/bin/env python

import errno
import fcntl
import getopt
import glob
import inspect
import json
import os
import random
import re
import shutil
import socket
import sys
import tempfile
import time

if os.name == 'posix' and sys.version_info[0] < 3:
    try:
        import subprocess32 as subprocess
    except:
        import subprocess
else:
    import subprocess

import portalocker


def main():
    init()
    path = pick_input()

    if path:
        process_input(path)


def init():
    init_globals()
    setup_locking(block=False)
    args = parse_commandline()
    read_config(args)


def init_globals():
    global script_path
    global script_dir
    global hostdir
    global mark_prefix
    global debug
    global verbose
    global logfile

    script = inspect.stack()[-1][1]
    script_path = os.path.realpath(script)
    script_dir = os.path.dirname(script_path)
    hostdir = os.path.join(script_dir, hostname())
    mark_prefix = 'processing.'
    debug = False
    verbose = False
    logfile = None

    random.seed()


def read_config(args):
    global config

    specific_config = None
    host_config = os.path.join(hostdir, 'queue.json')
    default_config = os.path.join(script_dir, 'queue.json')

    if args:
        specific_config = os.path.realpath(args[0])

    if specific_config:
        configfile = specific_config
    elif os.path.exists(host_config):
        configfile = host_config
    else:
        configfile = default_config

    try:
        config = json.load(open(configfile))
    except:
        output("Could not read any config file.")
        if specific_config:
            output(' Command-line config: %s' % specific_config)
        else:
            output(' Machine-specific config: %s' % host_config)
            output(' Default config: %s' % default_config)
        sys.exit(1)

    if 'call_vars' not in config:
        config['call_vars'] = dict()

    if 'incoming_paths' not in config or type(config['incoming_paths']) not in (str, unicode, list):
        raise (ValueError("Section 'incoming_paths' required in config file as a list."))
    if type(config['incoming_paths']) in (str, unicode):
        config['incoming_paths'] = [config['incoming_paths']]

    if 'in_order' in config and type(config['in_order']) in (str, unicode):
        config['in_order'] = [config['in_order']]

    if 'file_filters' not in config or type(config['file_filters']) not in (str, unicode, list):
        raise (ValueError("Section 'file_filters' required in config file as a list."))
    if type(config['file_filters']) in (str, unicode):
        config['file_filters'] = [config['file_filters']]

    if 'call' not in config or type(config['call']) is not list:
        raise (ValueError("Section 'call' required in config file as a list."))

    if 'destination_base' not in config or type(config['destination_base']) not in (str, unicode):
        raise (ValueError("Section 'destination_base' required in config file as a string."))

    if 'failed_path' not in config or type(config['failed_path']) not in (str, unicode):
        raise (ValueError("Section 'failed_path' required in config file as a string."))

    if subprocess.__name__ == 'subprocess32':
        if 'timeout' in config and type(config['timeout']) not in (int, float, long):
            raise (ValueError("Section 'timeout' must be a number."))

    if verbose:
        config['call_vars']['input_file'] = 'fake input'
        config['call_vars']['output_file'] = 'fake output'

        output('Search paths: %s' % ' '.join(config['incoming_paths']))
        output('File filters: %s' % ' '.join(config['file_filters']))
        output('Destination base: %s' % config['destination_base'])
        output('Failed path: %s' % config['failed_path'])

        if 'output_ext' in config:
            output('Output extension: %s' % config['output_ext'])
        if subprocess.__name__ == 'subprocess32' and 'timeout' in config:
            output('Subprocess timeout: %s hours' % config['timeout'])

        output('Default call: %s' % ' '.join(filter(None, replace_values(config['call'], config['call_vars']))))


def replace_values(l, m):
    return [elem % m for elem in l]


def pick_input():
    inputpath = None
    keep_looking = True

    while keep_looking:

        keep_looking = False
        clear_my_marks()

        for base in config['incoming_paths']:
            if not os.path.exists(base):
                continue
            if verbose: output('Base: %s' % base)

            all_files = file_list(base)
            if verbose: output('All files: %s' % ' '.join(all_files))
            if len(all_files) == 0:
                continue

            in_flight = all_marked()
            if verbose: output('Currently processing: %s' % ' '.join(in_flight))

            picklist = remove_marked(all_files, in_flight)
            if len(picklist) == 0:
                continue
            if verbose: output('Available files: %s' % ' '.join(picklist))

            if 'in_order' in config and base in config['in_order']:
                inputpath = picklist[0]
                if verbose: output('Picked (in order): %s' % inputpath)
            else:
                inputpath = random.choice(picklist)
                if verbose: output('Picked (randomly): %s' % inputpath)

            mark(inputpath)
            time.sleep(random.randint(2, 10))

            duplicates = specific_marks(inputpath)
            if len(duplicates) > 1:
                inputpath = None
                keep_looking = True

            break

    return inputpath


def file_list(path):
    return sorted([f for l in [glob.glob(os.path.join(path, p)) for p in config['file_filters']] for f in l])


def remove_marked(files, in_flight):
    return [path1 for path1 in files if
            os.path.basename(path1) not in [os.path.basename(path2)[len(mark_prefix):] for path2 in in_flight]]


def clear_my_marks():
    for path in glob.glob(os.path.join(hostdir, '%s*' % mark_prefix)):
        os.remove(path)


def mark(path):
    open(os.path.join(hostdir, '%s%s' % (mark_prefix, os.path.basename(path))), 'a')


def all_marked():
    return glob.glob(os.path.join(script_dir, '*/%s*' % mark_prefix))


def specific_marks(path):
    return glob.glob(os.path.join(script_dir, '*/%s%s' % (mark_prefix, os.path.basename(path))))


def process_input(path):
    intermediate_path = determine_intermediate_path(path)
    if run_process(path, intermediate_path) == 0:
        store_result(path, intermediate_path)
        atomic_remove(path)
    else:
        output("Processing '%s' failed! Moving aside." % os.path.basename(path))
        atomic_move(path, config['failed_path'])
    clear_my_marks()


def determine_intermediate_path(path):
    filename = os.path.basename(path)
    if 'output_ext' in config:
        (name, ext) = os.path.splitext(filename)
        return os.path.join(tempfile.gettempdir(), '%s.%s' % (name, config['output_ext']))
    else:
        return os.path.join(tempfile.gettempdir(), filename)


def run_process(in_file, out_file):
    determine_parameters(in_file, out_file)

    output('Starting processing: %s' % os.path.basename(in_file))
    this_call = filter(None, replace_values(config['call'], config['call_vars']))

    if verbose:
        output('Calling: %s' % ' '.join(this_call))

    if debug:
        return 0
    else:
        stdout_path = os.path.join(hostdir, '%s.%d.stdout' % (script_name, os.getpid()))
        stdout_file = open(stdout_path, 'a', 0)
        stderr_path = os.path.join(hostdir, '%s.%d.stderr' % (script_name, os.getpid()))
        stderr_file = open(stderr_path, 'a', 0)

        if subprocess.__name__ == 'subprocess32' and 'timeout' in config:
            try:
                return subprocess.call(this_call, stdout=stdout_file, stderr=stderr_file, timeout=config['timeout']*60*60)
            except:
                return 1
        else:
            return subprocess.call(this_call, stdout=stdout_file, stderr=stderr_file)


def determine_parameters(in_file, out_file):
    global config

    config['call_vars']['input_file'] = in_file
    config['call_vars']['output_file'] = out_file

    if 'conditional_vars' in config:
        for trigger in config['conditional_vars']:
            if in_file.find(trigger) >= 0:
                for var in config['conditional_vars'][trigger]:
                    val = config['conditional_vars'][trigger][var]
                    if verbose: output("Conditional '%s': %s = %s" % (trigger, var, val))
                    config['call_vars'][var] = val


def store_result(original, intermediate):
    filename = os.path.basename(original)
    (name, ext) = os.path.splitext(filename)

    subdir = None
    if 'default_subdir' in config:
        subdir = config['default_subdir']
        if verbose: output('Default subdir: %s' % subdir)

    if 'conditional_subdir' in config:
        for trigger in config['conditional_subdir']:
            if original.find(trigger) >= 0:
                subdir = config['conditional_subdir'][trigger]
                if verbose: output('Conditional subdir: %s' % subdir)

    if subdir:
        destination_base = os.path.join(config['destination_base'], subdir)
        output('Filing into \'%s\': %s' % (subdir, name))
    else:
        destination_base = config['destination_base']
        output('Filing: %s' % name)

    show_re = re.search('^(.*?) - [sS]\d+', filename)
    season_re = re.search(' - [sS](\d+)[eE]', filename)

    if show_re is None or season_re is None:
        location = destination_base
    else:
        location = os.path.join(destination_base, show_re.group(1), 'Season %s' % season_re.group(1))

    atomic_move(intermediate, location)


def atomic_move(src, dst):
    filename = os.path.basename(src)
    tmp = find_base_writable(dst)

    if verbose:
        output('Moving %s' % src)
        output(' ..to %s' % dst)
        output(' ..through %s' % tmp)

    if not debug:
        if not os.path.exists(dst):
            os.makedirs(dst)
        shutil.move(src, tmp)
        shutil.move(os.path.join(tmp, filename), dst)


def find_base_writable(path):
    path = os.path.realpath(path)
    if not os.path.isdir(path):
        path = os.path.dirname(path)
    if os.path.exists(path) and not is_writable(path):
        raise (ValueError("Can't write to '%s'." % path))
    prev = path
    while not os.path.exists(path) or is_writable(path):
        prev = path
        path = os.path.dirname(path)
        if os.path.ismount(path):
            return path
    return prev


def is_writable(path):
    try:
        testfile = tempfile.TemporaryFile(dir=path)
        testfile.close()
    except OSError as e:
        if e.errno == errno.EACCES:
            return False
        e.filename = path
        raise
    return True


def atomic_remove(path):
    if verbose:
        output('Removing: %s' % path)

    if not debug:
        os.remove(path)


def parse_commandline():
    global debug
    global verbose

    try:
        opts, args = getopt.getopt(sys.argv[1:], '', ['debug', 'verbose'])
    except getopt.GetoptError as err:
        output(str(err))
        sys.exit(1)

    for o, a in opts:
        if o == '--debug':
            debug = True
            verbose = True
        if o == '--verbose':
            verbose = True

    return args


def hostname():
    return socket.gethostname().split('.')[0]


def setup_locking(block=True):
    global lockfile

    lockfile_path = os.path.join(tempfile.gettempdir(), 'process_queue')
    lockfile = open(lockfile_path, 'a', 0)

    if block:
        portalocker.lock(lockfile, portalocker.LOCK_EX)
    else:
        try:
            portalocker.lock(lockfile, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.LockException:
            sys.exit(0)


def init_logfile():
    global logfile
    global script_name

    script_file = os.path.basename(script_path)
    (script_name, ext) = os.path.splitext(script_file)

    if not os.path.exists(hostdir):
        os.makedirs(hostdir)

    if not debug:
        logfile_path = os.path.join(hostdir, '%s.%d.log' % (script_name, os.getpid()))
        logfile = open(logfile_path, 'a', 0)


def output(msg):
    if not logfile:
        init_logfile()

    stamped_msg = '[%s] %s' % (time.strftime('%x %X'), msg)

    if not logfile:
        print stamped_msg
    else:
        logfile.write('%s\n' % stamped_msg.encode('ascii', 'replace'))


if __name__ == '__main__':
    main()
