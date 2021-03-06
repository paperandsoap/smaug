# Licensed under the Apache License, Version 2.0 (the "License"); you may
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

import smaug.services.protection.graph as graph
from smaug.services.protection.resource_graph import ResourceGraphContext
from smaug.services.protection.resource_graph \
    import ResourceGraphWalkerListener

from smaug.tests import base
from smaug.tests.unit.protection.fakes import FakeProtectionPlugin
from smaug.tests.unit.protection.fakes import plan_resources
from smaug.tests.unit.protection.fakes import resource_map


class ResourceGraphWalkerListenerTest(base.TestCase):
    def test_resource_graph_walker_listener_plan(self):
        expected_calls = [
            ("on_resource_start", 'A', True),
            ("on_resource_start", 'C', True),
            ("on_resource_start", 'D', True),
            ("on_resource_end", 'D'),
            ("on_resource_start", 'E', True),
            ("on_resource_end", 'E'),
            ("on_resource_end", 'C'),
            ("on_resource_end", 'A'),
            ("on_resource_start", 'B', True),
            ("on_resource_start", 'C', False),
            ("on_resource_start", 'D', False),
            ("on_resource_end", 'D'),
            ("on_resource_start", 'E', False),
            ("on_resource_end", 'E'),
            ("on_resource_end", 'C'),
            ("on_resource_end", 'B'),
        ]

        fake_cntxt = "fake_cntxt"
        fake_protection_plugin = FakeProtectionPlugin(expected_calls)
        fake_context = ResourceGraphContext(
            fake_cntxt,
            plugin_map={"fake_plugin": fake_protection_plugin})
        listener = ResourceGraphWalkerListener(fake_context)

        walker = graph.GraphWalker()
        walker.register_listener(listener)
        walker.walk_graph(graph.build_graph(plan_resources,
                                            resource_map.__getitem__))
        self.assertEqual(len(listener.context.status_getters), 5)

    def tearDown(self):
        super(ResourceGraphWalkerListenerTest, self).tearDown()
