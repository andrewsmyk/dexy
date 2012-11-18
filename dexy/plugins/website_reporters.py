from dexy.plugins.output_reporters import OutputReporter
from dexy.plugins.templating_plugins import PythonBuiltins
from jinja2 import Environment
from jinja2 import FileSystemLoader
import dexy.exceptions
import jinja2
import os

class WebsiteReporter(OutputReporter):
    """
    Applies a template to create a website from your dexy output.

    Templates are applied to all files with .html extension which don't already
    contain "<head" or "<body" tags.

    Templates must be named _template.html with no dexy filters applied (TODO relax this)
    """
    ALIASES = ['ws']
    REPORTS_DIR = 'output-site'
    ALLREPORTS = False

    def is_index_page(self, doc):
        fn = doc.output().name
        # TODO index.json only if htmlsections in doc key..
        return fn.endswith("index.html") or fn.endswith("index.json")

    def nav_directories(self):
        """
        Returns a dict whose keys are top-level directores containing an
        'index.html' page and whose values are a list with the 'doc' object
        for the 'index.html' page and a dict of subdirectories in same format.

        Will warn if a parent dir doesn't have index page, parent dir will be
        included in dict.

        """
        directories = [None, {}]

        def assign_nest(keys, value):
            temp = directories
            for k in keys:
                if not temp[1]:
                    temp[1] = {}
                if not temp[1].has_key(k):
                    temp[1][k] = [None, {}]
                temp = temp[1][k]
            temp[0] = doc

        for doc in self.wrapper.registered_docs():
            doc_dir = doc.output().parent_dir()
            if self.is_index_page(doc):
                path_elements = os.path.split(doc_dir)

                while path_elements and path_elements[0] in ('', '.'):
                    path_elements = path_elements[1:]

                if not path_elements:
                    directories[0] = doc
                    continue

                assign_nest(path_elements, doc)

        return directories

    def apply_and_render_template(self, doc):
        if doc.args.get('ws_template'):
            template_file = doc.args.get('ws_template')
        else:
            template_file = "_template.html"
        template_path = None

        path_elements = doc.output().parent_dir().split(os.sep)
        for i in range(len(path_elements), -1, -1):
            template_path = os.path.join(*(path_elements[0:i] + [template_file]))
            if os.path.exists(template_path):
                self.log.debug("using template %s for %s" % (template_path, doc.key))
                break

        if not template_path:
            raise dexy.exceptions.UserFeedback("no template path for %s" % doc.key)

        env = Environment(undefined=jinja2.StrictUndefined)
        env.loader = FileSystemLoader([".", os.path.dirname(template_path)])
        self.log.debug("loading template at %s" % template_path)
        template = env.get_template(template_path)

        if self.is_index_page(doc):
            nav_current_index = doc.output().parent_dir()
        else:
            nav_current_index = None

        if doc.final_artifact.ext == '.html':
            content = doc.output().as_text()
        else:
            content = doc.output()

        navigation = {
                'current_index' : nav_current_index,
                'directories' : self.nav_directories()
                }

        env_data = {
                'content' : content,
                'locals' : locals,
                'navigation' : navigation,
                'page_title' : doc.title(),
                'source' : doc.name,
                'template_source' : template_path,
                'wrapper' : self.wrapper
                }

        for builtin in PythonBuiltins.PYTHON_BUILTINS:
            env_data[builtin.__name__] = builtin

        fp = os.path.join(self.REPORTS_DIR, doc.output().name).replace(".json", ".html")

        parent_dir = os.path.dirname(fp)
        if not os.path.exists(parent_dir):
            os.makedirs(os.path.dirname(fp))

        template.stream(env_data).dump(fp, encoding="utf-8")

    def run(self, wrapper):
        self.wrapper=wrapper
        self.set_log()
        self.keys_to_outfiles = []

        self.create_reports_dir()

        for doc in wrapper.registered_docs():
            self.log.debug("Processing doc %s" % doc.key)
            if doc.canon:
                if doc.final_artifact.ext == ".html":
                    has_html_header = any(html_fragment in doc.output().as_text() for html_fragment in ('<html', '<body', '<head'))

                    if has_html_header or not doc.args.get('ws_template', True):
                        self.log.debug("found html tag in output of %s" % doc.key)
                        self.write_canonical_doc(doc)
                    else:
                        self.apply_and_render_template(doc)
                elif doc.final_artifact.ext == '.json' and 'htmlsections' in doc.filters:
                    self.apply_and_render_template(doc)
                else:
                    self.write_canonical_doc(doc)