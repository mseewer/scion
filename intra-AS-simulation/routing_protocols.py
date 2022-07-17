from pathlib import Path

class Zebra(object):
    """Class for Zebra daemon"""

    def __init__(self, FULL_NAME, SCION_PATH):
        self.FULL_NAME = FULL_NAME
        self.SCION_PATH = SCION_PATH
        self.config_path = Path(self.SCION_PATH, f'gen/zebra/{self.FULL_NAME}')
        self.config_path.mkdir(parents=True, exist_ok=True)

    def create_config(self, node):
        """Create zebra config file for this node.
        
        Defines on which interface the zebra daemon should listen.
        """
        name = node.name

        zebra_config_file = Path(self.config_path, f'zebra_{name}.conf')

        config = f"""hostname {name}
password scion
    """

        for intf in node.intfList():
            config += f"""
interface {intf.name}
    ip address {intf.IP()}/{intf.prefixLen}
    no shutdown
        """

        with open(zebra_config_file, mode='w') as f:
            f.writelines(config)

        return zebra_config_file


class OSPF(object):
    """Class for OSPF daemon"""

    def __init__(self, AS):
        self.FULL_NAME = AS.FULL_NAME
        self.net = AS.net
        self.SCION_PATH = AS.SCION_PATH
        self.Zebra = Zebra(self.FULL_NAME, self.SCION_PATH)
        self.nodes = self.net.hosts
        self.temp_path = Path(f'/var/tmp/SCION_INTRA_{self.FULL_NAME}/')
        self.temp_path.mkdir(parents=True, exist_ok=True)
        self.config_path = Path(self.SCION_PATH, f'gen/ospf/{self.FULL_NAME}')
        self.config_path.mkdir(parents=True, exist_ok=True)


    def start(self):
        """Start OSPF daemon on each node"""
        Path(self.SCION_PATH, f'logs/{self.FULL_NAME}/').mkdir(parents=True, exist_ok=True)


        for node in self.nodes:
            name = node.name
            socket = Path(self.temp_path, f'{name}_quagga.api')
            pid_zebra = Path(self.temp_path, f'{name}_zebra.pid')
            pid_ospf = Path(self.temp_path, f'{name}_ospf.pid')
            zebra_config = self.Zebra.create_config(node)
            ospf_config = self.create_config(node)

            node.cmd(f'cd {self.SCION_PATH} ; zebra -u root -d -f {zebra_config} -z {socket} -i {pid_zebra} --log-level debug --log file:logs/{self.FULL_NAME}/zebra_{name}.log 2>&1 &')
            node.cmd(f'cd {self.SCION_PATH} ; ospfd -u root -d -f {ospf_config} -z {socket} -i {pid_ospf} --log-level debug --log file:logs/{self.FULL_NAME}/ospf_{name}.log 2>&1 &')

    def stop(self):
        """Stops OSPF daemon on each node + Zebra daemon"""
        for node in self.nodes:
            name = node.name
            socket = Path(self.temp_path, f'{name}_quagga.api')
            pid_zebra = Path(self.temp_path, f'{name}_zebra.pid')
            pid_ospf = Path(self.temp_path, f'{name}_ospf.pid')
            if node.waiting:
                # give time for the process to stop
                node.monitor(timeoutms=2000)
                node.waiting = False
            node.cmd(f'kill -9 $(cat {pid_zebra})')
            node.cmd(f'kill -9 $(cat {pid_ospf})')
            node.cmd(f'rm {pid_zebra}')
            node.cmd(f'rm {pid_ospf}')
            node.cmd(f'rm {socket}')
        node.cmd(f'rm -rf {self.Zebra.config_path}')
        node.cmd(f'rm -rf {self.config_path}')
        node.cmd(f'rm -rf {self.temp_path}')
        node.cmd('rm -rf /var/tmp/frr/')


    def create_config(self, node):
        """Create OSPF config file for this node.

        Defines on which interface the OSPF daemon should listen.
        Calculates OSPF link cost based on the link properties.
        """
        name = node.name
        config_file = Path(self.config_path, f'ospf_{name}.conf')

        config = f"""!
hostname {name}
password scion
!
"""
        for intf in node.intfList():
            cost = OSPF.calc_cost(intf.params)

            config += f"""interface {intf.name}
    ip ospf area 0
    ip ospf cost {cost}
!
"""
    

        config += f"""router ospf
    ospf router-id {node.defaultIntf().IP()}
    redistribute connected
    passive-interface default
    """


        for intf in node.intfList():
            config += f"""no passive-interface {intf.name}
    """

        with open(config_file, mode='w') as f:
            f.writelines(config)

        return config_file

    @staticmethod
    def calc_cost(params):
        """Calculate OSPF link cost based on the link properties."""
        max_cost = 65535
        cost = 10
        bw = params.get('bw', None)
        delay = params.get('delay', None)
        loss = params.get('loss', None)
        jitter = params.get('jitter', None)

        if bw is not None:
            # increase cost for low bw
            bw = int(bw)
            if int(bw) < 100:
                cost += int(1000/bw)
        if delay is not None:
            # increase cost for high delay
            raw_delay = delay.split('s')[0]
            if raw_delay[-1] == 'm':
                real_delay = raw_delay[:-1]
            else: 
                real_delay = raw_delay * 1000

            cost += int(real_delay)
        if loss is not None:
            # increase cost for high loss
            cost += int(10*int(loss))
        if jitter is not None:
            raw_jitter = jitter.split('s')[0]
            if raw_jitter[-1] == 'm':
                # jitter in ms
                real_jitter = raw_jitter[:-1]
            else: 
                # jitter in s
                real_jitter = raw_jitter * 1000

            cost += int(real_jitter)
        
        return min(cost, max_cost)
