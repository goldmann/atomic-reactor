import json
import argparse
import logging
import os
import sys
import pkg_resources

from dock import build_image_here, build_image_in_privileged_container, \
    build_image_using_hosts_docker, set_logging
from dock.constants import CONTAINER_BUILD_JSON_PATH, CONTAINER_RESULTS_JSON_PATH, DESCRIPTION, PROG
from dock.buildimage import BuildImageBuilder
from dock.inner import BuildResultsEncoder, build_inside, BuildResults


logger = logging.getLogger('dock')


def cli_create_build_image(args):
    b = BuildImageBuilder(dock_tarball_path=args.dock_tarball_path,
                          dock_local_path=args.dock_local_path,
                          dock_remote_path=args.dock_remote_git,
                          use_official_dock_git=args.dock_latest)
    try:
        b.create_image(args.dockerfile_dir_path, args.image, use_cache=args.use_cache)
    except RuntimeError:
        logger.error("Build failed.")
        sys.exit(1)
    sys.exit(0)


def cli_build_image(args):
    if args.plugin_files:
        args.plugin_files = [os.path.abspath(f) for f in args.plugin_files]
    if args.json:
        with open(args.json) as json_fp:
            common_kwargs = json.load(json_fp)
    else:
        common_kwargs = {
            "git_url": args.git_url,
            "image": args.image,
            "git_dockerfile_path": args.git_path,
            "git_commit": args.git_commit,
            "parent_registry": args.source_registry,
            "parent_registry_insecure": args.source_registry_insecure,
            "target_registries": args.target_registries,
            "target_registries_insecure": args.target_registries_insecure,
        }
    response = BuildResults()
    if args.method == "hostdocker":
        response = build_image_using_hosts_docker(args.build_image, **common_kwargs)
    elif args.method == "privileged":
        response = build_image_in_privileged_container(args.build_image, **common_kwargs)
    elif args.method == 'here':
        build_result = build_image_here(plugin_files=args.plugin_files, **common_kwargs)
        if build_result.is_failed():
            response.return_code = -1
        else:
            response.return_code = 0

    if response.return_code != 0:
        logger.error("build failed")
    sys.exit(response.return_code)


def cli_inside_build(args):
    build_inside(input=args.input, input_args=args.input_arg, substitutions=args.substitute)


def store_result(results):
    # TODO: move this to api, it shouldnt be part of CLI
    with open(CONTAINER_RESULTS_JSON_PATH, 'w') as results_json_fd:
        json.dump(results, results_json_fd, cls=BuildResultsEncoder)


class CLI(object):
    def __init__(self, formatter_class=argparse.HelpFormatter, prog=PROG):
        self.parser = argparse.ArgumentParser(
            prog=prog,
            description=DESCRIPTION,
            formatter_class=formatter_class,
        )
        self.build_parser = None
        self.bi_parser = None
        self.ib_parser = None

    def set_arguments(self):
        try:
            version = pkg_resources.get_distribution("dock").version
        except pkg_resources.DistributionNotFound:
            version = "GIT"

        exclusive_group = self.parser.add_mutually_exclusive_group()
        exclusive_group.add_argument("-q", "--quiet", action="store_true")
        exclusive_group.add_argument("-v", "--verbose", action="store_true")
        exclusive_group.add_argument("-V", "--version", action="version", version=version)

        subparsers = self.parser.add_subparsers(help='commands')

        # BUILDING IMAGES

        self.build_parser = subparsers.add_parser('build',
                                                  usage="%s [OPTIONS] build" % PROG,
                                                  description='This command enables you to build images. '
                                                              'There are several methods for performing the build: '
                                                              'inside a build container using docker from host, '
                                                              'inside a build container using new instance of docker, '
                                                              'or within current environment')
        self.build_parser.set_defaults(func=cli_build_image)
        self.build_parser.add_argument("--json", action="store", help="path to build json")
        self.build_parser.add_argument("--build-image", action='store',
                                       help="name of build image to use "
                                            "(build image type has to match method)")
        self.build_parser.add_argument("--image", action='store',
                                       help="name under the image will be accessible")
        self.build_parser.add_argument("--git-url", action='store', metavar="URL",
                                       help="URL to git repo")
        self.build_parser.add_argument("--git-path", action='store',
                                       help="path to Dockerfile within git repo (default is ./)")
        self.build_parser.add_argument("--git-commit", action='store',
                                       help="checkout this commit (default is master)")
        self.build_parser.add_argument("--source-registry", action='store',
                                       metavar="REGISTRY",
                                       help="registry to pull base image from")
        self.build_parser.add_argument("--source-registry-insecure", action='store_true',
                                       help="allow connecting to source registry over plain http")
        self.build_parser.add_argument("--target-registries", action='store', nargs="*",
                                       metavar="REGISTRY",
                                       help="list of registries to push image to")
        self.build_parser.add_argument("--target-registries-insecure", action='store_true',
                                       help="allow connecting to target registries over plain http")
        self.build_parser.add_argument("--load-plugin", action="store", nargs="*", metavar="PLUGIN_FILE",
                                       dest="plugin_files", help="list of files where plugins live")
        self.build_parser.add_argument("--method", action='store', choices=["hostdocker", "privileged", "here"],
                                       required=True,
                                       help="choose method for building image: 'hostdocker' mounts socket "
                                            "inside container, 'privileged' spawns privileged container and "
                                            "runs separate docker instance inside and finally 'here' executes"
                                            "build in current environment")

        # CREATE BUILD IMAGE

        self.bi_parser = subparsers.add_parser('create-build-image',
                                               usage="%s [OPTIONS] create-build-image" % PROG,
                                               description='Create build image; dock installs itself inside and '
                                                           'is capable of building images within this image.')
        self.bi_parser.set_defaults(func=cli_create_build_image)
        dock_source = self.bi_parser.add_mutually_exclusive_group()
        dock_source.add_argument("--dock-latest", action='store_true',
                                 help="put latest dock inside (from public git)")
        dock_source.add_argument("--dock-remote-git", action='store',
                                 help="URL to git repo with dock (has to contain setup.py)")
        dock_source.add_argument("--dock-local-path", action='store',
                                 help="path to directory with dock (has to contain setup.py)")
        dock_source.add_argument("--dock-tarball-path", action='store',
                                 help="path to distribution tarball with dock")
        self.bi_parser.add_argument("dockerfile_dir_path", action="store", metavar="DOCKERFILE_DIR_PATH",
                                    help="path to directory with Dockerfile")
        self.bi_parser.add_argument("image", action='store', metavar="IMAGE",
                                    help="name under the image will be accessible")
        self.bi_parser.add_argument("--use-cache", action='store_true', default=False,
                                    help="use cache to build image (may be faster, but not up to date)")

        # inside build
        self.ib_parser = subparsers.add_parser(
            'inside-build',
            usage="%s [OPTIONS] inside-build" % PROG,
            description="We do expect we are inside container, therefore we'll read "
                        "build configuration from json at '%s'" % CONTAINER_BUILD_JSON_PATH +
                        "and when the build is done, "
                        "results are written in that dir so dock from host may read those.")
        self.ib_parser.add_argument("--input", action='store', help="input plugin name")
        self.ib_parser.add_argument("--input-arg", action='append',
                                    help="argument for input plugin (in form of 'key=value'), see input plugins "
                                         " to know what arguments they accept (can be specified multiple times)")
        self.ib_parser.add_argument("--substitute", action='append',
                                    help="substitute values in build json (key=value, or "
                                         "plugin_type.plugin_name.key=value)")
        self.ib_parser.set_defaults(func=cli_inside_build)

    def run(self):
        self.set_arguments()
        args = self.parser.parse_args()
        if args.verbose:
            set_logging(level=logging.DEBUG)
        elif args.quiet:
            set_logging(level=logging.WARNING)
        else:
            set_logging(level=logging.INFO)
        try:
            args.func(args)
        except AttributeError:
            if hasattr(args, 'func'):
                raise
            else:
                self.parser.print_help()
        except KeyboardInterrupt:
            pass
        except Exception as ex:
            if args.verbose:
                raise
            else:
                logger.error("Exception caught: %s", repr(ex))


def run():
    cli = CLI()
    cli.run()


if __name__ == '__main__':
    run()
