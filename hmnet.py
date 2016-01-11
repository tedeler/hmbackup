# -*- coding: utf-8 -*-
import json
import xmlrpclib
from devices import DeviceFactory, HMLink
import pandas as pd
from collections import OrderedDict
import logging as log

class network:
    def __init__(self, rpcaddr, namefile):
        self.rpcaddr = rpcaddr
        self.namefile = namefile
        self.proxy = xmlrpclib.ServerProxy(rpcaddr)
        log.info('Connected to serveraddress "%s"', rpcaddr)
    def getDevices(self):
        result = self.proxy.listDevices()
        devlist = [DeviceFactory(desc, self.proxy, self.namefile) for desc in result]
        return devlist
    def getLinksSlow(self):
        alllinks = list()
        for dev in self.getDevices():
            peers = dev.get_link_peers()
            for peer in peers:
                receiver = dev
                sender = peer
                try:
                    pset = self.proxy.getParamset(receiver.addr, sender.addr)
                except:
                    continue
                
                if len(pset) == 0:
                    continue
                link = HMLink(sender, receiver)
                if link in alllinks:
                    continue
                alllinks.append(link)
        return alllinks
    def getLinks(self):
        result = self.proxy.getLinks("", 0x4)
        devlist = self.getDevices()
        devdict = dict( [(d.addr, d) for d in devlist] )
        links = list()
        for r in result:
            sender = devdict[r['SENDER']]
            receiver = devdict[r['RECEIVER']]
            receiver_paramset = r['RECEIVER_PARAMSET']
            links.append( HMLink(sender, receiver, receiver_paramset, r['FLAGS']) )
        return links
    def callproxy(self, fkt, *args):
        callstr = '%s(%s)'%(fkt, '"' + '", "'.join(args) + '"')
        log.debug('Calling %s'%callstr)
        eval('self.proxy.%s'%callstr)
    def addLink(self, link, drymode):
        if drymode:
            log.info('Would add link to network: "%s"'%link)
        else:
            log.info('Add link to network: "%s"'%link)
            name = ''
            description = 'Created with hmnet.py'
            try:
                self.callproxy('addLink', link.sender.addr, link.receiver.addr, name, description)
#                self.proxy.addLink(link.sender.addr, link.receiver.addr, name, description)
                pset = link.receiver_paramset
                link.getParamset(reread_from_network=True)
                link.setParamset(pset, False)
            except xmlrpclib.Fault,e:
                log.error('Communication failure while adding link. Try revert action. :%s'%e)
                self.deleteLink(link, False)
    def deleteLink(self, link, drymode):
        if drymode:
            log.info('Would delete link from network: "%s"'%link)
        else:
            log.info('Delete link from network: "%s"'%link)
            try:
                self.callproxy('removeLink', link.sender.addr, link.receiver.addr)
            except xmlrpclib.Fault,e:
                log.error('Communication failure while deleting link.')

    def dumpLinksToFile(self, filename):
        dataset = OrderedDict()        
        dataset['links'] = list()
        
        links = self.getLinks()
        paramsets = list()
        linkoutputlist = list()
        with open(filename, 'w') as fd:
            for link in links:
                data = OrderedDict()
                pset = link.getParamset()
                if pset not in paramsets:
                    paramsets.append(pset)
                data['psetid'] = paramsets.index(pset)
                data['desc'] = '%-40s -> %-40s'%(link.sender.username, link.receiver.username)
                data['sender'] = link.sender.addr
                data['receiver'] = link.receiver.addr
                linkoutputlist.append(data)
            linkoutputlist = sorted(linkoutputlist, key=lambda x: (x['psetid'], x['desc']))
            dataset['links'] = linkoutputlist

            paramsetlist = list()
            for idx, pset in enumerate(paramsets):
                data = OrderedDict()
                data['id'] = idx
                data['paramset'] = pset
                paramsetlist.append(data)
            dataset['paramsets'] = paramsetlist

            outstr = json.dumps(dataset, ensure_ascii=False)
            outstr = outstr.replace('{"psetid"', '\n    {"psetid"')
            outstr = outstr.replace(' "paramsets"', '\n "paramsets"')
            outstr = outstr.replace('{"id"', '\n    {"id"')
            outstr = outstr.replace(']', '\n]')
            fd.write(outstr.encode('utf-8'))
            fd.write('\n')
            
    def getLinkTable(self):
        links = self.getLinks()
        keys = ['sender', 'receiver', 'SHORT_ACTION_TYPE', 'LONG_ACTION_TYPE']
        tbldict = OrderedDict()
        indexcolumn = list()
        for (idxlink, link) in enumerate(links):
            pset = link.getParamset()
            #extract the keys of the paramset as a set
            for k in pset.keys():
                if k not in keys:
                    keys.append(k)
            for key in keys:
                if key not in tbldict:
                    emptylist = [None] * idxlink
                    tbldict[key] = emptylist
                if key == 'sender':
                    value = link.sender.addr
                elif key == 'receiver':
                    value = link.receiver.addr
                elif key not in pset:
                    value = None
                else:
                    value = pset[key]
                tbldict[key].append(value)
            indexcolumn.append(u'%s -> %s'%(link.sender.username, link.receiver.username))
        df = pd.DataFrame(tbldict, index=indexcolumn)
        return df
        
if __name__ == '__main__':
    net = network('http://ccu:2000', 'names.json')
    link = net.getLinks()
    
    
        