from jumpscale import j
from zerorobot.template.base import TemplateBase


ETCD_TEMPLATE_UID = 'github.com/threefoldtech/0-templates/etcd/0.0.1'

NODE_CLIENT = 'local'

class Coredns(TemplateBase):
    version = '0.0.1'
    template_name = 'coredns'

    def __init__(self, name, guid=None, data=None):
        super().__init__(name=name, guid=guid, data=data)
        self._node_ = None
        self.add_delete_callback(self.uninstall)
        self.recurring_action('_monitor', 30)  # every 30 seconds

    def _monitor(self):
        self.logger.info('Monitor coredns %s' % self.name)
        self.state.check('actions', 'start', 'ok')

        if not self._coredns_sal.is_running():
            self.state.delete('status', 'running')
            self._coredns_sal.deploy()
            self._coredns_sal.start()
            if self._coredns_sal.is_running():
                self.state.set('status', 'running', 'ok')
        else:
            self.state.set('status', 'running', 'ok')
    @property
    def _node_sal(self):
        """
        connection to the node
        """
        return j.clients.zos.get(NODE_CLIENT)

    @property
    def _node(self):
        if not self._node_:
            self._node_ = self.api.services.get(template_account='threefoldtech', template_name='node')
        return self._node_

    @property
    def _coredns_sal(self):
        kwargs = {
            'name': self.name,
            'node': self._node_sal,
            'recursive_resolvers':self.data['upsteram'],
            'zt_identity': self.data['ztIdentity'],
            'nics': self.data['nics'],
            'etcd_endpoint': self._etc_url
        }
        return j.sal_zos.coredns.get(**kwargs)
    @property
    def _etcd(self):
        return self.api.services.get(template_uid=ETCD_TEMPLATE_UID, name=self.data['etcdServerName'])
    @property
    def _etc_url(self):
        result = self._etcd.schedule_action('connection_info').wait(die=True).result
        return result['client_url']
        
    def node_port(self):
        return self.data['nodePort']

    def install(self):
        self.logger.info('Installing CoreDns %s' % self.name)

        coredns_sal = self._coredns_sal

        coredns_sal.deploy()
        self.data['ztIdentity'] = coredns_sal.zt_identity

        self.data['nodePort'] = coredns_sal.node_port
        self.logger.info('Install CoreDns %s is Done' % self.name)
        self.state.set('actions', 'install', 'ok')

    def uninstall(self):
        self.logger.info('Uninstalling CoreDns %s' % self.name)
        self._coredns_sal.destroy()
        self.state.delete('actions', 'install')
        self.state.delete('status', 'running')

    def start(self):
        """
        start coredns server
        """
        self.state.check('actions', 'install', 'ok')
        self.logger.info('Starting CoreDns  %s' % self.name)
        self._coredns_sal.deploy()
        self._coredns_sal.start()
        self.state.set('actions', 'start', 'ok')
        self.state.set('status', 'running', 'ok')

    def stop(self):
        self.state.check('actions', 'install', 'ok')
        self.logger.info('Stopping CoreDns %s' % self.name)
        self._coredns_sal.stop()
        self.state.delete('actions', 'start')
        self.state.delete('status', 'running')

    def register_domain(self, domain, ip, ttl=300):
        self.state.check('actions', 'install', 'ok')
        self.logger.info('adding domain  in etcd server')
        domain_parts = domain.split('.')
        # The key for coredns should start with path(/hosts) and the domain reversed
        # i.e. test.com => /hosts/com/test
        key = "/hosts/{}".format("/".join(domain_parts[::-1]))
        value = '{{"host":"{}","ttl":{}}}'.format(ip, ttl)
        self._etcd.schedule_action('insert_record', args={"key":key, "value": value}).wait(die=True)
        self.logger.info('successful')

