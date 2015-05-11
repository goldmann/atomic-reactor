"""
Copyright (c) 2015 Red Hat, Inc
All rights reserved.

This software may be modified and distributed under the terms
of the BSD license. See the LICENSE file for details.
"""

from dock.core import DockerTasker
from dock.inner import DockerBuildWorkflow
from dock.plugin import PreBuildPluginsRunner, PreBuildPlugin
from dock.plugins.pre_add_yum_repo_by_url import AddYumRepoByUrlPlugin
from dock.util import ImageName
from tests.constants import DOCKERFILE_GIT
from tempfile import NamedTemporaryFile


class TestDockerfile(object):
    def __init__(self, lines, wget_expected_at):
        self.lines = lines
        self.wget_expected_at = wget_expected_at

    def get_wget_lines(self, lines, num_wget_lines=1):
        return [lines[n]
                for n in range(self.wget_expected_at,
                               self.wget_expected_at + num_wget_lines)]


DOCKERFILES = {
    "no maintainer":
    TestDockerfile(["# Simple example with no MAINTAINER line\n",
                    "FROM base\n",
                    " RUN yum -y update\n"],
                   wget_expected_at=2),

    "no yum":
    TestDockerfile(["FROM base\n",
                    "# This time there is a MAINTAINER line\n",
                    "# but it's the last last there is\n",
                    "MAINTAINER Example <example@example.com>\n"],
                   wget_expected_at=4),
}


class X(object):
    pass


def prepare(df_path):
    tasker = DockerTasker()
    workflow = DockerBuildWorkflow(DOCKERFILE_GIT, "test-image")
    setattr(workflow, 'builder', X)

    workflow.repos['yum'] = []

    setattr(workflow.builder, 'image_id', "asd123")
    setattr(workflow.builder, 'df_path', str(df_path))
    setattr(workflow.builder, 'base_image', ImageName(repo='Fedora', tag='21'))
    setattr(workflow.builder, 'git_dockerfile_path', None)
    setattr(workflow.builder, 'git_path', None)
    return tasker, workflow


def test_no_repourls(tmpdir):
    for df in DOCKERFILES.values():
        with NamedTemporaryFile(mode="w+t",
                                prefix="Dockerfile",
                                dir=str(tmpdir)) as f:
            f.writelines(df.lines)
            f.flush()
            tasker, workflow = prepare(f.name)
            runner = PreBuildPluginsRunner(tasker, workflow, [{
                'name': AddYumRepoByUrlPlugin.key,
                'args': {'repourls': []}}])
            runner.run()
            assert AddYumRepoByUrlPlugin.key is not None

            f.seek(0)
            # Should be unchanged
            assert f.readlines() == df.lines


def test_single_repourl(tmpdir):
    for df in DOCKERFILES.values():
        with NamedTemporaryFile(mode="w+t",
                                prefix="Dockerfile",
                                dir=str(tmpdir)) as f:
            f.writelines(df.lines)
            f.flush()
            tasker, workflow = prepare(f.name)
            url = 'http://example.com/example%20repo.repo'
            filename = '/etc/yum.repos.d/example repo.repo'
            runner = PreBuildPluginsRunner(tasker, workflow, [{
                'name': AddYumRepoByUrlPlugin.key,
                'args': {'repourls': [url]}}])
            runner.run()

            # Should see a single wget line
            f.seek(0)
            newdf = f.readlines()
            filter_wget = filter(lambda x: x.startswith("RUN wget "), newdf)
            wget_lines = [x for x in filter_wget]
            assert len(wget_lines) == 1

            # It should be where we expect it to be.
            assert (df.get_wget_lines(newdf) ==
                    ["RUN wget -O '%s' %s\n" % (filename, url)])

            # There should be a final 'rm'
            assert newdf[len(newdf) - 1] == "RUN rm -f '%s'\n" % filename


def test_multiple_repourls(tmpdir):
    for df in DOCKERFILES.values():
        with NamedTemporaryFile(mode="w+t",
                                prefix="Dockerfile",
                                dir=str(tmpdir)) as f:
            f.writelines(df.lines)
            f.flush()
            tasker, workflow = prepare(f.name)
            url1 = 'http://example.com/a/b/c/myrepo.repo'
            filename1 = '/etc/yum.repos.d/myrepo.repo'
            url2 = 'http://example.com/repo-2.repo'
            filename2 = '/etc/yum.repos.d/repo-2.repo'
            runner = PreBuildPluginsRunner(tasker, workflow, [{
                'name': AddYumRepoByUrlPlugin.key,
                'args': {'repourls': [url1, url2]}}])
            runner.run()

            # Should see two wget lines.
            f.seek(0)
            newdf = f.readlines()
            filter_wget = filter(lambda x: x.startswith("RUN wget "), newdf)
            wget_lines = [x for x in filter_wget]
            assert len(wget_lines) == 2

            # They should be where we expect them to be.
            assert (set(df.get_wget_lines(newdf, 2)) ==
                    set(["RUN wget -O '%s' %s\n" % (filename1, url1),
                         "RUN wget -O '%s' %s\n" % (filename2, url2)]))

            # For the 'rm' line, they could be in either order
            last = newdf[len(newdf) - 1]
            assert last in ["RUN rm -f '%s' '%s'\n" % (filename1, filename2),
                            "RUN rm -f '%s' '%s'\n" % (filename2, filename1)]
