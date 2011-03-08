try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict
from dexy.handler import DexyHandler

from jinja2 import Environment
import jinja2
import json
import os
import re
import uuid

class FilenameHandler(DexyHandler):
    """Generate random filenames to track provenance of data."""
    ALIASES = ['fn']
    def process_text(self, input_text):
        self.artifact.load_input_artifacts()
        for k, a in self.artifact.input_artifacts_dict.items():
            for ak, av in a['additional_inputs'].items():
                self.artifact.additional_inputs[ak] = av

        for m in re.finditer("dexy--(.+)\.([a-z]+)", input_text):
            key = m.groups()[0]
            ext = m.groups()[1]
            if key in self.artifact.additional_inputs.keys():
                filename = self.artifact.additional_inputs[key]
                self.log.debug("existing key %s in artifact %s links to file %s" %
                          (key, self.artifact.key, filename))
            else:
                filename = "%s.%s" % (uuid.uuid4(), ext)
                self.artifact.additional_inputs[key] = filename
                self.log.debug("added key %s to artifact %s ; links to file %s" %
                          (key, self.artifact.key, filename))

            input_text = input_text.replace(m.group(), filename)
        return input_text


class JinjaHelper:
    def read_file(self, filename):
        f = open(filename, "r")
        return f.read()

class JinjaHandler(DexyHandler):
    """
    Runs the Jinja templating engine on your document. The primary way to
    incorporate dynamic content into your documents.
    """

    INPUT_EXTENSIONS = [".*"]
    OUTPUT_EXTENSIONS = [".*"]
    ALIASES = ['jinja']

    def process_text(self, input_text):
        document_data = {}
        document_data['filenames'] = {}
        document_data['sections'] = {}
        document_data['a'] = {}

        # TODO move to separate 'index' handler for websites
        # create a list of subdirectories of this directory
        doc_dir = os.path.dirname(self.artifact.doc.name)
        children = [f for f in os.listdir(doc_dir) \
                    if os.path.isdir(os.path.join(doc_dir, f))]
        document_data['children'] = sorted(children)
        document_data['json'] = OrderedDict()

        self.artifact.load_input_artifacts()
        for k, a in self.artifact.input_artifacts_dict.items():
            common_prefix = os.path.commonprefix([self.artifact.doc.name, k])
            common_path = os.path.dirname(common_prefix)
            relpath = os.path.relpath(k, common_path)

            if document_data['filenames'].has_key(relpath):
                raise Exception("Duplicate key %s" % relpath)

            document_data['filenames'][relpath] = a['fn']
            document_data['sections'][relpath] = a['data_dict']
            document_data[relpath] = a['data']

            if a['fn'].endswith('.json'):
                self.log.debug("loading JSON for %s" % (relpath))
                path_to_file = os.path.join('artifacts', a['fn'])
                unsorted_json = json.load(open(path_to_file), "r")

                def sort_dict(d):
                    od = OrderedDict()
                    for k in sorted(d.keys()):
                        v = d[k]
                        if isinstance(v, dict):
                            od[k] = sort_dict(v)
                        else:
                            od[k] = v
                    return od

                document_data['json'][relpath] = sort_dict(unsorted_json)

            for ak, av in a['additional_inputs'].items():
                document_data['a'][ak] = av
                fullpath_av = os.path.join('artifacts', av)
                if av.endswith('.json') and os.path.exists(fullpath_av):
                    self.log.debug("loading JSON for %s" % fullpath_av)
                    document_data[ak] = json.load(open(fullpath_av, "r"))

        if self.artifact.ext == ".tex":
            self.log.debug("changing jinja tags to << >> etc. for %s" % self.artifact.key)
            env = Environment(
                block_start_string = '<%',
                block_end_string = '%>',
                variable_start_string = '<<',
                variable_end_string = '>>',
                comment_start_string = '<#',
                comment_end_string = '#>'
                )
        else:
            env = Environment()


        # TODO test that we are in textile or other format where this makes sense
        if re.search("latex", self.artifact.doc.key()):
            is_latex = True
        else:
            is_latex = False

        # Wrap HTML content in <notextile> tags if requested
        if self.artifact.doc.args.has_key('notextile'):
            for k, v in document_data.items():
                if k.find("|") > 0:
                    if document_data['filenames'][k].endswith(".html"):
                        document_data[k] = "\n<notextile>\n%s\n</notextile>\n" % v.rstrip()

            for file_key, data_hash in document_data['sections'].items():
                if document_data['filenames'][file_key].endswith(".html"):
                    for k, v in data_hash.items():
                        document_data['sections'][file_key][k] = "\n<notextile>\n%s\n</notextile>\n" % v.rstrip()

        document_data['filename'] = document_data['filenames']
        template_hash = {
            'd' : document_data,
            'filenames' : document_data['filenames'],
            'dk' : sorted(document_data.keys()),
            'a' : self.artifact,
            'h' : JinjaHelper(),
            'is_latex' : is_latex
        }

        try:
            template = env.from_string(input_text)
            result = str(template.render(template_hash))
        except jinja2.exceptions.TemplateSyntaxError as e:
            print "jinja error occurred processing line", e.lineno
            raise e
        except Exception as e:
            print e.__class__.__name__
            raise e

        return result
