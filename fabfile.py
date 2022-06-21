from fabric.api import *
from fabric.decorators import hosts, parallel, serial
import fabric.contrib.files
from fabric.operations import reboot
import time
import psutil
import os
import logging
#Disable annoyting log messages.
logging.basicConfig(level=logging.ERROR)

#This makes the paramiko logger less verbose
para_log=logging.getLogger('paramiko.transport')
para_log.setLevel(logging.ERROR)

env.keepalive = True

env.roledefs = {
        'hypervisors': ['maxim@stream1','maxim@stream2', 'maxim@stream3'],
        'brinst': ['maxim@stream28'],
}

hostvms = { 'maxim@stream1' : ['controller'],
        'maxim@stream2' :  ['network'],
        'maxim@stream3' :  ['compute'],
}

###VM MANAGEMENT###
@roles('hypervisors')
def definevms():
    vm = hostvms[env.host_string][0]
    run('virsh define ' + 'qemu/qemu' + env.host_string.split('stream')[1] + '/'+ vm + '.xml')  

@roles('hypervisors')
def undefinevms():
    vm = hostvms[env.host_string][0]
    run('virsh undefine '+ vm) 

@roles('hypervisors')
def startvms():
    vm = hostvms[env.host_string][0]
    with settings(warn_only=True):
        run('virsh start ' + vm)

@roles('hypervisors')
def stopvms():
    vm = hostvms[env.host_string][0]
    with settings(warn_only=True):
        run('virsh shutdown ' + vm)


#####KVM INSTALLATION#####
#@roles('hypervisors')
def installkvm():
    with settings(warn_only=True):
        sudo("apt-get install -y kvm qemu-kvm libvirt-bin virtinst", pty=True)
        sudo("adduser maxim libvirtd", pty=True)
        sudo("adduser maxim kvm", pty=True)

def removekvm():
    with settings(warn_only=True):
        sudo("apt-get remove  -y kvm qemu-kvm libvirt-bin virtinst", pty=True)


#####TIME MANAGEMENT#####
#@roles('hypervisors')
def installntpserver():
    with settings(warn_only=True):
        sudo("apt-get install -y ntp")

def removentpserver():
    with settings(warn_only=True):
        sudo("apt-get remove -y ntp")

@roles('hypervisors')
def addbridge():
    sudo('apt-get install -y bridge-utils')
    sudo('cp /etc/network/interfaces /etc/network/interfaces.old')
    put('templates/interfaces.dhcpbr0', '/tmp/interfaces')
    sudo('cp /tmp/interfaces /etc/network/interfaces')
    with settings(warn_only=True):
        reboot()

@roles('hypervisors')
def delbridge():
    sudo('cp /etc/network/interfaces.old /etc/network/interfaces')
    sudo('rm /etc/network/interfaces.old')
    with settings(warn_only=True):
        run('rm /tmp/interfaces')
    with settings(warn_only=True):
        reboot()


@roles('hypervisors')
def preparehost():
    execute(installkvm)
    execute(installntpserver)


@roles('hypervisors')
def getdefaulthost():
    execute(removekvm)
    execute(removentpserver)
    sudo("apt-get autoremove -y ")
