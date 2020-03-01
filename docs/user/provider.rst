VM Module Provider
==================

CyBorgBackup can use custom VM module provider to backup virtual machine based on hypervisor.

The module need to respect some prerequisites to be used by CyBorgBackup.

Module Name
-----------

This function return the module name displayed by CyBorgBackup::

      def module_name():
          return 'Proxmox'


Module Type
-----------

This function return the policy type code used by CyBorgBackup to identify the utility of this module.
For VM backup provider, it must be set to 'vm'::

      def module_type():
          return 'vm'


Get Client
----------

This function return the hostname of the hypervisor of the VM.
It will be used to connect them and launch backup script ::

    def get_client(client):
        return 'hypervisor.example.com'

Get Script
----------

This function return a string that represent the script send to the hypervisor and used to backup the virtual machine.
The script must return data on stdout. Data received will be directly send to borg create::

    def get_script():
        return '''#!/bin/bash
    echo "Hello World"
    '''

Example Proxmox Script
----------------------

You will find bellow an example script used to backup Proxmox VirtualMachine from her hypervisor ::

