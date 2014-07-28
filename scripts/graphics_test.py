#!/usr/bin/env python

import optparse
import sys
import os
import shutil
import datetime
import time
import traceback
import multiprocessing
import subprocess
import string
import commands

from jenkins_setup import common, rosdep, cob_pipe

class Timeout(Exception):
    pass
  
def run(command, timeout=10):
    proc = subprocess.Popen(command, bufsize=0, shell=True)
    poll_seconds = 1
    deadline = time.time()+timeout
    while time.time() < deadline and proc.poll() == None:
        time.sleep(poll_seconds)

    if proc.poll() == None:
        proc.terminate()
        raise Timeout()

    stdout, stderr = proc.communicate()
    return stdout, stderr, proc.returncode  
    
  
def analyse():
    bagfs = string.split(commands.getoutput("ls $BAG_PATH | grep \".bag$\""), "\n")
    for bagf in bagfs:
        com_ana = "roslaunch navigation_test_analysis analyse_bag_file.launch filepath:=$BAG_PATH/" + bagf
        (st, ou) =  commands.getstatusoutput(com_ana)
        print "Output: " + str(ou)	
        if st is 0:
            print "SUCCESSFULLY ANALYZED " + bagf
        else:
            raise ValueError('returned value is: ' + str(ou))
  
      
def main():
    #########################
    ### parsing arguments ###
    #########################
    print "=====> WORKAROUND INSTALLATION ..."
    common.call("sudo apt-get install -y python-numpy python-scipy python-matplotlib python-pygraphviz python-tk ros-hydro-controller-manage* ros-hydro-joint-* ros-hydro-desktop-full ros-hydro-gazebo-ros-control ros-hydro-ros-control")
    time_parsing = datetime.datetime.now()
    print "=====> entering argument parsing step at", time_parsing

    # parse parameter values
    parser = optparse.OptionParser()
    parser.add_option('-v', '--verbose', action='store_true', default=False)
    (options, args) = parser.parse_args()

    if len(args) < 5:
        print "Usage: %s pipeline_repos_owner server_name user_name ros_distro build_repo" % sys.argv[0]
        raise common.BuildException("Wrong arguments for build script")

    # get arguments
    pipeline_repos_owner = args[0]
    server_name = args[1]
    user_name = args[2]
    ros_distro = args[3]
    build_identifier = args[4]                      # repository + suffix
    build_repo = build_identifier.split('__')[0]    # only repository to build
    # environment variables
    workspace = os.environ['WORKSPACE']

    # cob_pipe object
    cp_instance = cob_pipe.CobPipe()
    cp_instance.load_config_from_file(pipeline_repos_owner, server_name, user_name, file_location=os.environ["WORKSPACE"])
    pipe_repos = cp_instance.repositories
    common.output("Pipeline configuration successfully loaded", blankline='b')

    # (debug) output
    print "\n", 50 * 'X'
    print "\nTesting on ros distro: %s" % ros_distro
    print "Testing repository: %s" % build_repo
    if build_repo != build_identifier:
        print "       with suffix: %s" % build_identifier.split('__')[1]
    print "Using source: %s" % pipe_repos[build_identifier].url
    print "Testing branch/version: %s" % pipe_repos[build_identifier].version
    print "\n", 50 * 'X'

    # set up directories variables
    tmpdir = '/tmp'
    repo_sourcespace = os.path.join(tmpdir, 'src')                                 # location to build repositories in
    repo_sourcespace_wet = os.path.join(repo_sourcespace, 'wet', 'src')            # wet (catkin) repositories
    repo_sourcespace_dry = os.path.join(repo_sourcespace, 'dry')                   # dry (rosbuild) repositories
    repo_test_results = os.path.join(tmpdir, 'test_results')                       # location for test results
    if not os.path.exists(repo_test_results):
        os.makedirs(repo_test_results)
    repo_build_logs = os.path.join(tmpdir, 'build_logs')                           # location for build logs

    # source wet and dry workspace
    ros_env_repo = common.get_ros_env(repo_sourcespace + '/setup.bash')
    ros_env_repo['ROS_TEST_RESULTS_DIR'] = repo_test_results

    ############
    ### test ###
    ############
    time_test = datetime.datetime.now()
    print "=====> entering testing step at", time_test

    # get amount of cores available on host system
    cores = multiprocessing.cpu_count()

    # get current repository name    
    user, repo_name = cp_instance.split_github_url(pipe_repos[build_identifier].data['url'])

    ### catkin repositories
    (catkin_packages, stacks, manifest_packages) = common.get_all_packages(repo_sourcespace_wet)
    if (len(catkin_packages) > 0) and (repo_name in catkin_packages):
        # get list of dependencies to test
        test_repos_list_wet = []

        # add all packages in main repository
        (catkin_test_packages, stacks, manifest_packages) = common.get_all_packages(catkin_packages[repo_name] + '/..')
        for pkg_name, pkg_dir in catkin_test_packages.items():
            test_repos_list_wet.append(pkg_name)

        # add all packages in dep repositories (if "test" is set to True)
        for dep in pipe_repos[build_identifier].dependencies.keys():
            if pipe_repos[build_identifier].dependencies[dep].test:
                (catkin_test_dep_packages, stacks, manifest_packages) = common.get_all_packages(catkin_packages[dep] + '/..')
                for pkg_name, pkg_dir in catkin_test_dep_packages.items():
                    test_repos_list_wet.append(pkg_name)

        print "Testing the following wet repositorie %s" % build_repo#test_repos_list_wet
        print "SOME PACKAGE LISTS:"
        print "test_repos_list_wet: %s" % test_repos_list_wet
        print "build_repo: %s" % build_repo
        print "ros_env_repo: %s" % ros_env_repo
        print "repo_sourcespace: %s" % repo_sourcespace
        try:
            test_list = ' '.join( test_repos_list_wet )
            print "test_list: %s" % test_list
            common.call("catkin_make --directory %s/wet run_tests_%s" % (repo_sourcespace, build_repo))
        except common.BuildException as ex:
            print ex.msg
            raise common.BuildException("Failed to catkin_make test wet repositories")

        # clean and copy test xml files
        common.clean_and_copy_test_results(repo_sourcespace + "/wet/build/test_results", workspace + "/test_results") # FIXME: is there a way to let catkin write test results to repo_test_results

    ### rosbuild repositories
    (catkin_packages, stacks, manifest_packages) = common.get_all_packages(repo_sourcespace_dry)
    if (len(stacks) > 0) and (repo_name in stacks):
        # get list of dependencies to test
        test_repos_list_dry = [build_repo]
        for dep, depObj in pipe_repos[build_identifier].dependencies.items():
            if depObj.test and dep in stacks:
                test_repos_list_dry.append(dep)

        # test dry repositories
        print "Test the following dry repositories %s" % test_repos_list_dry
        try:
            build_list = " ".join(test_repos_list_dry)
            common.call("rosmake -rV --skip-blacklist --profile --pjobs=%s --test-only --output=%s %s" %
                        ( cores, repo_build_logs, build_list ), ros_env_repo)
        except common.BuildException as ex:
            print ex.msg
            raise common.BuildException("Failed to rosmake test dry repositories")

        # clean and copy test xml files
        common.clean_and_copy_test_results(repo_test_results, workspace + "/test_results")
        
    # in case we have no tests executed (neither wet nor dry), we'll generate some dummy test result
    common.clean_and_copy_test_results(repo_test_results, workspace + "/test_results")

    ################
    ### Analysis ###
    ################
    time_ana = datetime.datetime.now()
    print "=====> entering analysis step at", time_ana

    path_video = "$WORKSPACE/videoFiles"

    com_folder = "mkdir -p " + path_video
    common.call(com_folder)
   
    print "Files in $BAG_PATH:"
    print common.call(os.path.expandvars("ls -al $BAG_PATH"))
   
    analyse()

    print "=====> making images"
    com_pix = "rosrun navigation_test_analysis simple_viewer.py AUTO"
    common.call(com_pix)

    ###########
    ### end ###
    ###########
    # steps: parsing, test, analysis
    time_finish = datetime.datetime.now()
    print "=====> finished script at", time_finish
    print "durations:"
    print "parsing arguments in       ", (time_test - time_parsing)
    print "test in                    ", (time_ana - time_test)
    print "analysis in                ", (time_finish - time_ana)
    print "total                      ", (time_finish - time_parsing)
    print ""
 
    # Trying to fix: Deleting project workspace... Cannot delete workspace: java.io.IOException: Unable to delete 
    common.call("sudo rm -rf $WORKSPACE/test_results/*")

if __name__ == "__main__":
    # global try
    try:
        main()
        print "Test script finished cleanly!"

    # global catch
    except (common.BuildException, cob_pipe.CobPipeException) as ex:
        print traceback.format_exc()
        print "Test script failed!"
        print ex.msg
        raise ex

    except Exception as ex:
        print traceback.format_exc()
        print "Test script failed! Check out the console output above for details."
        raise ex
