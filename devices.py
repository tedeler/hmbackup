# -*- coding: utf-8 -*-
import json
import logging as log
import copy
import xmlrpclib

def DeviceFactory(description, rpcproxy, names_file):
    if type(description) != dict:
        #description is assumed to be an address
        description = rpcproxy.getDeviceDescription(description)
    classdict = {'HMW-LC-Sw2-DR':Sw2DR,
                 'SWITCH':Switch,
                 'KEY':Key}
    dtype = description['TYPE']

    if dtype in classdict:
        return classdict[dtype](description, rpcproxy, names_file)
    else:
        return HMDevice(description, rpcproxy, names_file)

class HMLink(object):
    def __init__(self, sender, receiver, receiver_paramset, flags):
        self.sender = sender
        self.receiver = receiver
        self.receiver_paramset = receiver_paramset
        self.flags = flags
        self.proxy = sender.proxy
        if not self.receiver_paramset:
            log.debug("%s without paramset link"%self)
    def callproxy(self, fkt, *args):
        margs = list()
        for arg in args:
            if type(arg) == dict:
                margs.append(str(arg))
            else:
                margs.append('"' + str(arg) + '"')
        callstr = '%s(%s)'%(fkt, ', '.join(margs))
        log.debug('Calling %s'%callstr)
        try:
#            retval = eval('self.proxy.%s'%callstr)
            retval = self.proxy.__getattr__(fkt)(*args)
            return retval
        except xmlrpclib.Fault,e:
            import traceback
            log.error('Communication error: %s'%(e))
            log.error('%s'%(traceback.print_exc()))
            raise EnvironmentError(str(e))

    def link_broken_senderside(self):
        return bool(self.flags & 0x01)
    def link_broken_receiver(self):
        return bool(self.flags & 0x02)
    def getParamset(self, reread_from_network=False):
        if reread_from_network or not self.receiver_paramset:
            log.debug('Reading receiver paramset from network (%s)'%self.receiver)
            log.debug('%s, %s'%(reread_from_network, str(self.receiver_paramset)[:10]))
            self.receiver_paramset = self.callproxy('getParamset', self.receiver.addr, self.sender.addr)
        else:
            log.debug('Supply receiver paramset from cache (%s)'%self.receiver)
        return self.receiver_paramset
    def getParamsetDescription(self):
        info = self.receiver.get_paramset_info('LINK')
        return info
        
    def setParamset(self, paramset, drymode=True):
        existing_pset = self.getParamset()
        new_pset = copy.deepcopy(existing_pset)
        not_com_keys = set(paramset.keys()).symmetric_difference(existing_pset.keys())
        if len(not_com_keys) > 0:
            msg = 'Link %s\n    Keys %s are not common present in device or paramset to put'%(self, not_com_keys)
            log.error(msg)
            raise EnvironmentError(msg)

        firsttime=True
        psetchanged=False
        pset_info = self.getParamsetDescription()
        for key in sorted(paramset.keys()):
            v1 = paramset[key]
            v2 = existing_pset[key]
            if v1 == v2:
                continue
            if type(v1) != type(v2):
                msg = "Unexpected error. Types are not equal"
                log.error(msg)
                raise EnvironmentError(msg)
            if firsttime:
                if drymode:
                    log.info('------------ DRYMODE ---------------')
                log.info('Updating Paramset in link "%s"'%self)
                firsttime = False
            ok = self.check_new_pset_value(key, v2, v1, pset_info[key])
            if ok:
                new_pset[key] = paramset[key]
                psetchanged = True
        if not drymode and psetchanged:
            self.callproxy('putParamset', self.receiver.addr, self.sender.addr, paramset)
    def check_new_pset_value(self, name, old_value, new_value, info):
        log.debug(' Setting key %s', name)
        if (info['OPERATIONS'] & 0x02) == 0:
            msg = "Parameter %s is not writable"%name
            log.error(msg)
            raise EnvironmentError(msg)
        if info['FLAGS'] & 0x04:
            msg = "Transformflag of parameter %s is set. Aborting write of new value!"%name
            log.error(msg)
            raise EnvironmentError(msg)
        if info['TYPE'] == 'ENUM':
            log.debug('   Datatype is enum with values %s'%info['VALUE_LIST'])
            old_value = info['VALUE_LIST'][old_value]
            try:
                new_value = info['VALUE_LIST'][new_value]
            except IndexError:
                msg = 'New value %d of parameter %s is out of allowed range'%(new_value, name)
                log.error(msg)
                raise EnvironmentError(msg)
        elif info['TYPE'] in ['FLOAT', 'INTEGER', 'BOOL']:
            minvalue = info['MIN']
            maxvalue = info['MAX']
            log.debug('%s <= new value <= %s'%(minvalue, maxvalue))
            log.debug('New value is %s'%new_value)
            if new_value < minvalue or new_value > maxvalue:
                if new_value == 16383000.0 and info['TYPE'] == 'FLOAT':
                    log.debug('Value out of range but identical to special value 16383000.0')
                else:
                    msg = 'New value %s is out of range %s ... %s'%(new_value, minvalue, maxvalue)
                    log.error(msg)
                    raise EnvironmentError(msg)
        elif info['TYPE'] == 'STRING':
            log.debug('Datatype is string')
        else:
            log.debug('Unknown datatype %s. Ignoring parameter %s'%(info['TYPE'], name) )
            return False
        log.debug('Changing [%s] from %s to %s', name, old_value, new_value)
        return True
    def __eq__(self, other):
        eq1 = self.sender.addr == other.sender.addr
        eq2 = self.receiver.addr == other.receiver.addr
        return eq1 and eq2
        
    def __repr__(self):
        br = ''
        bs = ''
        if self.link_broken_receiver():
            br = '(*)'
        if self.link_broken_senderside():
            bs = '(*)'
        return self.sender.addr + bs + ' -> ' + self.receiver.addr + br
    def __unicode__(self):
        br = ''
        bs = ''
        if self.link_broken_receiver():
            br = '(*)'
        if self.link_broken_senderside():
            bs = '(*)'
        r = u'%s[%s%s] --> %s[%s%s]'%(self.sender.username, self.sender.addr, bs, self.receiver.username, self.receiver.addr, br)
        return r
        
    def __str__(self):
        return unicode(self).encode('utf-8')
        
class HMDevice(object):
    PARAMSET_INFO = dict()
    def __init__(self, description, proxy, names_file):
        self.proxy = proxy
        self.desc  = description
        self.addr  = self.desc['ADDRESS']
        with open(names_file) as fd:
            data = json.load(fd)
        if self.addr in data:
            self.username = data[self.addr]
        else:
            self.username = None
    def get_paramset_info(self, paramset_name, force_reread_from_network=False):
        mytype = self.desc['TYPE']
        if mytype not in self.PARAMSET_INFO or force_reread_from_network:
            log.debug('Get info of devicetype %s and parameterset %s from network'%(mytype, paramset_name))
            self.PARAMSET_INFO[mytype] = self.proxy.getParamsetDescription(self.addr, paramset_name)
        else:
            log.debug('Get info of devicetype %s and parameterset %s from cache'%(mytype, paramset_name))
        return self.PARAMSET_INFO[mytype]
        
    def get_paramset(self, name):
        return self.proxy.getParamset(self.addr, name)
    def get_link_peers(self):
        result = self.proxy.getLinkPeers(self.addr)
        return [DeviceFactory(self.proxy.getDeviceDescription(d), self.proxy) for d in result]
    def get_links(self):
        result = self.proxy.getLinks(self.addr)
        links = list()
        for r in result:
            sender = DeviceFactory(r['SENDER'], self.proxy)
            receiver = DeviceFactory(r['RECEIVER'], self.proxy)
            links.append( HMLink(sender, receiver) )
        return links
    def __unicode__(self):
        result = u'Homematic Device %s addr:%s name:"%s"'%(self.desc['TYPE'], self.addr, self.username)
        return result
    def __str__(self):
        return unicode(self).encode('utf-8')
    def __repr__(self):
        return '%s %s'%(type(self), self.addr)
class Sw2DR(HMDevice):
    def __init__(self, description, proxy, names_file):
        HMDevice.__init__(self, description, proxy, names_file)
        
class Switch(HMDevice):
    def __init__(self, description, proxy, names_file):
        HMDevice.__init__(self, description, proxy, names_file)
    def state(self):
        pset = self.proxy.getParamset(self.addr, 'VALUES')
        return pset['STATE']
    def set_state(self, state):
        self.proxy.setValue(self.addr, 'STATE', state)
    def __unicode__(self):
        result = u'SWITCH: Addr: %s "%s"'%(self.addr, self.username)
        return result
class Key(HMDevice):
    def __init__(self, description, proxy, names_file):
        HMDevice.__init__(self, description, proxy, names_file)
    def __unicode__(self):
        result = u"KEY: Addr: %s (%s)"%(self.addr, self.username)
        return result
if __name__=='__main__':
    import xmlrpclib
    import time

    proxy = xmlrpclib.ServerProxy("http://hpi:2001/")
    result = proxy.listDevices()
    dev = [DeviceFactory(desc, proxy) for desc in result]
    for d in dev:
        if d.addr == 'LEQ1181007:4':
            break
    l = d.get_links()[0]

    pset = l.getParamset()
    print pset['LONG_ACTION_TYPE']
    pset['LONG_ACTION_TYPE'] = 1
    l.setParamset(pset)

    pset = l.getParamset()
    print pset['LONG_ACTION_TYPE']
    