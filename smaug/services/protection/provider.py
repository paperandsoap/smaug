# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os

from oslo_config import cfg
from oslo_log import log as logging
from smaug.common import constants
from smaug.i18n import _LE
from smaug.resource import Resource
from smaug.services.protection import bank_plugin
from smaug.services.protection.checkpoint import CheckpointCollection
from smaug.services.protection.graph import GraphWalker
from smaug.services.protection.protectable_registry import ProtectableRegistry
from smaug.services.protection.resource_graph import ResourceGraphContext
from smaug.services.protection.resource_graph \
    import ResourceGraphWalkerListener
from smaug import utils

provider_opts = [
    cfg.MultiStrOpt('plugin',
                    default='',
                    help='plugins to use for protection'),
    cfg.StrOpt('bank',
               default='',
               help='bank plugin to use for storage'),
    cfg.StrOpt('description',
               default='',
               help='the description of provider'),
    cfg.StrOpt('name',
               default='',
               help='the name of provider'),
    cfg.StrOpt('id',
               default='',
               help='the provider id')
]
CONF = cfg.CONF

LOG = logging.getLogger(__name__)

PROTECTION_NAMESPACE = 'smaug.protections'

CONF.register_opt(cfg.StrOpt('provider_config_dir',
                             default='providers.d',
                             help='Configuration directory for providers.'
                                  ' Absolute path, or relative to smaug '
                                  ' configuration directory.'))


class PluggableProtectionProvider(object):
    def __init__(self, provider_config):
        super(PluggableProtectionProvider, self).__init__()
        self._config = provider_config
        self._id = self._config.provider.id
        self._name = self._config.provider.name
        self._description = self._config.provider.description
        self._extended_info_schema = {'options_schema': {},
                                      'restore_schema': {},
                                      'saved_info_schema': {}}
        self.checkpoint_collection = None
        self._bank_plugin = None
        self._plugin_map = {}

        if hasattr(self._config.provider, 'bank') \
                and not self._config.provider.bank:
            raise ImportError("Empty bank")

        self._load_bank(self._config.provider.bank)
        self._bank = bank_plugin.Bank(self._bank_plugin)
        self.checkpoint_collection = CheckpointCollection(
            self._bank)

        if hasattr(self._config.provider, 'plugin'):
            for plugin_name in self._config.provider.plugin:
                if not plugin_name:
                    raise ImportError("Empty protection plugin")
                self._load_plugin(plugin_name)

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return self._description

    @property
    def extended_info_schema(self):
        return self._extended_info_schema

    @property
    def bank(self):
        return self._bank

    @property
    def plugins(self):
        return self._plugin_map

    def _load_bank(self, bank_name):
        try:
            plugin = utils.load_plugin(PROTECTION_NAMESPACE, bank_name,
                                       self._config)
        except Exception:
            LOG.error(_LE("Load bank plugin: '%s' failed."), bank_name)
            raise
        else:
            self._bank_plugin = plugin

    def _load_plugin(self, plugin_name):
        try:
            plugin = utils.load_plugin(PROTECTION_NAMESPACE, plugin_name,
                                       self._config)
        except Exception:
            LOG.error(_LE("Load protection plugin: '%s' failed."), plugin_name)
            raise
        else:
            self._plugin_map[plugin_name] = plugin
            for resource in plugin.get_supported_resources_types():
                if hasattr(plugin, 'get_options_schema'):
                    self._extended_info_schema['options_schema'][resource] \
                        = plugin.get_options_schema(resource)
                if hasattr(plugin, 'get_restore_schema'):
                    self._extended_info_schema['restore_schema'][resource] \
                        = plugin.get_restore_schema(resource)
                if hasattr(plugin, 'get_saved_info_schema'):
                    self._extended_info_schema['saved_info_schema'][resource] \
                        = plugin.get_saved_info_schema(resource)

    def get_checkpoint_collection(self):
        return self.checkpoint_collection

    def build_task_flow(self, ctx):
        cntxt = ctx["context"]
        workflow_engine = ctx["workflow_engine"]
        operation = ctx["operation_type"]

        resource_context = None
        resource_graph = None

        if operation == constants.OPERATION_PROTECT:
            plan = ctx["plan"]
            task_flow = workflow_engine.build_flow(flow_name=plan.get('id'))
            resources = plan.get('resources')
            parameters = plan.get('parameters')
            graph_resources = []
            for resource in resources:
                graph_resources.append(Resource(type=resource['type'],
                                                id=resource['id'],
                                                name=resource['name']))
            # TODO(luobin): pass registry in ctx
            registry = ProtectableRegistry()
            registry.load_plugins()
            resource_graph = registry.build_graph(cntxt, graph_resources)
            resource_context = ResourceGraphContext(
                cntxt=cntxt,
                operation=operation,
                workflow_engine=workflow_engine,
                task_flow=task_flow,
                plugin_map=self._plugin_map,
                parameters=parameters
            )
        if operation == constants.OPERATION_RESTORE:
            restore = ctx['restore']
            task_flow = workflow_engine.build_flow(
                flow_name=restore.get('id'))
            checkpoint = ctx["checkpoint"]
            resource_graph = checkpoint.resource_graph
            parameters = restore.get('parameters')
            heat_template = ctx["heat_template"]
            resource_context = ResourceGraphContext(
                cntxt=cntxt,
                checkpoint=checkpoint,
                operation=operation,
                workflow_engine=workflow_engine,
                task_flow=task_flow,
                plugin_map=self._plugin_map,
                parameters=parameters,
                heat_template=heat_template
            )

        # TODO(luobin): for other type operations

        walker_listener = ResourceGraphWalkerListener(resource_context)
        graph_walker = GraphWalker()
        graph_walker.register_listener(walker_listener)
        graph_walker.walk_graph(resource_graph)

        if operation == constants.OPERATION_PROTECT:
            return {"task_flow": walker_listener.context.task_flow,
                    "status_getters": walker_listener.context.status_getters,
                    "resource_graph": resource_graph}
        if operation == constants.OPERATION_RESTORE:
            return {"task_flow": walker_listener.context.task_flow}

        # TODO(luobin): for other type operations


class ProviderRegistry(object):
    def __init__(self):
        super(ProviderRegistry, self).__init__()
        self.providers = {}
        self._load_providers()

    def _load_providers(self):
        """load provider"""
        config_dir = utils.find_config(CONF.provider_config_dir)

        for config_file in os.listdir(config_dir):
            if not config_file.endswith('.conf'):
                continue
            config_path = os.path.abspath(os.path.join(config_dir,
                                                       config_file))
            provider_config = cfg.ConfigOpts()
            provider_config(args=['--config-file=' + config_path])
            provider_config.register_opts(provider_opts, 'provider')
            try:
                provider = PluggableProtectionProvider(provider_config)
            except Exception:
                LOG.error(_LE("Load provider: %s failed."),
                          provider_config.provider.name)
            else:
                self.providers[provider.id] = provider

    def list_providers(self, marker=None, limit=None, sort_keys=None,
                       sort_dirs=None, filters=None):
        # TODO(wangliuan) How to use the list option
        return [dict(id=provider.id, name=provider.name,
                     description=provider.description)
                for provider in self.providers.values()]

    def show_provider(self, provider_id):
        return self.providers.get(provider_id, None)
