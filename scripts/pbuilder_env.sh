#!/bin/bash

export WORKSPACE=$1

. $WORKSPACE/env_vars.sh

. /opt/ros/$ROSDISTRO/setup.bash

export PATH=$PATH:/usr/local/bin
export PYTHONPATH=$WORKSPACE/jenkins_setup/src:$PYTHONPATH

export HOME="/root"
chmod go-rw $WORKSPACE/.ssh/authorized_keys
chmod go-rw $WORKSPACE/.ssh/id_rsa
cp -a $WORKSPACE/.ssh /root &&
chown -R root.root /root/.ssh
if [ $? != 0 ]; then
    echo "Could not successfully set up ssh"
    exit 1
fi

case $JOBTYPE in
    regular_graphics_test|prio_graphics_test)
        echo "Set up graphic" # TODO: this step takes a long time, can we shorten it? Maybe move some parts into the initial generation of the chroot tarballs?

        export DIR=$WORKSPACE/jenkins_setup/scripts/graphicTest/chroot
        $DIR/checkDisplayNull.bash &&
        $DIR/setupSources.bash &&
        $DIR/../tvnc/installTurboVNC.bash &&
        $DIR/../vgl/installVirtualGL.bash &&
        $DIR/distUpgrade.bash &&
        $DIR/installNvidia.bash &&
        $DIR/setupOGRE.bash
        if [ $? != 0 ]; then
            echo "Could not successfully prepare chroot"
            exit 1
        fi

        $DIR/remoteX.py start
        if [ $? != 0 ]; then
            echo "Could not start remote X server"
            exit 1
        fi
        export DISPLAY=`cat /tmp/vncDisplay`
        echo "Using Display $DISPLAY. Start vncviewer to see the X environment: vncviewer $HOSTNAME$DISPLAY"
        ;;
esac

echo
echo "==============================================="
echo "==== Begin script. Ignore the output above ===="
echo "==============================================="

echo "CALLING: >>"$WORKSPACE"/jenkins_setup/scripts/"${JOBTYPE}".py "$PIPELINE_REPOS_OWNER" "$JENKINS_MASTER" "$JENKINS_USER" "$ROSDISTRO" "$REPOSITORY" <<"

nice -n19 ionice -c2 -n7 python $WORKSPACE/jenkins_setup/scripts/${JOBTYPE}.py $PIPELINE_REPOS_OWNER $JENKINS_MASTER $JENKINS_USER $ROSDISTRO $REPOSITORY
result=$?

case $JOBTYPE in
    regular_graphics_test|prio_graphics_test)
        if [ ! -z "$DISPLAY" ] && [ "$DISPLAY" != ":0" ]; then
            $DIR/remoteX.py stop
        fi
        ;;
esac

echo "==============================================="
echo "==== End script. Ignore the output below ======"
echo "==============================================="
exit $result
