#!/opt/anaconda/bin/python

import os
import os.path
import re
import sys
import shutil

from subprocess import Popen, PIPE, check_output

env = os.environ
dstdir = None
dummy = False
demfile = None

idl_bin = '/usr/local/bin/idl'

if env['USER'] == 'mapred':
    # env['TMPDIR'] = '/tmp/mapred-soilfrost/'
    env['LM_LICENSE_FILE'] = '1700@idl.terradue.int'

    import cioppy
    ciop = cioppy.Cioppy()
    def LOGINFO(x): ciop.log("INFO", "CP:" + x)
    def LOGERROR(x): ciop.log("ERROR", "CP:" + x)
    LOGINFO(" Using Cioppy tools")
    def copy(url, dst):
        LOGINFO("Copying <{0}> to <{1}>".format(url, dst))
        return ciop.copy(url, dst, extract=False)
    getparam = ciop.getparam
    def no_publish(pths):
        if isinstance(pths, basestring):
            pths = [pths]
        for pth in pths:
            LOGINFO("Publishing path " + pth)
            ciop.publish(pth, metalink=False)
    publish = ciop.publish
    permadir = '/data/public'
    bindir = '/application/soilfrost/bin'
else:
    def LOGINFO(x): print("[INFO]CP:" + x)
    params = {
        'startdate' : '2000-07-02',
        'enddate'   : '2525-08-05',
    }
    def getparam(x): return params[x]
    def copy(pths, dst): 
        if not os.path.isdir(dst):
            raise RuntimeError("copy: dst must be directory")
        if isinstance(pths, basestring):
            pths = [pths]
        for pth in pths:
            dpth = os.path.join(dst, os.path.basename(pth))
            LOGINFO("Copying <{0}> to <{1}>".format(pth, dpth))
            if not dummy:
                # shutil.copy(pth, dpth)
                if not os.path.exists(dpth):
                    os.symlink(pth, dpth)
        return "".join(["[INFO   ][shutil.copy][done] url '{0}' > local '{1}'"\
                .format(pth, os.path.join(dst, os.path.basename(pth))) for pth in pths])
    def publish(pths, **kwargs):
        if 'recursive' in kwargs:
            pths = [os.path.join(pths, x) for x in os.listdir(pths)]
        if isinstance(pths, basestring):
            pths = [pths]
        for pth in pths:
            LOGINFO("Publishing path " + pth)
    permadir = os.path.join(env['HOME'], 'src/s3/soilfrost/permanent')
    bindir = os.path.join(env['HOME'], 'src/s3/soilfrost/bin')

def p_copy(url, dstdir):
    from glob import glob
    if url[0] == '/' or url[:4] == 'file':
        res = copy(url, dstdir)
    else:
        if env['USER'] == 'mapred':
            # anything complex may (for now) have to go through a call to opensearch-client
            url = check_output(['opensearch-client', url, 'enclosure'])
            url = url.rstrip(' \n')
            LOGINFO("Getting data from <{}>".format(url))
            res = copy(url, dstdir)
            # rr = glob(res + '/*.SAFE')
            # if len(rr) > 1: raise ValueError("Not sure how this happens")
            # if len(rr) == 1: res = rr

    if res[-4:] == '.zip':
        LOGINFO("Unpacking " + res)
        out = check_output(['unzip', res, '-d', dstdir])
        m = re.search(r"creating: ([\w/.-]+.SAFE)/", out)
        if not m: raise ValueError("unexpected output from unzip: <" + out + ">")
        os.unlink(res)
        res = m.group(1)
        LOGINFO("Unpacked to " + res)
        return res
    try:
        m = re.search(r"\[done\] url '([^']+)' > local '([^']+)'", res)
        if m is None: raise ValueError("Unexpected output from copy: " + res)

        return m.group(2)
    except ValueError:
        return res

def safe_getparam(x, default):
    try:
        rval = getparam(x)
    except:
        return default
    return rval

def mkdir_p(path):
    try:
        junk = os.listdir(path)
    except OSError:
        head, tail = os.path.split(path)
        mkdir_p(head)
        os.mkdir(path)

def cleandir(dir):
    for name in os.listdir(dir):
        pth = os.path.join(dir, name)
        try:
            shutil.rmtree(pth)
        except OSError:
            os.unlink(pth)


def cluster_main():

    global dstdir, demfile

    startdate = safe_getparam('startdate', '2014-04-01')
    enddate   = safe_getparam('enddate',   '2014-04-01')
    pixelsize = safe_getparam('pixelsize', None)
    if demfile is None:
        # demfile   = safe_getparam('demfile',  'S3_dem_geoid_correction_already_applied.tiff')
        demfile   = safe_getparam('demfile',  'S3_dem_10m_geoid_correction_already_applied.tiff')

    if 'TMPDIR' not in env: env['TMPDIR'] = '/var/tmp'

    srcdir = os.path.join(env['TMPDIR'], 'inputs')

    if dstdir is None:
        dstdir = os.path.join(env['TMPDIR'], 'outputs')

    mkdir_p(srcdir)
    mkdir_p(dstdir)
    cleandir(srcdir)
    cleandir(dstdir)

    if len(os.path.split(demfile)[0]) == 0: demfile = os.path.join(permadir, demfile)

    cwd = None
    if True:                    # env['USER'] in [ 'mapred', 'sensyf-s3' ] or '-s' in sys.argv:
        LOGINFO("Running geocoding from .sav file")
        savfile = os.path.join(bindir, 'geocode_main.sav')
        cmd_args = [idl_bin, '-rt=' + savfile, '-args', demfile, dstdir]
    else:                       # doesn't work 
        print "Running geocoding from .pro file"
        cwd = os.path.join(env['HOME'], 'src/SenSyF/S3/src/')
        cmd_args = ['idl', '-e', 'geocode_main', '-args', demfile, dstdir]

    if pixelsize:
        cmd_args.append('-p{0}'.format(pixelsize))

    idl = Popen(cmd_args, cwd=cwd, stdin=PIPE)
    # idl = Popen(['cat'], cwd=cwd, stdin=PIPE)
    
    sys.stdin.flush()
    # for line in sys.stdin:
    while 1:
        line = sys.stdin.readline()
        if len(line) == 0: break
        url = line.rstrip(' \n/')
        if len(url) == 0: continue
        LOGINFO("Got input line <{0}>".format(url))
        parts = url.split(';')
        if len(parts) == 0:
            stop
        elif len(parts) == 1:
            grd = p_copy(url, srcdir)
            idl.stdin.write(grd + "\n")
            LOGINFO("Passed line <{0}> to IDL".format(grd))
        else:
            grds = [p_copy(url, srcdir) for url in parts]
            idl.stdin.write(':'.join(grds) + "\n")
            LOGINFO("Passed line <{0}> to IDL".format(':'.join(grds)))
        sys.stdout.flush()

        idl.stdin.flush()
        sys.stdin.flush()
        sys.stdout.flush()

    idl.stdin.close()
    if idl.wait() != 0:
        print "IDL closed with error"

    for product in os.listdir(dstdir):
        pname = os.path.join(dstdir, product) + '.tgz'
        out = check_output(['/bin/tar', 'zcvf', pname, '-C', dstdir, product])
        publish(pname, metalink=False)




if __name__ == "__main__":

    while len(sys.argv) > 1:
        arg = sys.argv.pop(1)
        if arg == '-d':
            dummy = True
            continue
        if arg == '-o':
            dstdir = sys.argv.pop(1)
            continue
        if arg == '-dem':
            demfile = sys.argv.pop(1)
            continue
        print 'Unknown option ' + arg

    cluster_main()


