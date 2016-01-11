# hmbackup
Utility for backup and restore Homematic direct links (German: Direktverknüpfungen) using xmlrpc-api of the CCU-Device.

The backupfile has JSON format. Each link is presented in one line with the followin attributes:
* delete: Always false. Change to true will cause the restore process to permanently delete this link.
* psetid: Reference of the associated parameter set. These sets are defined at the bottom of the backup file.
* desc:   User readable description of the link (ignored during restore)
* sender: Sender address
* receiver: Receiver address

Upon restore the linkfile is read from top to bottom. For every link the following procedure will be executed:
* 1.) Link is present in Homematic Network?
* 1.1) Should it be deleted? YES ==> Delete
* 1.2) Is parameter set different? YES ==> Update
* 2.) Link is not present in Homematic Network?
* 2.1) Should it be deleted? YES ==> Do nothing
* 2.2) Create link




## usage
### help
``python hmbackup.py -h``

### backup direct homematic links
``python hmbackup.py -c``

This assumes the ccu is available in the network under the name "ccu" and port 2000. You can change this with parameters  ``-s`` and ``-p``

### restore direct homematic links
``python hmbackup.py -r (drymode -- Don't do any actual writes to Homematic Network)``

``python hmbackup.py -rw (wetmode -- Aktually write to Homematic Network)``


## name file
Devices are identified with their address. To make the backupfile more readable it is possible to provide a namefile (option ``-n``). Default is ``"homematic_manager_names.json"``. The namefile preset in the project is a demo file to give you an idea of the syntax. 

If you are running the fantastic application Homematic-Manager (<https://github.com/hobbyquaker/homematic-manager>) you can directly use the namefile present in ``~/.hm-manager/names.json``.

