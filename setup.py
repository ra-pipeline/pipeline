import collections
import distutils.cmd
import distutils.log
import os
import re
import shutil
import subprocess
import sys
import setuptools
from setuptools.command.build_py import build_py

ENCODING = 'utf-8'  # locale.getpreferredencoding()
PIPELINE_PACKAGES = ['h', 'hif', 'hifa', 'hifas', 'hifv', 'hsd', 'hsdn']


def flatten(items):
    """Yield items from any nested iterable"""
    for x in items:
        if isinstance(x, collections.Iterable) and not isinstance(x, (str, bytes)):
            for sub_x in flatten(x):
                yield sub_x
        else:
            yield x


class MinifyJSCommand(distutils.cmd.Command):
    description = 'Minify the pipeline javascript'
    user_options = [('inplace', 'i', 'Generate minified JS in src directory')]
    boolean_options = ['inplace']

    def __init__(self, dist):
        distutils.cmd.Command.__init__(self, dist)

    def initialize_options(self):
        """Set default values for options."""
        self.inplace = None

    def finalize_options(self):
        # get the path to this file
        root_dir = os.path.dirname(os.path.realpath(__file__))
        build_py_cmd = self.get_finalized_command('build_py')

        if self.inplace:
            build_path = root_dir
        else:
            # get the path to the build directory
            build_path = os.path.join(root_dir, build_py_cmd.build_lib)

        js_path = build_py_cmd.get_package_dir('pipeline.infrastructure.renderer.templates.resources.js')
        self.js_input_dir = os.path.join(root_dir, js_path)
        self.js_output_dir = os.path.join(build_path, js_path)
        self.root_dir = root_dir

    def run(self):
        to_minify = {
            'pipeline_common.min.js': [
                'jquery-3.3.1.js',                          # dependency of pipeline.js and its plugins,
                'holder.js',                                # placeholders for missing images
                'lazyload.js',                              # only load images when they become visible
                'jquery.fancybox.js',                       # fancybox
                'plotcmd.js',                               # fancybox plugin to show originating plot command
                'tcleancmd.js',                             # fancybox plugin to show originating tclean command
                'purl.js',                                  # URL inspection
                'bootstrap.js',                             # bootstrap
                'pipeline.js',                              # pipeline
            ],
            'pipeline_plots.min.js': [
                'select2.js',                               # filters on detail plots pages
                'd3.v3.js',                                 # histograms
            ]
        }

        if not os.path.exists(self.js_output_dir):
            os.mkdir(self.js_output_dir)
            shutil.copymode(self.js_input_dir, self.js_output_dir)

        for output_file, input_files in to_minify.items():
            output_path = os.path.join(self.js_output_dir, output_file)
            input_paths = [os.path.join(self.js_input_dir, f) for f in input_files]
            self.minify(input_paths, output_path)

    def minify(self, inputs, output):
        self.announce('Creating minified JS: {}'.format(os.path.basename(output)),
                      level=distutils.log.INFO)

        command = ['java',
                   '-jar', 'closure-compiler.jar',
                   '--js_output_file', output,
                   '--language_in', 'ECMASCRIPT6',
                   '--language_out', 'ECMASCRIPT6',
                   '--generate_exports', 'false',
                   '--warning_level', 'verbose',
                   '--compilation_level', 'BUNDLE']

        input_files = [['--js', i] for i in inputs]

        input_args = flatten([command, input_files])

        subprocess.check_output([str(i) for i in input_args], cwd=self.root_dir)


class MinifyCSSCommand(distutils.cmd.Command):
    description = 'Minify the pipeline CSS'
    user_options = [('inplace', 'i', 'Generate minified CSS in src directory')]
    boolean_options = ['inplace']

    def __init__(self, dist):
        distutils.cmd.Command.__init__(self, dist)

    def initialize_options(self):
        """Set default values for options."""
        self.inplace = None

    def finalize_options(self):
        # get the path to this file
        root_dir = os.path.dirname(os.path.realpath(__file__))
        build_py_cmd = self.get_finalized_command('build_py')

        if self.inplace:
            build_path = root_dir
        else:
            # get the path to the build directory
            build_path = os.path.join(root_dir, build_py_cmd.build_lib)

        # get the path to the source CSS directory
        css_path = build_py_cmd.get_package_dir('pipeline.infrastructure.renderer.templates.resources.css')
        self.css_input_dir = os.path.join(root_dir, css_path)
        self.css_output_dir = os.path.join(build_path, css_path)

    def run(self):
        to_minify = {
            'all.min.css': [
                'font-awesome.css',
                'jquery.fancybox.css',
                'select2.css',
                'select2-bootstrap.css',
                'pipeline.css',
            ]
        }

        if not os.path.exists(self.css_output_dir):
            os.mkdir(self.css_output_dir)
            shutil.copymode(self.css_input_dir, self.css_output_dir)

        for output_file, input_files in to_minify.items():
            output_path = os.path.join(self.css_output_dir, output_file)
            input_paths = [os.path.join(self.css_input_dir, f) for f in input_files]
            self.minify(input_paths, output_path)

    def minify(self, inputs, output_path):
        self.announce('Creating minified CSS: {}'.format(os.path.basename(output_path)),
                      level=distutils.log.INFO)

        buffer = []
        for name in inputs:
            with open(name, 'r', encoding=ENCODING) as f:
                buffer.append(f.read())
        buffer = '\n\n'.join(buffer)

        import csscompressor
        output = csscompressor.compress(buffer)

        with open(output_path, 'w', encoding=ENCODING) as f:
            f.write(output)
            f.write('\n')


class VersionCommand(distutils.cmd.Command):
    description = 'Generate the version file'
    user_options = [('inplace', 'i', 'Generate the version file in src directory')]
    boolean_options = ['inplace']

    def __init__(self, dist):
        distutils.cmd.Command.__init__(self, dist)

    def initialize_options(self):
        """Set default values for options."""
        self.inplace = None

    def finalize_options(self):
        # get the path to this file
        dir_path = os.path.dirname(os.path.realpath(__file__))

        if self.inplace:
            self.build_path = dir_path
        else:
            # get the path to the build directory
            build_py_cmd = self.get_finalized_command('build_py')
            self.build_path = os.path.join(dir_path, build_py_cmd.build_lib)

    def run(self):
        version = _get_git_version()
        version_py = os.path.join(self.build_path, 'pipeline', '_version.py')
        self.announce('Creating version file: {}'.format(version_py), level=distutils.log.INFO)
        with open(version_py, 'w', encoding=ENCODING) as f:
            f.write("# File generated by setup.py\n# do not change, do not track in version control\n")
            f.write("version = '{}'\n".format(version))
            f.write('\n')


def _get_git_version() -> str:
    # Retrieve info about current branch.
    git_branch = None
    try:
        git_branch = subprocess.check_output(['git', 'symbolic-ref', '--short', 'HEAD'],
                                             stderr=subprocess.DEVNULL).decode().strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        # FileNotFoundError: if git is not on PATH.
        # subprocess.CalledProcessError: if git command returns error; for example, current checkout
        #   may have a detached HEAD pointing at a specific tag (not pointing to a branch).
        pass

    # Try to get version information
    ver_from_script = []
    try:
        # Output of the version.py script is a string with two or three space-separated elements:
        # last branch tag (possibly empty), last release tag, and possibly a "dirty" suffix.
        # For example:
        # 2024.0.0.3 2024.0.0.3
        # or
        # '' 2024.0.0.3 dirty
        ver_from_script = subprocess.check_output([sys.executable, 'pipeline/infrastructure/version.py'],
                                             stderr=subprocess.DEVNULL).decode().rstrip().split(' ')
    except (FileNotFoundError, subprocess.CalledProcessError):
        # FileNotFoundError: if git is not on PATH.
        # subprocess.CalledProcessError: if git command returns error; for example, current checkout
        #   may have a detached HEAD pointing at a specific tag (not pointing to a branch).
        pass

    if git_branch is not None and (git_branch == 'main' or git_branch.startswith('release/')):
        # Version string returned by this routine contains the latest release tag and optionally
        # a local version identifier ("dirty") as described in PEP440, separated by "+".
        return '+'.join(ver_from_script[1:])
    else:
        # Retrieve info about current commit.
        try:
            # Set version to latest tag, number of commits since tag, and latest commit hash.
            commit_hash = subprocess.check_output(['git', 'describe', '--always', '--tags', '--long', '--dirty'],
                                                  stderr=subprocess.DEVNULL).decode().strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            # FileNotFoundError: if git is not on PATH.
            # subprocess.CalledProcessError: if git command returns error.
            commit_hash = None

        # Populate the hash, branch, and version from the script if any are unset:
        if commit_hash is None:
            commit_hash = "unknown_hash"
        else:
            # Only ASCII numbers, letters, '.', '-', and '_' are allowed in the local version label
            commit_hash = re.sub(r'[^\w_\-\.]+', '.', commit_hash)

        if git_branch is None:
            git_branch = "unknown_branch"
        else:
            # Only ASCII numbers, letters, '.', '-', and '_' are allowed in the local version label
            git_branch = re.sub(r'[^\w_\-\.]+', '.', git_branch)

        if len(ver_from_script) < 2:
            # Invalid version number:
            version_number = '0.0.dev0'
        else:
            version_number = ver_from_script[1]

        # Consolidate into single version string.
        version = "{}+{}-{}".format(version_number, commit_hash, git_branch)

        return version


class PipelineBuildPyCommand(build_py):
    def run(self):
        build_py.run(self)
        self.run_command('minify_css')
        self.run_command('minify_js')
        self.run_command('version')


# The pipeline.XXX.cli packages are not recognised by find_packages as they do
# not contain an __init__.py file. The __init__.py files are autogenerated as
# part of the buildmytasks command, and as we don't want autogenerated files
# to be committed, the cli/__init__.py files are added to .gitignore and are
# not part of a pristine checkout. This leaves us with a problem: we either
# need __init__.py to be created ahead of the find_packages() call, we add the
# unrecognised packages to the package list manually, or we use a package
# finder class with more relaxed heuristics about identifying packages. Here
# we do the latter; this might need updating to
# setuptool.find_namespace_packages when CASA's setuptools is updated.
packages = setuptools.PEP420PackageFinder().find(exclude=['build*', 'doc*'])


setuptools.setup(
    name='Pipeline',
    version=_get_git_version(),
    description='CASA pipeline',
    cmdclass={
        'build_py': PipelineBuildPyCommand,
        'minify_js': MinifyJSCommand,
        'minify_css': MinifyCSSCommand,
        'version': VersionCommand,
    },
    # install_requires=[
    #     'cachetools',       # memo decorator to cache expensive calls
    #     'intervaltree',     # callibrary
    #     'Mako',             # web log
    #     'pyparsing',        # parse user input using CASA syntax
    # ],
    setup_requires=[
        'csscompressor'  # minify CSS
    ],
    packages=packages,
    package_data={'': ['*.css',
                       '*.egg',
                       '*.eot',
                       '*.gif',
                       '*.html',
                       '*.jpg',
                       '*.js',
                       '*.mak',
                       '*.mako',
                       '*.otf',
                       '*.png',
                       '*.svg',
                       '*.ttf',
                       '*.txt',
                       '*.woff',
                       '*.woff2',
                       '*.xml',
                       'version']},
    zip_safe=False
)