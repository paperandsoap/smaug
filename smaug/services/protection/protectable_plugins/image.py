# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import six

from oslo_log import log as logging

from smaug.common import constants
from smaug import exception
from smaug.i18n import _LE
from smaug import resource
from smaug.services.protection.client_factory import ClientFactory
from smaug.services.protection import protectable_plugin

LOG = logging.getLogger(__name__)


class ImageProtectablePlugin(protectable_plugin.ProtectablePlugin):
    _SUPPORT_RESOURCE_TYPE = constants.IMAGE_RESOURCE_TYPE

    def _glance_client(self, context):
        self._glance_client_instance = \
            ClientFactory.create_client('glance', context)
        return self._glance_client_instance

    def _nova_client(self, context):
        self._nova_client_instance = \
            ClientFactory.create_client('nova', context)
        return self._nova_client_instance

    def get_resource_type(self):
        return self._SUPPORT_RESOURCE_TYPE

    def get_parent_resource_types(self):
        return (constants.SERVER_RESOURCE_TYPE,
                constants.PROJECT_RESOURCE_TYPE,)

    def list_resources(self, context):
        try:
            images = self._glance_client(context).images.list()
        except Exception as e:
            LOG.exception(_LE("List all images from glance failed."))
            raise exception.ListProtectableResourceFailed(
                type=self._SUPPORT_RESOURCE_TYPE,
                reason=six.text_type(e))
        else:
            return [resource.Resource(type=self._SUPPORT_RESOURCE_TYPE,
                                      id=image.id, name=image.name)
                    for image in images]

    def _get_dependent_resources_by_server(self,
                                           context,
                                           parent_resource):
        try:
            server = self._nova_client(context).servers.get(parent_resource.id)
        except Exception as e:
            LOG.exception(_LE("List all server from nova failed."))
            raise exception.ListProtectableResourceFailed(
                type=self._SUPPORT_RESOURCE_TYPE,
                reason=six.text_type(e))
        else:
            return [resource.Resource(type=self._SUPPORT_RESOURCE_TYPE,
                                      id=server.image['id'],
                                      name=server.image['name'])]

    def _get_dependent_resources_by_project(self,
                                            context,
                                            parent_resource):
        try:
            images = self._glance_client(context).images.list()
        except Exception as e:
            LOG.exception(_LE("List all images from glance failed."))
            raise exception.ListProtectableResourceFailed(
                type=self._SUPPORT_RESOURCE_TYPE,
                reason=six.text_type(e))
        else:
            return [resource.Resource(type=self._SUPPORT_RESOURCE_TYPE,
                                      id=image.id,
                                      name=image.name)
                    for image in images
                    if image.owner == parent_resource.id]

    def show_resource(self, context, resource_id):
        try:
            image = self._glance_client(context).images.get(resource_id)
        except Exception as e:
            LOG.exception(_LE("Show a image from glance failed."))
            raise exception.ListProtectableResourceFailed(
                type=self._SUPPORT_RESOURCE_TYPE,
                reason=six.text_type(e))
        else:
            return resource.Resource(type=self._SUPPORT_RESOURCE_TYPE,
                                     id=image.id, name=image.name)

    def get_dependent_resources(self, context, parent_resource):
        if parent_resource.type == constants.SERVER_RESOURCE_TYPE:
            return self._get_dependent_resources_by_server(context,
                                                           parent_resource)

        if parent_resource.type == constants.PROJECT_RESOURCE_TYPE:
            return self._get_dependent_resources_by_project(context,
                                                            parent_resource)

        return []
