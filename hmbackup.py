# -*- coding: utf-8 -*-

import argparse
import os
import sys
import hmnet
from devices import HMLink, DeviceFactory
import json
from collections import OrderedDict
import pandas as pd

import logging as log

#Creates and Restores Backups of Homematic Links


def define_commandline_arguments():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    group = parser.add_argument_group('RPC Server')
    group.add_argument('-s', '--host', default="ccu", help="Address of rpc server")
    group.add_argument('-p', '--port', default="2000", help="port of xml service")
    group = parser.add_argument_group('Files')
    group.add_argument('-n', '--name-file', default='homematic_manager_names.json', help="Namefile (JSON) for HM-Devices")
    group.add_argument('-f', '--backup_file', default='link_backup.json', help='Location of backup file')
    group = parser.add_argument_group('Commands')
    megroup = group.add_mutually_exclusive_group()
    megroup.add_argument('-c', '--create-link-backup', action='store_true', help="Backup links")
    megroup.add_argument('-r', '--restore-link-backup', action='store_true', help="Restore links")
    group.add_argument('-w', '--wet-mode', action='store_true', help="Enables writes to homematic network")
    group.add_argument('-o', '--overwrite_files', action='store_true', help="Overwrite existing files")
    group.add_argument('-v', '--verbosity', action='count', default=0)
    return parser
def check_options(options, parser):
    pass

def check_file(filename, mode, overwrite=False, doopen=False):
    '''
    checks if the file <filename> can be opened in mode <mode> (r/w).
    In case of mode=='r' (reading) it checks if the file exists and throws EnvironmentError otherwise.
    In case of mode=='w' (writing) it checks if file path exists. If not it is created.
                                   it checks if file exists. If yes it throws EnvironmentError if overwrite_files is False.
    '''

    if os.path.exists(filename):
        if mode=='w' and overwrite:
            log.warn('File exists! Overwriting "%s"', filename)
        elif mode=='w' and not overwrite:
            msg = 'File "%s" exists. Use overwrite option if you want to overwrite file'%filename
            log.error(msg)
            raise EnvironmentError(msg)
    else:
        if mode=='r':
            msg = 'File "%s" does not exist'%filename
            log.error(msg)
            raise EnvironmentError(msg)
        elif mode=='w':
            path = os.path.dirname(filename)
            if not os.path.exists(path) and len(path)>0:
                log.warn('Path "%s" does not exist. It will be created', path)
                os.makedirs(path)

    #Open file if requested
    if doopen:
        return open(filename, mode)
    else:
        return None

def create_device_list(net, options):
    devlist  = net.getDevices()
    devdata = list()
    for dev in devlist:
        data = {'addr':dev.addr, 'description':dev.username}
        devdata.append(data)

    filename = os.path.join(options.backup_dir, 'devicelist.txt')
    log.info('Writing device list to file "%s"', filename)
    fd = check_file(filename, 'w', options.overwrite_files, doopen=True)
#    pd_dataframe_to_html(pd.DataFrame(devdata), filename)
    fd.write(pd.DataFrame(devdata).to_string().encode('utf-8'))
    fd.close()

def restore_link_backup(net, options):
    '''
        Restores links from backupfile and writes them into the corresponding devices
        net: Network object for accessing devices
        options: Programm options
    '''
    filename_links = options.backup_file
    log.info('restoring links from file "%s"', filename_links)

    #Load backupfile
    fd = check_file(filename_links, 'r', doopen=True)    
    try:
        backup = json.load(fd)
    except ValueError, e:
        msg = 'Error while reading file %s: %s'%(filename_links, e)
        log.error(msg)
        fd.close()
        raise EnvironmentError(msg)
    fd.close
    
    paramsets = backup['Paramsets']
    links = backup['Linklist']
    existing_links = net.getLinks()
    device_list = net.getDevices()
    devices = dict( [(d.addr, d) for d in device_list] )
    for rlink in links:
        try:
            sender = devices[rlink['sender']]
            receiver = devices[rlink['receiver']]
        except KeyError, e:
            log.warn('address %s is not present in network. Check file "%s"'%(e, filename_links))
            continue
        
        existing_link = None
        for elink in existing_links:
            if elink.sender.addr == sender.addr and elink.receiver.addr == receiver.addr:
                existing_link = elink
        
        try:
            pset = paramsets[unicode(rlink['psetid'])]
        except KeyError, e:
            log.error('Unknown reference to psetid %s. Check backup file'%(e))
            continue

        if existing_link:
            log.debug('Found link "%r" in network'%existing_link)
            if rlink['delete']:
                #Link is requested to be deleted
                net.deleteLink(existing_link, not options.wet_mode)
                existing_links.remove(existing_link)
            else:
                #Link does exists ==> update parameters
                existing_link.setParamset(pset, not options.wet_mode)
        elif rlink['delete']:
            log.debug('Link does not exist and can not be deleted: %s->%s'%(sender, receiver))
        else:
            #Link does not exist and is not marked for deletion ==> Create link!
            log.debug('Link "%s" not existing in network. It will be added'%existing_link)
            new_link = HMLink(sender, receiver, pset, 0x00)
            net.addLink(new_link, not options.wet_mode)
            existing_links.append(new_link)
def create_link_backup(net, options):    
    '''
        Creates the full link backup of all links in <net>
        net: Network object to access all homematic devices
        options: programm options
    '''
    filename_links = options.backup_file   
    log.info('Create link backup')
    linklist = net.getLinks()
    paramsets = OrderedDict()
    linkbackuplist = list()
    for link in linklist:
        #Get sorted pset of current link
        pset = link.getParamset()
        pset = OrderedDict( (k, pset[k]) for k in sorted(pset) )

        #Insert pset of link into known paramsets if it's not in already
        if pset not in paramsets.values():
            pid = 0
            while(str(pid) in paramsets.keys()):
                pid += 1
            paramsets[str(pid)] = pset

        #Find paramset id for the given pset of link in all known paramsets
        for key,value in paramsets.iteritems():
            if value == pset:
                paramset_id = key

        #Mark broken links
        br = ''
        bs = ''
        if link.link_broken_receiver():
            br = '(*)'
        if link.link_broken_senderside():
            bs = '(*)'
        us = bs + unicode(link.sender.username)
        ur = br + unicode(link.receiver.username)

        #Fill data fields
        data = OrderedDict()
        data['delete'] = False
        data['psetid'] = paramset_id
        data['desc'] = u'%-40s -> %-40s'%(us, ur)
        data['sender'] = link.sender.addr
        data['receiver'] = link.receiver.addr
        linkbackuplist.append(data)

    #Sort by paramset id and secondly by description
    sortkey = lambda x: (x['psetid'], x['desc'])
    linkbackuplist = sorted(linkbackuplist, key=sortkey)
    
    log.info('Found %d links and %d paramsets', len(linkbackuplist), len(paramsets))
    log.info('Write linklist to file "%s"', filename_links)

    #write json file
    write_json(filename_links, linkbackuplist, paramsets, options.overwrite_files)

def write_json(filename, links, paramsets, overwrite_flag):
    '''
        filename: Location and name of outputfile
        links: list of dicts. Each dict is a link with reference to a parameterset
        paramsets: dict of dicts: Paramsets sorted by parameterset reference
    '''
    outstr = u'{"Linklist": [ \n'
    for link in links:
        outstr += '    ' + json.dumps(link, ensure_ascii=False) + ',\n'
    outstr = outstr[:-2] + u'\n],'
    outstr += u'"Paramsets": { \n'
    for key in sorted(paramsets):
        outstr += '    "%s":'%key
        outstr += json.dumps(paramsets[key], ensure_ascii=False) + ',\n'
    outstr = outstr[:-2] + u'\n}}'
    fd = check_file(filename, 'w', overwrite_flag, doopen=True)
    fd.write(outstr.encode('utf-8'))
    fd.close()


parser = define_commandline_arguments()
options = parser.parse_args()
check_options(options, parser)

if options.verbosity == 0:
    loglevel = log.INFO
elif options.verbosity == 1:
    loglevel = log.DEBUG
else:
    loglevel = log.DEBUG

log.basicConfig(format='[%(levelname)s] %(filename)s(%(lineno)s): %(message)s', level=loglevel)


rpcaddress = 'http://%s:%s'%(options.host, options.port)

#Connect to Homematic networt
HMNetwork = hmnet.network(rpcaddress, options.name_file)

try:
    if options.create_link_backup:
#        create_device_list(HMNetwork, options)
        create_link_backup(HMNetwork, options)
    if options.restore_link_backup:
        restore_link_backup(HMNetwork, options)
except EnvironmentError, e:
    log.error('Programm aborted')
    log.error(e)
