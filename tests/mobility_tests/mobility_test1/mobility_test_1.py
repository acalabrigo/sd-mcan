#!/usr/bin/python

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Node
from mininet.log import setLogLevel, info, output, warn
from mininet.cli import CLI
from mininet.node import OVSSwitch, Controller, RemoteController

from random import randint
import time

def int2dpid(dpid):
        try:
            dpid = hex(dpid)[2:]
            dpid = '0' * (16 - len(dpid)) + dpid
            return dpid
        except IndexError:
            raise Exception( 'Unable to derive default datapath ID - '
                             'please either specify a dpid or use a '
                             'canonical switch name such as s23.' )

class MobilitySwitch(OVSSwitch):
    "Switch that can reattach and rename interfaces"

    def delIntf(self, intf):
        "Remove (and detach) an interface"
        port = self.ports[intf]
        del self.ports[intf]
        del self.intfs[port]
        del self.nameToIntf[intf.name]

    def addIntf(self, intf, rename=False, **kwargs):
        "Add (and reparent) an interface"
        OVSSwitch.addIntf(self, intf, **kwargs)
        intf.node = self
        if rename:
            self.renameIntf(intf)

    def attach(self, intf):
        "Attach an interface and set its port"
        port = self.ports[intf]
        if port:
            if self.isOldOVS():
                self.cmd('ovs-vsctl add-port', self, intf)
            else:
                self.cmd('ovs-vsctl add-port', self, intf,
                         '-- set Interface', intf,
                         'ofport_request=%s' % port)
            self.validatePort(intf)

    def validatePort(self, intf):
        "Validate intf's OF port number"
        ofport = int(self.cmd('ovs-vsctl get Interface', intf,
                              'ofport'))
        if ofport != self.ports[intf]:
            warn('WARNING: ofport for', intf, 'is actually', ofport,
                  '\n')

    def renameIntf(self, intf, newname=''):
        "Rename an interface (to its canonical name)"
        intf.ifconfig('down')
        if not newname:
            newname = '%s-eth%d' % (self.name, self.ports[intf])
        intf.cmd('ip link set', intf, 'name', newname)
        del self.nameToIntf[intf.name]
        intf.name = newname
        self.nameToIntf[intf.name] = intf
        intf.ifconfig('up')

    def moveIntf(self, intf, switch, port=None, rename=True):
        "Move one of our interfaces to another switch"
        self.detach(intf)
        self.delIntf(intf)
        switch.addIntf(intf, port=port, rename=rename)
        switch.attach(intf)


def printConnections(switches):
    "Compactly print connected nodes to each switch"
    for sw in switches:
        output('%s: ' % sw)
        for intf in sw.intfList():
            link = intf.link
            if link:
                intf1, intf2 = link.intf1, link.intf2
                remote = intf1 if intf1.node != sw else intf2
                output('%s(%s) ' % (remote.node, sw.ports[intf]))
        output('\n')


def moveHost(host, oldSwitch, newSwitch, newPort=None):
    "Move a host from old switch to new switch"
    hintf, sintf = host.connectionsTo(oldSwitch)[ 0 ]
    oldSwitch.moveIntf(sintf, newSwitch, port=newPort)
    return hintf, sintf

class NetworkTopo(Topo):
    def build(self, **_opts):
        ss = [['s1', 1],
              ['s2', 2],
              ['s3', 3],
              ['s4', 4],
              ['s5', 5],
              ['s6', 6],
              ['s7', 7],
              ['s8', 8]]

        # add switches
        s1, s2, s3, s4, s5, s6, s7, s8 = [self.addSwitch(s, dpid=int2dpid(i))
                                          for s,i in ss]

        # Create the central mesh
        self.addLink(s1, s2)
        self.addLink(s1, s3)
        self.addLink(s1, s4)
        self.addLink(s2, s3)
        self.addLink(s2, s4)
        self.addLink(s3, s4)

        # add edge switches
        self.addLink(s1, s5)
        self.addLink(s2, s6)
        self.addLink(s3, s7)
        self.addLink(s4, s8)

        # add hosts
        h1 = self.addHost('h1', ip=None)
        h2 = self.addHost('h2', ip=None)
        #h3 = self.addHost('h3', ip=None)
        #h4 = self.addHost('h4', ip=None)

        # connect hosts to edge switches
        for h, s in [(h1, s5), (h2, s6)]:
            self.addLink(h, s)


def run():
    topo = NetworkTopo()
    net = Mininet(topo=topo, controller=RemoteController, switch=MobilitySwitch)
    net.start()
    info('*** Network:\n')
    printConnections(net.switches)
    time.sleep(15)

    h1, h2, old = net.get('h1', 'h2', 's5')

    for h in [h1, h2]:
        info('*** {0} dhclient\n'.format(h.name))
        info(h.cmd('dhclient ' + h.defaultIntf().name))

    CLI(net, script='mt1_s1')


    for s in [6, ]:
        new = net[ 's%d' % s ]
        port = randint( 10, 20 )
        info( '* Moving', h1, 'from', old, 'to', new, 'port', port, '\n' )
        hintf, sintf = moveHost( h1, old, new, newPort=port )
        info( '*', hintf, 'is now connected to', sintf, '\n' )
        info( '* New network:\n' )
        printConnections( net.switches )
        info('*** h1 dhclient\n')
        h1.cmd('dhclient ' + h1.defaultIntf().name)
        info( '*** Testing connectivity:\n' )
        CLI(net, script='mt1_s1')
        old = new
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()
