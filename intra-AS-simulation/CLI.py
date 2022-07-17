#!/usr/bin/env python3

import networkx as nx
from networkx import NetworkXException
from mininet.cli import CLI
import matplotlib.pyplot as plt
from mininet.log import lg, info, output, warning, error, debug
from mininet.cli import CLI

from test_SCION_in_mininet import test_SCION_ping, test_SCION_bwtest_client_server


def AS_CLI(networks, ASes, AS):
    while True:
        try:
            output('--------------------------------------------------\n')
            output(f'In the CLI of AS: \t {AS.ISD_AS_id} \n')
            output('[0] Back to main menu\n')
            output('[1] Test SCION ping\n')
            output('[2] Start SCION bandwidth test\n')
            output('[3] Start Mininet CLI\n')
            output('[4] Draw intra AS topology\n')
            option = input('Enter option: ').strip()
            if option == '0':
                break
            elif option == '1':
                info('### Testing SCION ###\n')
                try:
                    test_SCION_ping(ASes, AS)
                except Exception as e: 
                    output(f'Test failed: {e}\n')
            elif option == '2':
                info('### Starting SCION bwtest ###\n')
                try:
                    test_SCION_bwtest_client_server(ASes, networks, AS)
                except Exception as e:
                    output(f'Test failed: {e}\n')
            elif option == '3':
                info('### Starting Mininet CLI ###\n')
                output('### Press CTRL+D or type `quit`, `exit` to exit Mininet CLI ###\n')
                CLI(AS.net)
            elif option == '4':
                info('### Drawing intra AS topology ###\n')
                try:
                    try: 
                        nx.draw_planar(AS.graph, node_color='#8691fc', with_labels=True)
                    except NetworkXException:
                        # Graph is not planar
                        nx.draw(AS.graph, node_color='#8691fc', with_labels=True)
                    plt.show() 
                except Exception as e:
                    output(f'Drawing failed: {e}\n')
            else:
                output('Invalid option\n')
        except:
            continue


if __name__ == '__main__':
    pass
