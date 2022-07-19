#!/usr/bin/env python3

import argparse
import os
import json
import sys
import configparser
import networkx as nx

from AutonomousSystem import AutonomousSystem
from pathlib import Path
from collections import defaultdict
from CLI import AS_CLI
from mininet.log import info, output, error

from python.lib.util import (
    load_yaml_file,
)
from python.lib.defines import (
    GEN_PATH,
    NETWORKS_FILE,
    IFIDS_FILE,
    AS_LIST_FILE,
    BR_NAMES_FILE,
)


class SCIONTopology(object):
    """Creates multiple ASes and connects them to each other"""

    def __init__(self, intra_config, scion_apps_path):
        """Initialize the topology"""
        self.SCION_PATH = Path().absolute()
        self.SCION_APPS_PATH = scion_apps_path
        self.intra_config = intra_config
        self.gen_dir = Path(self.SCION_PATH, GEN_PATH)
        # using getlogin() returning username
        self.username = os.getlogin()
        if self.username == 'root':
            output("You are root. Please run this script (+SCION) as a regular user.")
            sys.exit(1)

        self.networks_file = Path(self.gen_dir, NETWORKS_FILE)
        self.AS_list_file = Path(self.gen_dir, AS_LIST_FILE)
        self.interface_IDS_file = Path(self.gen_dir, IFIDS_FILE)
        self.BR_names_file = Path(self.gen_dir, BR_NAMES_FILE)

        self.AS_yaml_dict = load_yaml_file(self.AS_list_file)
        self.intra_config_dict = load_yaml_file(self.intra_config)
        self.ifids_dict = load_yaml_file(self.interface_IDS_file)
        self.BR_names_dict = load_yaml_file(self.BR_names_file)

        self.networks_config = configparser.ConfigParser()
        self.networks_config.read(self.networks_file)

        self.ASes = {}
        self.initialize_ASes()
        self.networks = {}
        self.BR_name_map = {}
        self.BR_name_map_rev = defaultdict(dict)
        self.initialize_BR_names()

    def initialize_ASes(self):
        """For each AS define some useful attributes"""
        for _, value_list in self.AS_yaml_dict.items():
            for ISD_AS_id in value_list:
                # replace to create AS name like in the networks file
                FULL_NAME = ISD_AS_id.replace(":", "_")
                gen_folder_name = 'AS' + FULL_NAME.split('-')[-1]
                AS_gen_path = Path(self.gen_dir, gen_folder_name)
                AS_config_dict = self.intra_config_dict["ASes"][ISD_AS_id]
                intra_topo = AS_config_dict['Intra-Topology']
                p = Path(intra_topo)
                if not p.is_absolute():
                    config_dir = self.intra_config.parent
                    p = Path(config_dir, intra_topo)

                intra_topo_dict = self.gen_intra_topo_dict(
                    p, AS_config_dict['Borderrouter'])
                graph = self.gen_intra_topo_graph(intra_topo_dict, ISD_AS_id)

                self.ASes[ISD_AS_id] = {
                    "FULL_NAME": FULL_NAME,
                    'AS_gen_path': AS_gen_path,
                    "intra_topology_dict": intra_topo_dict,
                    "routing_protocol": AS_config_dict['Routing-Protocol'],
                    "BR_name_mapping": AS_config_dict['Borderrouter'],
                    'intra_topo_graph': graph
                }

    def gen_intra_topo_dict(self, intra_topology, BR_name_mapping):
        """Generate intra topology dict from yaml file and remove unused BRs (+ their links)"""
        intra_topo_dict = load_yaml_file(intra_topology)

        BR_used = list(BR_name_mapping.keys())
        intra_topo_dict['Nodes']['Borderrouter'] = [
            BR for BR in intra_topo_dict['Nodes']['Borderrouter'] if BR in BR_used]
        all_nodes = []
        for _, node_list in intra_topo_dict['Nodes'].items():
            all_nodes.extend(node_list)

        for link in list(intra_topo_dict['links']):
            if link['a'] not in all_nodes or link['b'] not in all_nodes:
                intra_topo_dict['links'].remove(link)

        return intra_topo_dict

    def gen_intra_topo_graph(self, intra_topo_dict, ISD_AS_id):
        """Generate intra topology graph from the intra topology dict"""
        G = nx.MultiGraph()
        nodes = intra_topo_dict["Nodes"]
        for _, node_list in nodes.items():
            for node in node_list:
                G.add_node(node)
        topo_links = intra_topo_dict["links"]
        for link in topo_links:
            a = link['a']
            b = link['b']
            label = ""
            if link.get('bw', None) is not None:
                label += f'BW: {link["bw"]} Mbit/s\n'
            if link.get('delay', None) is not None:
                label += f'Delay: {link["delay"]} ms\n'
            if link.get('loss', None) is not None:
                label += f'Loss: {link["loss"]}%\n'
            if link.get('jitter', None) is not None:
                label += f'Jitter: {link["jitter"]} ms\n'
            label = label.strip()
            G.add_edge(a, b,
                       label=label
                       )
        if not nx.is_connected(G):
            error("ERROR: AS %s: Intra topology is not connected", ISD_AS_id)
            sys.exit(1)
        return G

    def initialize_BR_names(self):
        """Maps border router name from config to names used in the Mininet topology

        Example: maps: br1-ff00_0_111-3  -> br3 (name in intra config file)
        Stores the map from: BR name -> (ISD, internal name)
        and also the reverse map: (ISD, internal name) -> BR name
        """
        for ISD_AS_id, BR_map in self.BR_names_dict.items():
            for SCION_name, BR_net_name in BR_map.items():
                name_no_itf = SCION_name.split('#')[0]
                split = name_no_itf.split('-')
                if len(split) == 3:
                    # specific ID is given,
                    # don't use interface, because this BR will have multiple interfaces
                    SCION_name = name_no_itf

                internal_map = self.ASes[ISD_AS_id]['BR_name_mapping']
                internal_name = list(internal_map.keys())[list(
                    internal_map.values()).index(SCION_name)]
                self.BR_name_map[BR_net_name] = (ISD_AS_id, internal_name)
                self.BR_name_map_rev[ISD_AS_id][internal_name] = BR_net_name

    def create_networks(self):
        """Create Mininet networks for each AS

        Store Mininet network reference + other useful attributes in self.networks
        """
        for ISD_AS_id, AS_config in self.ASes.items():
            AS = AutonomousSystem(
                self, ISD_AS_id=ISD_AS_id, **AS_config)
            AS.build()
            # get real BR, not only its string name
            BRs = [AS.net.get(BR)
                   for BR in AS_config['BR_name_mapping'].keys()]

            AS_gen_path = AS_config['AS_gen_path']
            with open(Path(AS_gen_path, 'topology.json')) as f:
                topology_dict = json.load(f)
            self.networks[ISD_AS_id] = {
                "BRs": BRs,
                'AS': AS,
                'topology_dict': topology_dict,
                'graph': AS_config['intra_topo_graph']
            }

    def add_inter_AS_links(self, ISD_AS_id, BR_dict, links_created):
        """Add links between ASes

        Add also link properties defined in the SCION topology file
        and now stored in the topology dict (from topology.json)
        """
        BR_SUBNETS = self.networks[ISD_AS_id]['AS'].BR_SUBNETS

        for BR1, BR2 in BR_dict.items():
            if BR1 in links_created or BR2 in links_created:
                if not (BR1 in links_created and BR2 in links_created):
                    #  only one link between two BRs with the SAME interface is allowed
                    raise Exception(
                        f'Second link with same interface name requested: {BR1} and {BR2}')
                continue

            BR1_name = BR1.split()[0]
            BR2_name = BR2.split()[0]

            BR1_ifid = BR1.split()[1]
            BR2_ifid = BR2.split()[1]

            AS1, in_net_BR1_name = self.BR_name_map[BR1_name]
            AS2, in_net_BR2_name = self.BR_name_map[BR2_name]

            # retrieve right BR from the Mininet network
            in_net_BR1, in_net_BR2 = None, None
            for BR in self.networks[AS1]['BRs']:
                if BR.name == in_net_BR1_name:
                    in_net_BR1 = BR
            for BR in self.networks[AS2]['BRs']:
                if BR.name == in_net_BR2_name:
                    in_net_BR2 = BR
            if in_net_BR1 is None or in_net_BR2 is None:
                raise Exception(
                    f'ERROR: BR not found in network: {in_net_BR1_name} or {in_net_BR2_name}')

            # extract correct IP address
            addr1, addr2 = None, None
            for subnet in BR_SUBNETS:
                netprefix = subnet.split('/')[1]
                found1, found2 = False, False
                for name in self.networks_config[subnet]:
                    if name == BR1_name:
                        found1 = True
                        ip1 = self.networks_config[subnet][name]
                        addr1 = f'{ip1}/{netprefix}'
                    if name == BR2_name:
                        found2 = True
                        ip2 = self.networks_config[subnet][name]
                        addr2 = f'{ip2}/{netprefix}'
                if found1 and found2:
                    break
            if not (found1 and found2):
                raise Exception(
                    f'ERROR: both BR not found in one subnet: {BR1_name} and {BR2_name}')
            if addr1 is None or addr2 is None:
                raise Exception(
                    f'ERROR: addr1 or addr2 is None for {BR1_name} and {BR2_name}')

            # create actual link (virtual ethernet link)
            intf1 = f'veth-{BR1_ifid}'
            intf2 = f'veth-{BR2_ifid}'
            in_net_BR1.cmd(
                f'ip link add {intf1} type veth peer name {intf2} netns {in_net_BR2.pid}')
            in_net_BR1.cmd(f'ifconfig {intf1} {addr1}')
            in_net_BR2.cmd(f'ifconfig {intf2} {addr2}')

            # add defined link properties
            self.add_link_attributes(ISD_AS_id, BR1_name, BR2_name, BR1_ifid,
                                     in_net_BR1, in_net_BR2, intf1, intf2)

            links_created.add(BR1)
            links_created.add(BR2)
        return links_created

    def add_link_attributes(self, ISD_AS_id, BR1_name, BR2_name, BR1_ifid,
                            in_net_BR1, in_net_BR2, intf1, intf2):
        """Add link properties defined in the SCION topology file

        Adapted from Mininets traffic control implementation: mininet/link.py TCIntf
        """
        mtu = self.get_link_attribute(
            ISD_AS_id, BR1_name, BR1_ifid, 'mtu')  # mtu is always set
        in_net_BR1.cmd(f'ip link set dev {intf1} mtu {mtu}')
        in_net_BR2.cmd(f'ip link set dev {intf2} mtu {mtu}')
        bw = self.get_link_attribute(ISD_AS_id, BR1_name, BR1_ifid, 'bw')
        parent = ' root '
        cmds = []
        if bw and (bw < 0 or bw > 1000):
            error(
                f'Bandwidth limit {bw} is outside supported range 0..1000 - ignoring\n')
        elif bw:
            cmds += ['tc qdisc add dev %s root handle 5:0 htb default 1',
                     'tc class add dev %s parent 5:0 classid 5:1 htb ' +
                     f'rate {bw}Mbit burst 15k']
            info(f'{BR1_name} and {BR2_name} are connected with bw {bw}Mbit/s')
            parent = ' parent 5:1 '

        delay = self.get_link_attribute(ISD_AS_id, BR1_name, BR1_ifid, 'delay')
        jitter = self.get_link_attribute(
            ISD_AS_id, BR1_name, BR1_ifid, 'jitter')
        loss = self.get_link_attribute(ISD_AS_id, BR1_name, BR1_ifid, 'loss')

        if loss and (loss < 0 or loss > 100):
            error(f'Bad loss percentage {loss}\n')

        netemargs = '%s%s%s' % (
            f'delay {delay} ' if delay is not None else '',
            f'{jitter} ' if jitter is not None else '',
            f'loss {loss:.5f} ' if (loss is not None and loss > 0) else '')
        if netemargs:
            cmds += ['tc qdisc add dev %s ' +
                     f'{parent} handle 10: netem {netemargs}']
        # apply commands to both interfaces
        for cmd in cmds:
            in_net_BR1.cmd(cmd % intf1)
            in_net_BR2.cmd(cmd % intf2)

    def get_link_attribute(self, ISD_AS_id, BR_name, BR_interface, metric):
        """Get link attribute from the SCION topology file"""
        topology_dict = self.networks[ISD_AS_id]['topology_dict']
        return topology_dict.get('border_routers', {}) \
                            .get(BR_name, {}) \
                            .get('interfaces', {}) \
                            .get(BR_interface, {}) \
                            .get(metric, None)

    def start_CLI(self):
        """Start global CLI"""
        while True:
            try:
                output('\n')
                output('#################################################\n')
                output('##### Which network do you want to inspect? #####\n')
                output('[0] Shutdown topology\n')
                network_list = list(self.networks.keys())
                for i, network in enumerate(network_list):
                    print(f'[{i+1}] {network}')
                try:
                    network_index = int(input('Network index: ').strip())
                except Exception:
                    print('Invalid network index')
                    continue
                if network_index == 0:
                    break
                if network_index > len(network_list):
                    print('Network index to big')
                    continue
                network = network_list[network_index-1]
                AS = self.networks[network]['AS']
                # start CLI for specific AS
                AS_CLI(networks=self.networks,
                       ASes=self.ASes,
                       AS=AS
                       )
            except (Exception, KeyboardInterrupt):
                pass

    def start(self):
        """After everything is set up, start all ASes"""
        # create individual ASes
        output('------   Creating ASes...   ------\n')
        self.create_networks()
        # create intra-AS links
        output('------   Connect ASes with inter-AS links...   ------\n')
        links_created = set()
        for ISD_AS_id, BR_dict in self.ifids_dict.items():
            links_created = self.add_inter_AS_links(
                ISD_AS_id, BR_dict, links_created)
        output('------   Starting ASes...   ------\n')
        for ISD_AS_id, AS_dict in self.networks.items():
            AS = AS_dict['AS']
            AS.add_SCION_services(BR_name_map=self.BR_name_map_rev[ISD_AS_id])
            AS.start()
            output(f'------   Network {ISD_AS_id} started ------\n')

        info('\n#####         All Networks started!         #####')
        self.start_CLI()
        self.stop()

    def stop(self):
        """Shutdown everything"""
        output('\n------   Stopping Networks...   ------\n')
        for ISD_AS_id, AS_dict in self.networks.items():
            output(f'------   Stopping network {ISD_AS_id}   ------\n')
            AS = AS_dict['AS']
            AS.stop()


def check_scion_apps(apps_argument):
    """Check if the scion apps are cloned and available"""

    if apps_argument is None:
        print('SCION_APPS_PATH is not set')
        print('Either set it as environment variable or pass it as an argument')
        print('Exiting...')
        sys.exit(1)

    apps_path = Path(apps_argument)
    if not apps_path.exists():
        print(f'"SCION_APPS_PATH={apps_path}", path does not exist!')
        if "~" in apps_argument:
            print('Expand the path (e.g. "~" -> "/home/[username]/")')
        print('Exiting...')
        sys.exit(1)

    if not apps_path.is_dir():
        print(f'"SCION_APPS_PATH={apps_path}", path is not a directory!')
        print('Exiting...')
        sys.exit(1)

    for app in ['bin/scion-bwtestclient', 'bin/scion-bwtestserver']:
        if not apps_path.joinpath(app).exists():
            print(f'"SCION_APPS_PATH={apps_path}", path does not contain "{app}"')
            print('Exiting...')
            sys.exit(1)

    return apps_path


def parse_arguments():
    parser = argparse.ArgumentParser(description='Starts all SCION topologies')
    parser.add_argument('-i', '--intra_config', required=True,
                        help='Path to intra.config file')
    parser.add_argument('-a', '--apps', default=os.getenv('SCION_APPS_PATH'),
                        help='Path to SCION apps directory')

    args = parser.parse_args()
    intra_path = Path(args.intra_config)
    if not intra_path.exists():
        print(f'{args.intra_config} does not exist')
        print('Exiting...')
        sys.exit(1)

    apps_path = check_scion_apps(args.apps)

    return intra_path.absolute(), apps_path.absolute()


def main():
    intra_config_path, scion_apps_path = parse_arguments()
    SCIONTopology(intra_config_path, scion_apps_path).start()


if __name__ == '__main__':
    main()
