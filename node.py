# Copyright (c) 2015 Puget Sound Regional Council, Seattle WA USA
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# This script manages model runs on a server by communicating with the PSRC Model Dashboard.
# It must be running for models runs to be initiated remotely.
#
# ===========================
import os
import Pyro4
import time
import subprocess
import sys
import socket
import select
import threading
import shutil
import logging
import requests

logger = logging.getLogger(socket.gethostname())

class Node(object):
    busy = False
    command = None
    p = None
    cwd = None
    returncode = -1
    run_id = None

    def __init__(self):
        self.name = socket.gethostname()
        logger.info('##############################################')
        logger.info('i am: '+self.name)
        logger.info('working dir: '+os.getcwd())


    def is_busy(self):
        return self.busy


    def is_available(self):
        return not self.busy


    def create_dir(self, path, subdir=None):
        '''
        Create a directory, with optional subdirectory
        '''
        fullpath = path
        if subdir:
            fullpath = os.path.join(path, subdir)

        try:
            os.makedirs(fullpath)
        except OSError as exc: # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(fullpath):
                pass
            else: raise


    def kill(self):
        '''
        Kill a running command, if there is one
        '''
        if self.p:
            logger.info('terminating: '+str(self.command))
            self.p.terminate()
        else:
            logger.info('nothing to terminate.')


    def status(self):
        '''
        Get node status
        Returns tuple: (returncode, busy, command, working_dir)
        returncode=-1 if process has not returned yet
        '''
        return (self.returncode, self.busy, self.command, self.cwd)


    def runscript(self, lines, project, series, cwd=None, run_id=None):
        '''
        Take a list of script lines, and run them
        '''
        self.create_dir(project, series)
        for line in lines:
            if line.startswith('::'): continue
            if len(line.strip())==0: continue
            logger.info('RUN: '+line)
            self.runandwait(line, cwd, run_id)
            if self.returncode>0:
                logger.error('ERR ' + str(returncode))
                break
            pass


    def runandwait(self, command, cwd=None, run_id=None):
        '''
        Spawn a subprocess. Wait for task to finish, and return the process returncode.
        '''
        logger.info("runandwait: run_id is " + str(run_id))
        self.start(command, cwd, wait=True, run_id=run_id)


    def start(self, command, cwd=None, wait=False, run_id=None):
        '''
        Spawn a subprocess. Return immediately.
        '''
        if self.busy:
            logger.error('# Already busy, running: '+str(command))
            raise RuntimeError("Already busy")
            return

        logger.info('----------------------------------------------')
        logger.info('received command: '+str(command))
        logger.info("start: run_id is " + str(run_id))

        self.busy = True
        self.command = command
        self.cwd = cwd
        self.returncode = -1
        self.run_id=run_id

        # Launch the process, and save a handle to it in self.p
        self.popenAndCall(self.onExit, command, cwd, wait)


    def onExit(self, returncode):
        """
        Callback function which is run when a subprocess is completed.
        Resets busy flag and gets node ready for the next run.
        """
        logger.info("ON-EXIT: return code "+ str(returncode) + " : " + str(self.command))

        self.returncode = returncode
        self.busy = False
        self.p = None
        self.command = None
        self.cwd = None

        # Update run log with status
        if self.run_id:
            data = {'status': returncode}
            url = 'http://localhost/runlog/'+str(self.run_id)
            logger.info(url)
            response = requests.get(url, params=data)

            logger.info('updated status: response ' + str(response))

        if (returncode>0):
            raise RuntimeError('Failed: return code '+str(returncode))


    def popenAndCall(self, onExit, command, cwd, wait):
        """
        Runs the given args in a subprocess.Popen, and then calls the function
        onExit when the subprocess completes.
        onExit is a callable object, and popenArgs is a list/tuple of args that
        would give to subprocess.Popen.
        """
        def runIt(onExit, command):
            rtncode = -1

            # Put log files in cwd folder
            pout = 'stdout.log'
            if cwd:
                pout = os.path.join(cwd, pout)

            try:
                with open(pout, 'a') as file_out:
                    self.p = subprocess.Popen(command, cwd=cwd, stdout=file_out, stderr=subprocess.STDOUT)
                    self.p.wait()
                    rtncode = self.p.returncode
            except:
                rtncode = 8
            finally:
                onExit(rtncode)

        if wait:
            runIt(onExit, command)
        else:
            thread = threading.Thread(target=runIt, args=(onExit, command))
            thread.start()


def runtests():
    n = Node()

    cmd = ["ipconfig.exe"]
    n.start(cmd, r"c:\users\zbilly")
    time.sleep(1)
    print n.status()
    n.start(cmd)
    time.sleep(1)
    n.kill()

def set_high_priority():
    '''
    Run node code at extra-high priority, so it stays responsive even
    while models are running.
    '''
    import platform
    if platform.system()=='Windows':
        print 'Setting Windows process priority'
        import win32api, win32process, win32con
        pid = win32api.GetCurrentProcessId()
        handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
        win32process.SetPriorityClass(handle, win32process.HIGH_PRIORITY_CLASS)


def setup_logger():
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler('node.log')
    fh.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s/%(name)s %(levelname)s %(message)s')

    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)


def main():
    set_high_priority()
    setup_logger()

    # Start Pyro -- requires one Pyro Name server on network somewhere
    n = Node()
    try:
        Pyro4.Daemon.serveSimple({ n : n.name } , host=n.name, ns=True)
    except:
        print('\n###\nNo Pyro name server found on local network.')
        print("To start a Pyro Name Server, do 'pyro4-ns.exe -n [hostname]'")


if __name__ == '__main__':
    #runtests()
    main()
