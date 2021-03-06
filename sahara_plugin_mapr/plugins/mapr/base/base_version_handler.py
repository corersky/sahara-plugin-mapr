# Copyright (c) 2015, MapR Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import collections as c

import sahara.plugins.provisioning as p
import sahara.plugins.utils as u
from sahara_plugin_mapr.i18n import _
import sahara_plugin_mapr.plugins.mapr.abstract.version_handler as vh
import sahara_plugin_mapr.plugins.mapr.base.base_cluster_configurer as b_conf
import sahara_plugin_mapr.plugins.mapr.base.base_cluster_validator as bv
import sahara_plugin_mapr.plugins.mapr.base.base_edp_engine as edp
import sahara_plugin_mapr.plugins.mapr.base.base_health_checker as health
import sahara_plugin_mapr.plugins.mapr.base.base_node_manager as bs
from sahara_plugin_mapr.plugins.mapr import images
import sahara_plugin_mapr.plugins.mapr.util.general as util


class BaseVersionHandler(vh.AbstractVersionHandler):
    def __init__(self):
        self._validator = bv.BaseValidator()
        self._configurer = b_conf.BaseConfigurer()
        self._health_checker = health.BaseHealthChecker()
        self._node_manager = bs.BaseNodeManager()
        self._version = None
        self._required_services = []
        self._services = []
        self._node_processes = {}
        self._configs = []
        self.images = images

    def get_edp_engine(self, cluster, job_type):
        if job_type in edp.MapROozieJobEngine.get_supported_job_types():
            return edp.MapROozieJobEngine(cluster)
        return None

    def get_edp_job_types(self):
        return edp.MapROozieJobEngine.get_supported_job_types()

    def get_edp_config_hints(self, job_type):
        return edp.MapROozieJobEngine.get_possible_job_config(job_type)

    def get_services(self):
        return self._services

    def get_required_services(self):
        return self._required_services

    def get_node_processes(self):
        if not self._node_processes:
            self._node_processes = {
                s.ui_name: [np.ui_name for np in s.node_processes]
                for s in self.get_services() if s.node_processes}
        return self._node_processes

    def get_configs(self):
        if not self._configs:
            configs = [c for s in self.get_services() for c in s.get_configs()]
            configs += self._get_version_configs()
            configs += self._get_repo_configs()
            self._configs = util.unique_list(configs)
        return self._configs

    def _get_repo_configs(self):
        ubuntu_base = p.Config(
            name="Ubuntu base repo",
            applicable_target="general",
            scope='cluster',
            priority=1,
            default_value="",
            description=_(
                'Specifies Ubuntu MapR core repository.')
        )
        centos_base = p.Config(
            name="CentOS base repo",
            applicable_target="general",
            scope='cluster',
            priority=1,
            default_value="",
            description=_(
                'Specifies CentOS MapR core repository.')
        )
        ubuntu_eco = p.Config(
            name="Ubuntu ecosystem repo",
            applicable_target="general",
            scope='cluster',
            priority=1,
            default_value="",
            description=_(
                'Specifies Ubuntu MapR ecosystem repository.')
        )
        centos_eco = p.Config(
            name="CentOS ecosystem repo",
            applicable_target="general",
            scope='cluster',
            priority=1,
            default_value="",
            description=_(
                'Specifies CentOS MapR ecosystem repository.')
        )
        return [ubuntu_base, centos_base, ubuntu_eco, centos_eco]

    def _get_version_configs(self):
        services = self.get_services()

        service_version_dict = c.defaultdict(list)
        for service in services:
            service_version_dict[service.ui_name].append(service.version)

        result = []
        for service in services:
            versions = service_version_dict[service.ui_name]
            if len(versions) > 1:
                result.append(service.get_version_config(versions))

        return result

    def get_configs_dict(self):
        configs = dict()
        for service in self.get_services():
            configs.update(service.get_configs_dict())
        return configs

    def configure_cluster(self, cluster):
        instances = u.get_instances(cluster)
        cluster_context = self.get_context(cluster, added=instances)
        self._configurer.configure(cluster_context)

    def start_cluster(self, cluster):
        instances = u.get_instances(cluster)
        cluster_context = self.get_context(cluster, added=instances)
        self._node_manager.start(cluster_context)
        self._configurer.post_start(cluster_context)

    def validate(self, cluster):
        cluster_context = self.get_context(cluster)
        self._validator.validate(cluster_context)

    def validate_scaling(self, cluster, existing, additional):
        cluster_context = self.get_context(cluster)
        self._validator.validate_scaling(cluster_context, existing, additional)

    def scale_cluster(self, cluster, instances):
        cluster_context = self.get_context(cluster, added=instances)
        cluster_context._cluster_services = None
        self._configurer.configure(cluster_context, instances)
        self._configurer.update(cluster_context, instances)
        self._node_manager.start(cluster_context, instances)

    def decommission_nodes(self, cluster, instances):
        cluster_context = self.get_context(cluster, removed=instances)
        cluster_context._cluster_services = None
        self._node_manager.move_nodes(cluster_context, instances)
        self._node_manager.stop(cluster_context, instances)
        self._node_manager.await_no_heartbeat()
        self._node_manager.remove_nodes(cluster_context, instances)
        self._configurer.update(cluster_context, instances)

    def get_open_ports(self, node_group):
        result = []
        for service in self.get_services():
            for node_process in service.node_processes:
                if node_process.ui_name in node_group.node_processes:
                    result += node_process.open_ports
        return util.unique_list(result)

    def get_cluster_checks(self, cluster):
        cluster_context = self.get_context(cluster)
        return self._health_checker.get_checks(cluster_context)

    def get_image_arguments(self):
        if hasattr(self, 'images'):
            return self.images.get_image_arguments()
        else:
            return NotImplemented

    def pack_image(self, hadoop_version, remote, test_only=False,
                   image_arguments=None):
        if hasattr(self, 'images'):
            self.images.pack_image(
                remote, test_only=test_only, image_arguments=image_arguments)

    def validate_images(self, cluster, test_only=False, image_arguments=None):
        if hasattr(self, 'images'):
            self.images.validate_images(
                cluster, test_only=test_only, image_arguments=image_arguments)
