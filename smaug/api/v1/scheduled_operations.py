#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""The scheduled operations api."""

from oslo_log import log as logging
from oslo_utils import uuidutils
from webob import exc

from smaug.api import common
from smaug.api.openstack import wsgi
from smaug import exception
from smaug.i18n import _
from smaug import objects
from smaug import policy
from smaug.services.operationengine import api as operationengine_api
from smaug.services.operationengine import operation_manager
from smaug import utils

LOG = logging.getLogger(__name__)

OPERATION_MANAGER = operation_manager.OperationManager()


def check_policy(context, action, target_obj=None):
    _action = 'scheduled_operation:%s' % action
    policy.enforce(context, _action, target_obj)


class ScheduledOperationViewBuilder(common.ViewBuilder):
    """Model a server API response as a python dictionary."""

    _collection_name = "scheduled_operations"

    def detail(self, request, operation):
        """Detailed view of a single scheduled operation."""

        operation_ref = {
            'scheduled_operation': {
                'id': operation.get('id'),
                'name': operation.get('name'),
                'operation_type': operation.get('operation_type'),
                'project_id': operation.get('project_id'),
                'trigger_id': operation.get('trigger_id'),
                'operation_definition': operation.get('operation_definition'),
            }
        }
        return operation_ref

    def detail_list(self, request, operations):
        """Detailed view of a list of operations."""
        return self._list_view(self.detail, request, operations)

    def _list_view(self, func, request, operations):
        operations_list = [func(request, item)['scheduled_operation']
                           for item in operations]

        operations_links = self._get_collection_links(request,
                                                      operations,
                                                      self._collection_name,
                                                      )
        ret = {'operations': operations_list}
        if operations_links:
            ret['operations_links'] = operations_links

        return ret


class ScheduledOperationController(wsgi.Controller):
    """The Scheduled Operation API controller for the OpenStack API."""

    _view_builder_class = ScheduledOperationViewBuilder

    def __init__(self):
        self.operationengine_api = operationengine_api.API()
        super(ScheduledOperationController, self).__init__()

    def create(self, req, body):
        """Creates a new scheduled operation."""

        LOG.debug('Create scheduled operation start')

        if not self.is_valid_body(body, 'scheduled_operation'):
            raise exc.HTTPUnprocessableEntity()
        LOG.debug('Create a scheduled operation, request body: %s', body)

        context = req.environ['smaug.context']
        check_policy(context, 'create')
        operation_info = body['scheduled_operation']

        name = operation_info.get("name", None)
        operation_type = operation_info.get("operation_type", None)
        operation_definition = operation_info.get(
            "operation_definition", None)
        if name is None:
            msg = _("Operation name or type or definition is not provided.")
            raise exc.HTTPBadRequest(explanation=msg)

        self.validate_name_and_description(operation_info)

        try:
            OPERATION_MANAGER.check_operation_definition(
                operation_type, operation_definition)
        except exception.Invalid as ex:
            raise exc.HTTPBadRequest(explanation=ex.msg)
        except Exception as ex:
            self._raise_unknown_exception(ex)

        trigger_id = operation_info.get("trigger_id", None)
        trigger = self._get_trigger_by_id(context, trigger_id)
        if context.project_id != trigger.project_id:
            msg = _("Invalid trigger id provided.")
            raise exc.HTTPBadRequest(explanation=msg)

        operation_obj = {
            'name': operation_info.get('name', None),
            'operation_type': operation_type,
            'project_id': context.project_id,
            'trigger_id': trigger_id,
            'operation_definition': operation_definition,
        }
        try:
            operation = objects.ScheduledOperation(context=context,
                                                   **operation_obj)
            operation.create()
        except Exception as ex:
            self._raise_unknown_exception(ex)

        try:
            self._create_scheduled_operation(context, operation.id,
                                             trigger_id)
        except Exception:
            try:
                operation.destroy()
            except Exception:
                pass

            raise

        return self._view_builder.detail(req, operation)

    def delete(self, req, id):
        """Delete a scheduled operation."""

        LOG.debug('Delete scheduled operation(%s) start', id)

        context = req.environ['smaug.context']
        operation = self._get_operation_by_id(context, id, ['trigger'])
        trigger = operation.trigger

        check_policy(context, 'delete', operation)

        try:
            self.operationengine_api.delete_scheduled_operation(
                context, id, trigger.id)

        except (exception.ScheduledOperationStateNotFound,
                exception.TriggerNotFound,
                Exception) as ex:
            self._raise_unknown_exception(ex)

        operation.destroy()

    def show(self, req, id):
        """Return data about the given operation."""

        LOG.debug('Get scheduled operation(%s) start', id)

        context = req.environ['smaug.context']
        operation = self._get_operation_by_id(context, id)
        check_policy(context, 'get', operation)

        return self._view_builder.detail(req, operation)

    def index(self, req):
        """Returns a list of operations, transformed through view builder."""

        context = req.environ['smaug.context']
        check_policy(context, 'list')

        params = req.params.copy()
        LOG.debug('List scheduled operation start, params=%s', params)
        marker, limit, offset = common.get_pagination_params(params)
        sort_keys, sort_dirs = common.get_sort_params(params)
        filters = params

        valid_filters = ["all_tenants", "name", "operation_type",
                         "trigger_id", "operation_definition"]
        utils.remove_invalid_filter_options(context, filters, valid_filters)
        utils.check_filters(filters)

        all_tenants = utils.get_bool_param("all_tenants", filters)
        if not (context.is_admin and all_tenants):
            filters["project_id"] = context.project_id

        try:
            operations = objects.ScheduledOperationList.get_by_filters(
                context, filters, limit, marker, sort_keys, sort_dirs)
        except Exception as ex:
            self._raise_unknown_exception(ex)

        return self._view_builder.detail_list(req, operations)

    def _get_operation_by_id(self, context, id, expect_attrs=[]):
        if not uuidutils.is_uuid_like(id):
            msg = _("Invalid operation id provided.")
            raise exc.HTTPBadRequest(explanation=msg)

        try:
            operation = objects.ScheduledOperation.get_by_id(
                context, id, expect_attrs)
        except exception.ScheduledOperationNotFound as error:
            raise exc.HTTPNotFound(explanation=error.msg)
        except Exception as ex:
            self._raise_unknown_exception(ex)

        return operation

    def _get_trigger_by_id(self, context, trigger_id):
        if not uuidutils.is_uuid_like(trigger_id):
            msg = _("Invalid trigger id provided.")
            raise exc.HTTPBadRequest(explanation=msg)
        try:
            trigger = objects.Trigger.get_by_id(context, trigger_id)
        except exception.NotFound as ex:
            raise exc.HTTPNotFound(explanation=ex.msg)
        except Exception as ex:
            self._raise_unknown_exception(ex)

        return trigger

    def _create_scheduled_operation(self, context, operation_id, trigger_id):
        try:
            self.operationengine_api.create_scheduled_operation(
                context, operation_id, trigger_id)

        except (exception.InvalidInput,
                exception.TriggerIsInvalid) as ex:
            raise exc.HTTPBadRequest(explanation=ex.msg)

        except (exception.TriggerNotFound, Exception) as ex:
            self._raise_unknown_exception(ex)

    def _raise_unknown_exception(self, exception_instance):
        value = exception_instance.msg if isinstance(
            exception_instance, exception.SmaugException) else type(
            exception_instance)
        msg = (_('Unexpected API Error. Please report this at '
                 'http://bugs.launchpad.net/smaug/ and attach the '
                 'Smaug API log if possible.\n%s') % value)
        raise exc.HTTPInternalServerError(explanation=msg)


def create_resource():
    return wsgi.Resource(ScheduledOperationController())
