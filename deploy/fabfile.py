from fabric.api import *
from fabric.decorators import hosts, parallel, serial
from fabric.contrib.files import append
from fabric.operations import reboot
from fabric.context_managers import shell_env
import time
import psutil
import os
import logging
#Disable annoyting log messages.
logging.basicConfig(level=logging.ERROR)

#This makes the paramiko logger less verbose
para_log=logging.getLogger('paramiko.transport')
para_log.setLevel(logging.ERROR)


env.roledefs = {

    'controller': ['ubuntu@10.6.1.8'],
    'network': ['ubuntu@10.7.5.9'],
    'compute': ['ubuntu@10.7.5.1'],
	'hypervisors': ['maxim@stream1', 'maxim@stream2', 'maxim@stream3'],
    'localmachine': ['maxim@10.6.1.4'],
    'desktop': ['localhost']
}

hostvms = { 'maxim@stream1' : ['controller'],
        'maxim@stream2' :  ['network'],
        'maxim@stream3' :  ['compute'],
}

###PASSWDS

dbmysqlroot = ''
RABBIT_PASS = ''
KEYSTONE_DBPASS = ''
ADMIN_TOKEN = ''
ADMIN_PASS = ''
ADMIN_EMAIL = ''
DEMO_PASS =  ''
DEMO_EMAIL = ''
GLANCE_DBPASS = ''
GLANCE_PASS = ''
EMAIL_ADDRESS = ''
NOVA_DBPASS = ''
NOVA_PASS = ''
NEUTRON_DBPASS = ''
NEUTRON_PASS = ''

###NETWORKS IP'S
FLOATING_IP_START = ''
FLOATING_IP_END = ''
EXTERNAL_NETWORK_GATEWAY = ''
EXTERNAL_NETWORK_CIDR = ''
TENANT_NETWORK_GATEWAY = ''
TENANT_NETWORK_CIDR = ''

################## 1 BASIC ENVIRONMENT#################

@roles('controller', 'network', 'compute')
def addnopasswd():
    append('/etc/sudoers', '%clustersudo ALL=(ALL) NOPASSWD:ALL', use_sudo=True)
    sudo('groupadd clustersudo')
    sudo('sudo adduser ubuntu clustersudo')


@roles('controller', 'network', 'compute')
def configurehosts():
    #print env.host_string
    for role in env.roledefs:
        #print env.roledefs[role]
        if env.host_string in env.roledefs[role]:
            print env.host_string, role
            put('templates/'+role+'/hosts', "/tmp/hosts")
            sudo('mv /tmp/hosts /etc/hosts')
            put('templates/'+role+'/hostname', "/tmp/hostname")
            sudo('mv /tmp/hostname /etc/hostname')
            sudo('service hostname restart')
            put('templates/'+role+'/interfaces.new', "/tmp/interfaces.new")
            sudo('mv /tmp/interfaces.new /etc/network/interfaces')
            with settings(warn_only=True):
                reboot()

###ADD###

@roles('controller', 'network', 'compute')
def installntpserver():
    with settings(warn_only=True):
        sudo("apt-get install -y ntp")

@roles('controller')
def installmysqlandconfigure():
    with settings(warn_only=True):
        run('sudo echo mysql-server-5.5 mysql-server/root_password password '+ dbmysqlroot +' | sudo debconf-set-selections')
        run('sudo echo mysql-server-5.5 mysql-server/root_password_again password '+ dbmysqlroot +' | sudo debconf-set-selections')
        sudo("apt-get install -y mysql-server")
        put('templates/controller/my.cnf', "/tmp/my.cnf")
        sudo('mv /tmp/my.cnf /etc/mysql/my.cnf')
        sudo('service mysqld restart')
        sudo('mysql_install_db')
        sudo('mysql_secure_installation')

@roles('network', 'compute', 'controller')
def installmysqlclient():
    with settings(warn_only=True):
        sudo("apt-get install -y python-mysqldb")

@serial
def installdb():
    execute(installmysqlandconfigure)
    execute(installmysqlclient)

@roles('controller')
def installmsgbroker():
    with settings(warn_only=True):
        sudo("apt-get install -y rabbitmq-server")
        sudo("rabbitmqctl change_password guest " + RABBIT_PASS)

###REMOVE###

@roles('controller', 'network', 'compute')
def removentpserver():
    with settings(warn_only=True):
        sudo("apt-get remove -y ntp")

@roles('controller')
def removemysqlserver():
    with settings(warn_only=True):
        sudo("apt-get remove -y mysql-server")
        sudo("apt-get autoremove -y")

@roles('controller', 'network', 'compute')
def removemysqlclient():
    with settings(warn_only=True):
        sudo("apt-get remove -y python-mysqldb")
        sudo("apt-get autoremove -y")

@serial
def removedb():
    execute(removemysqlserver)
    execute(removemysqlclient)

@roles('controller')
def removemsgbroker():
    with settings(warn_only=True):
        sudo("apt-get remove -y rabbitmq-server")

################## 2 CONFIGURE IDENTITY SERVICE #################


###HELPER FUNCTION####
def mysql_admin(user, password, command):
    """Runs a mysql command without specifying which database to run it on.
Badly named."""
    run('mysql --default-character-set=utf8 -u%s -p%s -e "%s"' % (
        user,
        password,
        command,
    ))
######################


###ADD###

@roles('controller')
def installkeystone():
    with settings(warn_only=True):
        sudo('apt-get update') 
        sudo("apt-get install -y keystone")
        put('templates/controller/keystone.conf', "/tmp/keystone.conf")
        sudo('mv /tmp/keystone.conf /etc/keystone/keystone.conf')
        sudo('rm /var/lib/keystone/keystone.db')
        mysql_admin('root', dbmysqlroot, 'CREATE DATABASE keystone;')
        mysql_admin('root', dbmysqlroot, "GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'localhost' IDENTIFIED BY '"+ KEYSTONE_DBPASS +"';")
        mysql_admin('root', dbmysqlroot, "GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'%' IDENTIFIED BY '"+ KEYSTONE_DBPASS +"';")
        sudo('su -s /bin/sh -c "keystone-manage db_sync" keystone')
        sudo('service keystone restart')
        sudo("(crontab -l -u keystone 2>&1 | grep -q token_flush) || echo '@hourly /usr/bin/keystone-manage token_flush >/var/log/keystone/keystone-tokenflush.log 2>&1' >> /var/spool/cron/crontabs/keystone")


@roles('controller')
def defineuserstenantsandroles():
    with shell_env(OS_SERVICE_TOKEN=ADMIN_TOKEN, OS_SERVICE_ENDPOINT='http://controller:35357/v2.0'):
        ##Create an administrative user
        sudo('keystone user-create --name=admin --pass='+ADMIN_PASS+' --email='+ADMIN_EMAIL)        
        sudo('keystone role-create --name=admin')
        sudo('keystone tenant-create --name=admin --description="Admin Tenant"')
        sudo('keystone user-role-add --user=admin --tenant=admin --role=admin')
        sudo('keystone user-role-add --user=admin --role=_member_ --tenant=admin')
        ##Create a normal user
        sudo('keystone user-create --name=demo --pass='+DEMO_PASS+' --email='+DEMO_EMAIL)
        sudo('keystone tenant-create --name=demo --description="Demo Tenant"')
        sudo('keystone user-role-add --user=demo --role=_member_ --tenant=demo')
        ##Create a service tenant
        sudo('keystone tenant-create --name=service --description="Service Tenant"')
        ##Define services and API endpoints
        sudo('keystone service-create --name=keystone --type=identity  --description="OpenStack Identity"')
        output = run('keystone service-list | awk "/ identity / {print $2}"')
        SERVICEID = output.split('|')[1].strip()
        print SERVICEID
        sudo('keystone endpoint-create   --service-id='+SERVICEID+'   --publicurl=http://controller:5000/v2.0   --internalurl=http://controller:5000/v2.0   --adminurl=http://controller:35357/v2.0')
    ##Verify the Identity Service installation        
    run('keystone --os-username admin  --os-tenant-name admin --os-password '+ADMIN_PASS+' --os-auth-url http://controller:35357/v2.0 token-get')
    #Verify that authorization behaves as expected
    run('keystone --os-username admin --os-password '+ADMIN_PASS+' --os-tenant-name admin --os-auth-url http://controller:35357/v2.0 tenant-list')
    #set environment variables
    append('~/.bashrc', 'export OS_USERNAME=admin')
    append('~/.bashrc', 'export OS_PASSWORD='+ADMIN_PASS)
    append('~/.bashrc', 'export OS_TENANT_NAME=admin')
    append('~/.bashrc', 'export OS_AUTH_URL=http://controller:35357/v2.0')
        ##run('keystone token-get') does not work with fabric run next line
    with shell_env(OS_USERNAME='admin', OS_PASSWORD=ADMIN_PASS, OS_TENANT_NAME='admin', OS_AUTH_URL='http://controller:35357/v2.0'):
        run('keystone token-get')
        run('keystone user-list')
        run('keystone user-role-list --user admin --tenant admin')

###REMOVE###


@roles('controller')
def removekeystone():
    with settings(warn_only=True):
        sudo("apt-get remove -y keystone")

################## 3 INSTALL AND CONFIGURE OPENSTACK CLIENTS  #################

###ADD###
@roles('desktop')
def installopenstackclients():
    sudo('apt-get update')
    sudo('apt-get install -y python-novaclient')   
    sudo('apt-get install -y python-ceilometerclient') 
    sudo('apt-get install -y python-cinderclient') 
    sudo('apt-get install -y python-glanceclient')
    sudo('apt-get install -y python-heatclient')
    sudo('apt-get install -y python-keystoneclient')
    sudo('apt-get install -y python-neutronclient')
    sudo('apt-get install -y python-swiftclient')
    sudo('apt-get install -y python-troveclient')

###REMOVE###
@roles('desktop')
def removeopenstackclients():
    sudo('apt-get remove -y python-novaclient')   
    sudo('apt-get remove -y python-ceilometerclient') 
    sudo('apt-get remove -y python-cinderclient') 
    sudo('apt-get remove -y python-glanceclient')
    sudo('apt-get remove -y python-heatclient')
    sudo('apt-get remove -y python-keystoneclient')
    sudo('apt-get remove -y python-neutronclient')
    sudo('apt-get remove -y python-swiftclient')
    sudo('apt-get remove -y python-troveclient')

################## 4 CONFIGURE IMAGE SERVICE  #################

###ADD###
@roles('controller')
def installimageservice():
    ###configure prerequisites
    mysql_admin('root', dbmysqlroot, 'CREATE DATABASE glance;')
    mysql_admin('root', dbmysqlroot, "GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'localhost' IDENTIFIED BY '"+ GLANCE_DBPASS +"';")
    mysql_admin('root', dbmysqlroot, "GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'%' IDENTIFIED BY '"+ GLANCE_DBPASS +"';")
    ##Create a normal user
    with shell_env(OS_USERNAME='admin', OS_PASSWORD=ADMIN_PASS, OS_TENANT_NAME='admin', OS_AUTH_URL='http://controller:35357/v2.0'):
        run('keystone user-create --name=glance --pass='+GLANCE_PASS+' --email='+ EMAIL_ADDRESS)
        run('keystone user-role-add --user=glance --role=admin --tenant=service')
        run('keystone service-create --name=glance --type=image --description="OpenStack Image Service"')
        output = run('keystone service-list | awk "/ image / {print $2}"')
        SERVICEID = output.split('|')[1].strip()
        run('keystone endpoint-create --service-id='+SERVICEID+'  --publicurl=http://controller:9292  --internalurl=http://controller:9292 --adminurl=http://controller:9292')
    sudo('apt-get update')
    sudo('apt-get install -y glance python-glanceclient') 
    put('templates/controller/glance-api.conf', "/tmp/glance-api.conf")
    sudo('mv /tmp/glance-api.conf /etc/glance/glance-api.conf')
    put('templates/controller/glance-registry.conf', "/tmp/glance-registry.conf")
    sudo('mv /tmp/glance-registry.conf /etc/glance/glance-registry.conf')    
    sudo('su -s /bin/sh -c "glance-manage db_sync" glance')
    sudo('service glance-registry restart')
    sudo('service glance-api restart')
    with settings(warn_only=True):
        sudo('rm /var/lib/glance/glance.sqlite')
        
    ###verify operations
    run('mkdir /tmp/images')
    with cd('/tmp/images'):
        run('wget http://cdn.download.cirros-cloud.net/0.3.2/cirros-0.3.2-x86_64-disk.img')
        with shell_env(OS_USERNAME='admin', OS_PASSWORD=ADMIN_PASS, OS_TENANT_NAME='admin', OS_AUTH_URL='http://controller:35357/v2.0'):
            run('glance image-create --name "cirros-0.3.2-x86_64" --file cirros-0.3.2-x86_64-disk.img --disk-format qcow2 --container-format bare --is-public True --progress') 
    with shell_env(OS_USERNAME='admin', OS_PASSWORD=ADMIN_PASS, OS_TENANT_NAME='admin', OS_AUTH_URL='http://controller:35357/v2.0'):  
        run('glance image-list')
    with settings(warn_only=True):
        run('rm -r /tmp/images')

###REMOVE###
@roles('controller')
def removeimageservice():
    sudo('apt-get remove -y glance python-glanceclient')  
    
    
################## 5 ADD COMPUTE SERVICE  #################

###ADD###
@roles('controller')    
def configurecomputedbconn():
    mysql_admin('root', dbmysqlroot, 'CREATE DATABASE nova;')
    mysql_admin('root', dbmysqlroot, "GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'localhost' IDENTIFIED BY '"+ NOVA_DBPASS +"';")
    mysql_admin('root', dbmysqlroot, "GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'%' IDENTIFIED BY '"+ NOVA_DBPASS +"';")
    ###Create a compute user
    with shell_env(OS_USERNAME='admin', OS_PASSWORD=ADMIN_PASS, OS_TENANT_NAME='admin', OS_AUTH_URL='http://controller:35357/v2.0'):
        run('keystone user-create --name=nova --pass='+NOVA_PASS+' --email='+ EMAIL_ADDRESS)
        run('keystone user-role-add --user=nova --role=admin --tenant=service')
        run('keystone service-create --name=nova --type=compute --description="OpenStack Compute"')
        output = run('keystone service-list | awk "/ compute / {print $2}"')
        print output
        SERVICEID = output.split('|')[1].strip()
        run('keystone endpoint-create --service-id='+SERVICEID+' --publicurl=http://controller:8774/v2/%\(tenant_id\)s --internalurl=http://controller:8774/v2/%\(tenant_id\)s --adminurl=http://controller:8774/v2/%\(tenant_id\)s')     
    sudo('apt-get update') 
    sudo('apt-get -y install nova-api nova-cert nova-conductor nova-consoleauth nova-novncproxy nova-scheduler python-novaclient')
    put('templates/controller/nova.conf', "/tmp/nova.conf")
    sudo('mv /tmp/nova.conf /etc/nova/nova.conf')    
    sudo('su -s /bin/sh -c "nova-manage db sync" nova')
    sudo('service nova-api restart')
    sudo('service nova-cert restart')
    sudo('service nova-consoleauth restart')
    sudo('service nova-scheduler restart')
    sudo('service nova-conductor restart')
    sudo('service nova-novncproxy restart')
    with settings(warn_only=True):
        sudo('rm /var/lib/nova/nova.sqlite')
        
        
@roles('compute')    
def configurecompute(): 
    sudo('apt-get update') 
    sudo('apt-get -y install nova-compute python-guestfs')   
    put('templates/compute/nova.conf', "/tmp/nova.conf")
    sudo('mv /tmp/nova.conf /etc/nova/nova.conf')    
    put('templates/compute/nova-compute.conf', "/tmp/nova-compute.conf")
    sudo('mv /tmp/nova-compute.conf /etc/nova/nova-compute.conf')  
    with settings(warn_only=True):
        sudo('rm /var/lib/nova/nova.sqlite')    
    sudo('service nova-compute restart')

@roles('controller')    
def verifycompute():          
    ####verify operations
    with shell_env(OS_USERNAME='admin', OS_PASSWORD=ADMIN_PASS, OS_TENANT_NAME='admin', OS_AUTH_URL='http://controller:35357/v2.0'):  
        run('nova service-list')
        run('nova image-list')


###REMOVE###
@roles('controller')
def removenovacontroller():
    sudo('apt-get -y remove nova-api nova-cert nova-conductor nova-consoleauth nova-novncproxy nova-scheduler python-novaclient')   
    
@roles('compute')
def removenovacompute():
    sudo('apt-get -y remove nova-compute')   
    
    
    
################## 6 ADD NETWORKING COMPONENT  #################

###ADD###
@roles('controller')    
def configureneutrondbconn():
    mysql_admin('root', dbmysqlroot, 'CREATE DATABASE neutron;')
    mysql_admin('root', dbmysqlroot, "GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'localhost' IDENTIFIED BY '"+ NEUTRON_DBPASS +"';")
    mysql_admin('root', dbmysqlroot, "GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'%' IDENTIFIED BY '"+ NEUTRON_DBPASS +"';")
    ###Create a compute user
    with shell_env(OS_USERNAME='admin', OS_PASSWORD=ADMIN_PASS, OS_TENANT_NAME='admin', OS_AUTH_URL='http://controller:35357/v2.0'):
        run('keystone user-create --name=neutron --pass='+NEUTRON_PASS+' --email='+ EMAIL_ADDRESS)
        run('keystone user-role-add --user=neutron --role=admin --tenant=service')
        run('keystone service-create --name=neutron --type=network --description="OpenStack Networking"')    
        output = run('keystone service-list | awk "/ network / {print $2}"')
        print output
        SERVICEID = output.split('|')[1].strip()
        run('keystone endpoint-create --service-id='+SERVICEID+' --publicurl http://controller:9696 --adminurl http://controller:9696 --internalurl http://controller:9696')    
    sudo('apt-get update')
    sudo('apt-get -y install neutron-server neutron-plugin-ml2')
    ###SET nova_admin_tenant_id = SERVICE_TENANT_ID in neutron.conf MANUALLY
    with shell_env(OS_USERNAME='admin', OS_PASSWORD=ADMIN_PASS, OS_TENANT_NAME='admin', OS_AUTH_URL='http://controller:35357/v2.0'):
        output = run('keystone tenant-get service | awk "/ id / {print $4}"')
        print output
        SERVICE_TENANT_ID = output.split('|')[2].strip()
        print SERVICE_TENANT_ID
    
    
    put('templates/controller/neutron.conf', "/tmp/neutron.conf")
    sudo('mv /tmp/neutron.conf /etc/neutron/neutron.conf')  
    put('templates/controller/ml2_conf.ini', "/tmp/ml2_conf.ini")
    sudo('mv /tmp/ml2_conf.ini /etc/neutron/plugins/ml2/ml2_conf.ini')  
    put('templates/controller/nova.conf', "/tmp/nova.conf")
    sudo('mv /tmp/nova.conf /etc/nova/nova.conf') 
    sudo('service nova-api restart')
    sudo('service nova-scheduler restart')
    sudo('service nova-conductor restart')
    sudo('service neutron-server restart')
    

@roles('network')    
def configureneutronnetwork():
    put('templates/network/sysctl.conf', "/tmp/sysctl.conf")
    sudo('mv /tmp/sysctl.conf /etc/sysctl.conf') 
    sudo('sysctl -p')
    sudo('apt-get update')
    sudo('apt-get -y install neutron-plugin-ml2 neutron-plugin-openvswitch-agent openvswitch-datapath-dkms neutron-l3-agent neutron-dhcp-agent')
    put('templates/network/neutron.conf', "/tmp/neutron.conf")
    sudo('mv /tmp/neutron.conf /etc/neutron/neutron.conf')   
    put('templates/network/l3_agent.ini', "/tmp/l3_agent.ini")
    sudo('mv /tmp/l3_agent.ini /etc/neutron/l3_agent.ini')       
    put('templates/network/dhcp_agent.ini', "/tmp/dhcp_agent.ini")
    sudo('mv /tmp/dhcp_agent.ini /etc/neutron/dhcp_agent.ini')  
    put('templates/network/dnsmasq-neutron.conf', "/tmp/dnsmasq-neutron.conf")
    sudo('mv /tmp/dnsmasq-neutron.conf /etc/neutron/dnsmasq-neutron.conf')  
    with settings(warn_only=True):
        sudo('killall dnsmasq')
    put('templates/network/metadata_agent.ini', "/tmp/metadata_agent.ini")
    sudo('mv /tmp/metadata_agent.ini /etc/neutron/metadata_agent.ini') 
    put('templates/network/ml2_conf.ini', "/tmp/ml2_conf.ini")
    sudo('mv /tmp/ml2_conf.ini /etc/neutron/plugins/ml2/ml2_conf.ini') 
    sudo('service openvswitch-switch restart')
    with settings(warn_only=True):
        sudo('ovs-vsctl add-br br-int')
    with settings(warn_only=True):
        sudo('ovs-vsctl add-br br-ex')
        sudo('ovs-vsctl add-port br-ex eth0')
        #sudo('ethtool -K eth0 gro off')
    
    sudo('service neutron-plugin-openvswitch-agent restart')
    sudo('service neutron-l3-agent restart')
    sudo('service neutron-dhcp-agent restart')
    sudo('service neutron-metadata-agent restart')

@roles('controller')    
def configureneutronnetworkcontroller():   
    put('templates/controller/nova.conf', "/tmp/nova.conf")
    sudo('mv /tmp/nova.conf /etc/nova/nova.conf') 
    sudo('service nova-api restart')
    

@roles('compute')    
def configureneutroncompute():
    put('templates/network/sysctl.conf', "/tmp/sysctl.conf")
    sudo('mv /tmp/sysctl.conf /etc/sysctl.conf') 
    sudo('sysctl -p')
    sudo('apt-get update')
    sudo('apt-get -y install neutron-common neutron-plugin-ml2 neutron-plugin-openvswitch-agent openvswitch-datapath-dkms')
    put('templates/compute/neutron.conf', "/tmp/neutron.conf")
    sudo('mv /tmp/neutron.conf /etc/neutron/neutron.conf')      
    put('templates/compute/ml2_conf.ini', "/tmp/ml2_conf.ini")
    sudo('mv /tmp/ml2_conf.ini /etc/neutron/plugins/ml2/ml2_conf.ini') 
    sudo('service openvswitch-switch restart')
    with settings(warn_only=True):
        sudo('ovs-vsctl add-br br-int')
    put('templates/compute/nova.conf', "/tmp/nova.conf")
    sudo('mv /tmp/nova.conf /etc/nova/nova.conf')  
    sudo('service nova-compute restart')
    sudo('service neutron-plugin-openvswitch-agent restart')
    
@roles('controller')    
def createinitialnetworks():   
    with shell_env(OS_USERNAME='admin', OS_PASSWORD=ADMIN_PASS, OS_TENANT_NAME='admin', OS_AUTH_URL='http://controller:35357/v2.0'):
        sudo('neutron net-create ext-net --shared --router:external=True')
        sudo('neutron subnet-create ext-net --name ext-subnet --allocation-pool start='+FLOATING_IP_START+',end='+FLOATING_IP_END+' --disable-dhcp --gateway '+EXTERNAL_NETWORK_GATEWAY+' '+EXTERNAL_NETWORK_CIDR)
##create the tenant network
    with shell_env(OS_USERNAME='demo', OS_PASSWORD=DEMO_PASS, OS_TENANT_NAME='demo', OS_AUTH_URL='http://controller:35357/v2.0'):
        sudo('neutron net-create demo-net')
        sudo('neutron subnet-create demo-net --name demo-subnet --gateway '+TENANT_NETWORK_GATEWAY+' '+TENANT_NETWORK_CIDR)
##create a router on the tenant network and attach the external and tenant networks to it
        sudo('neutron router-create demo-router')
        sudo('neutron router-interface-add demo-router demo-subnet')
        sudo('neutron router-gateway-set demo-router ext-net')
        
###REMOVE###
@roles('controller')
def removeneutron():
    sudo('apt-get -y remove neutron-server neutron-plugin-ml2') 
    

@roles('network')    
def removeneutronnetwork():
    sudo('apt-get -y remove neutron-plugin-ml2 neutron-plugin-openvswitch-agent openvswitch-datapath-dkms neutron-l3-agent neutron-dhcp-agent')
    
    
@roles('compute')    
def removeneutroncompute():
    sudo('apt-get -y remove neutron-common neutron-plugin-ml2 neutron-plugin-openvswitch-agent openvswitch-datapath-dkms')  
    
    
 ################## 7 ADD DASHBOARD COMPONENT  #################
 ###ADD###
@roles('controller')
def adddash(): 
    sudo('apt-get update')
    sudo('apt-get -y install apache2 memcached libapache2-mod-wsgi openstack-dashboard')
    sudo('apt-get -y remove --purge openstack-dashboard-ubuntu-theme')
    put('templates/controller/local_settings.py', "/tmp/local_settings.py")
    sudo('mv /tmp/local_settings.py /etc/openstack-dashboard/local_settings.py')   
    sudo('service apache2 restart')
    sudo('service memcached restart')    

###REMOVE###
@roles('controller')
def deldash(): 
    sudo('apt-get -y remove apache2 memcached libapache2-mod-wsgi openstack-dashboard')    
        