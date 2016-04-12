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

"""
OperationEngine Service
"""

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging

from smaug import exception
from smaug import manager
from smaug import objects
from smaug.operationengine.engine import trigger_manager
from smaug.operationengine import scheduled_operation_state


CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class OperationEngineManager(manager.Manager):
    """Smaug OperationEngine Manager."""

    RPC_API_VERSION = '1.0'

    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, service_name=None,
                 *args, **kwargs):
        super(OperationEngineManager, self).__init__(*args, **kwargs)
        self._service_id = None
        self._trigger_manager = None

    def init_host(self, **kwargs):
        self._trigger_manager = trigger_manager.TriggerManager()
        self._service_id = kwargs.get("service_id")

    def cleanup_host(self):
        self._trigger_manager.shutdown()

    @messaging.expected_exceptions(exception.TriggerNotFound,
                                   exception.InvalidInput,
                                   exception.InvalidOperationObject)
    def create_scheduled_operation(self, context, operation_id, trigger_id):
        LOG.debug("Create scheduled operation.")

        # register operation
        self._trigger_manager.register_operation(trigger_id, operation_id)

        # create ScheduledOperationState record
        state_info = {
            "operation_id": operation_id,
            "service_id": self._service_id,
            "state": scheduled_operation_state.REGISTERED
        }
        operation_state = objects.ScheduledOperationState(
            context, **state_info)
        try:
            operation_state.create()
        except Exception:
            self._trigger_manager.unregister_operation(
                trigger_id, operation_id)
            raise

    @messaging.expected_exceptions(exception.ScheduledOperationStateNotFound,
                                   exception.TriggerNotFound,
                                   exception.InvalidInput)
    def delete_scheduled_operation(self, context, operation_id, trigger_id):
        LOG.debug("Delete scheduled operation.")

        operation_state = objects.ScheduledOperationState.\
            get_by_operation_id(context, operation_id)
        if scheduled_operation_state.DELETED != operation_state.state:
            operation_state.state = scheduled_operation_state.DELETED
            operation_state.save()

        self._trigger_manager.unregister_operation(trigger_id, operation_id)

    @messaging.expected_exceptions(exception.InvalidInput)
    def create_trigger(self, context, trigger):
        self._trigger_manager.add_trigger(trigger.id, trigger.type,
                                          trigger.properties)

    @messaging.expected_exceptions(exception.TriggerNotFound,
                                   exception.DeleteTriggerNotAllowed)
    def delete_trigger(self, context, trigger_id):
        self._trigger_manager.remove_trigger(trigger_id)

    @messaging.expected_exceptions(exception.TriggerNotFound)
    def update_trigger(self, context, trigger):
        self._trigger_manager.update_trigger(trigger.id, trigger.properties)
