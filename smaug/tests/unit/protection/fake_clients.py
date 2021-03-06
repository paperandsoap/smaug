# Copyright 2010 OpenStack Foundation
# All Rights Reserved.
#
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

from collections import namedtuple

Stack = namedtuple('Stack', ['id',
                             'stack_status',
                             'stack_name'])

FakeStacks = {}


class FakeHeatClient(object):
    class Stacks(object):
        def create(self, stack_name, template):
            stack = Stack(id='fake_stack_id',
                          stack_name=stack_name,
                          stack_status='CREATE_IN_PROGRESS')
            FakeStacks[stack.id] = stack
            return {
                'stack': {
                    'id': 'stack_id_1',
                }
            }

        def get(self, stack_id):
            return FakeStacks[stack_id]

    def __init__(self):
        self.stacks = self.Stacks()
