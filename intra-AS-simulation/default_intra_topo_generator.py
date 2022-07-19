#!/usr/bin/env python3

import argparse
from collections import defaultdict
import sys
import yaml

from pathlib import Path


def parse_arguments():
    parser = argparse.ArgumentParser(description='Generates a default intra-domain config file')
    parser.add_argument('-i', '--input', required=True,
                        help='Path to SCION topology file')
    parser.add_argument('-o', '--output_file',
                        help='Output filename where the generated intra.config should be stored')
    parser.add_argument('-p', '--protocol', default='OSPF',
                        help='default intra routring protocol')

    args = parser.parse_args()
    p_in = Path(args.input)
    if not p_in.exists():
        print(f'{args.input} does not exist')
        sys.exit(1)

    if args.output_file is None:
        file_name = Path('intra.config')
        i = 0
        while(file_name.exists()):
            i += 1
            file_name = Path(f'intra.config{i}')
    else:
        file_name = Path(args.output_file)
        file_name.parent.mkdir(parents=True, exist_ok=True)

    protocol = args.protocol.upper()
    if protocol not in ['OSPF']:
        print(f'{args.protocol} is not a valid protocol')
        sys.exit(1)

    return p_in.absolute(), file_name.absolute(), protocol


def get_BRs_per_AS(topo_dict, AS_names):
    mapping = defaultdict(list)
    for AS_name in AS_names:
        for link in topo_dict['links']:
            a = link['a']
            b = link['b']

            for x in [a, b]:
                if x.startswith(AS_name):
                    x_no_itf = x.split('#')[0]
                    x_split = x_no_itf.split('-')
                    if len(x_split) == 3:
                        # specific ID is given, check if already contained
                        if x_no_itf in mapping[AS_name]:
                            continue
                        # don't save interface, because this BR will have multiple interfaces
                        mapping[AS_name].append(x_no_itf)
                    else:
                        # no specific ID is given, save all interfaces
                        mapping[AS_name].append(x)
    return mapping


def generate_intra_dict(BRs_per_AS, protocol):
    intra_dict = {'ASes': {}}
    for AS, BRs in BRs_per_AS.items():
        BR_map = {}
        for i, BR in enumerate(BRs):
            BR_map[f'br{i+1}'] = BR

        intra_dict['ASes'][AS] = {
                                    'Intra-Topology': 'default.intra.topo',
                                    'Routing-Protocol': f'{protocol}',
                                    'Borderrouter': BR_map
                                 }
    return intra_dict


def main():
    in_file, out_file, protocol = parse_arguments()
    with open(in_file, 'r') as f:
        topo_dict = yaml.safe_load(f)
    AS_names = topo_dict['ASes'].keys()
    BRs_per_AS = get_BRs_per_AS(topo_dict, AS_names)
    intra_dict = generate_intra_dict(BRs_per_AS, protocol)
    with open(out_file, 'w') as f:
        yaml.dump(intra_dict, f)

    print(f'Intra-domain config file generated: {out_file}')


if __name__ == '__main__':
    main()
