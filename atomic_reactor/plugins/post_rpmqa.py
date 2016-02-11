"""
Copyright (c) 2015 Red Hat, Inc
All rights reserved.

This software may be modified and distributed under the terms
of the BSD license. See the LICENSE file for details.
"""

from atomic_reactor.plugin import PostBuildPlugin


__all__ = ('PostBuildRPMqaPlugin', )


class PostBuildRPMqaPlugin(PostBuildPlugin):
    key = "all_rpm_packages"
    is_allowed_to_fail = False
    rpm_tags = [
        'NAME',
        'VERSION',
        'RELEASE',
        'ARCH',
        'EPOCH',
        'SIZE',
        'SIGMD5',
        'BUILDTIME',
    ]

    def __init__(self, tasker, workflow, image_id, ignore_autogenerated_gpg_keys=True):
        """
        constructor

        :param tasker: DockerTasker instance
        :param workflow: DockerBuildWorkflow instance
        """
        # call parent constructor
        super(PostBuildRPMqaPlugin, self).__init__(tasker, workflow)
        self.image_id = image_id
        self.ignore_autogenerated_gpg_keys = ignore_autogenerated_gpg_keys

    def run(self):
        fmt = ",".join(["%%{%s}" % tag for tag in self.rpm_tags])
        container_id = self.tasker.run(
            self.image_id,
            command="-qa --qf '{0}\n'".format(fmt),
            create_kwargs={"entrypoint": "/bin/rpm"},
            start_kwargs={},
        )
        self.tasker.wait(container_id)
        plugin_output = self.tasker.logs(container_id, stream=False)

        # gpg-pubkey are autogenerated packages by rpm when you import a gpg key
        # these are of course not signed, let's ignore those by default
        if self.ignore_autogenerated_gpg_keys:
            self.log.debug("ignore rpms 'gpg-pubkey'")
            plugin_output = [x for x in plugin_output if not x.startswith("gpg-pubkey,")]

        self.tasker.remove_container(container_id)
        return plugin_output
