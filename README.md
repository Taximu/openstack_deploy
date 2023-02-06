![Alt text](https://ruvds.com/wp-content/uploads/2021/04/Selection_011.png)

## What is the purpose of this repo?
It is an automated installation of Openstack platform. For more information please see:
https://cloudpenguin.blogspot.com/2015/05/experience-with-ubuntuopenstack.html

## Install Ubuntu Server 14.04.1 64-bit

## Setup for development
    cd /root && git clone https://github.com/Taximu/openstack_deploy.git && sudo apt-get install -y fabric
## Setup for deploy/testing
    ssh ubuntu@controller && cd root/openstackdeploy/deploy && fab <openstack_launch_deploy> || fab <function_name>
