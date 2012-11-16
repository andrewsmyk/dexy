from dexy.common import OrderedDict
from dexy.plugins.pygments_filters import PygmentsFilter
from idiopidae.runtime import Composer
from pygments.formatters import get_all_formatters
import idiopidae.parser
import json
import re

class IdioFilter(PygmentsFilter):
    """
    Apply idiopidae to split document into sections at ### @export
    "section-name" comments.
    """
    ALIASES = ['idio', 'idiopidae']
    ADD_NEW_FILES = False
    OUTPUT_EXTENSIONS = PygmentsFilter.MARKUP_OUTPUT_EXTENSIONS + PygmentsFilter.IMAGE_OUTPUT_EXTENSIONS + [".txt"]

    @classmethod
    def data_class_alias(klass, file_ext):
        return 'sectioned'

    def do_add_new_files(self):
        return self.ADD_NEW_FILES or self.args().get('add-new-files', False)

    def process(self):
        input_text = self.input().as_text()
        composer = Composer()
        builder = idiopidae.parser.parse('Document', input_text + "\n\0")

        args = self.args().copy()
        lexer = self.create_lexer_instance(args)
        formatter = self.create_formatter_instance(args)

        output_dict = OrderedDict()
        lineno = 1

        add_new_docs = self.do_add_new_files()

        for i, s in enumerate(builder.sections):
            self.log.debug("In section no. %s name %s" % (i, s))
            lines = builder.statements[i]['lines']
            if len(lines) == 0:
                next
            if not re.match("^\d+$", s):
                # Manually named section, the sectioning comment takes up a
                # line, so account for this to keep line nos in sync.
                lineno += 1

            formatter.linenostart = lineno
            formatted_lines = composer.format(lines, lexer, formatter)

            if add_new_docs:
                doc = self.add_doc("%s--%s%s" % (self.output().baserootname(), s, self.artifact.ext), formatted_lines)

            if not self.artifact.ext in self.IMAGE_OUTPUT_EXTENSIONS:
                if add_new_docs:
                    doc.canon = False
                output_dict[s] = formatted_lines

            lineno += len(lines)

        self.output().set_data(output_dict)

class IdioMultipleFormatsFilter(PygmentsFilter):
    """
    Apply idiopidae to split document into sections at ### @export
    "section-name" comments, then apply syntax highlighting for all available
    text-based formats.
    """
    ALIASES = ['idiom']
    OUTPUT_EXTENSIONS = ['.json']

    def create_formatter_instance(self, args, formatter_class):
        formatter_args = {'lineanchors' : self.output().web_safe_document_key() }

        # Python 2.6 doesn't like unicode keys as kwargs
        for k, v in args.iteritems():
            formatter_args[str(k)] = v

        return formatter_class(**formatter_args)

    def process(self):
        input_text = self.input().as_text()
        composer = Composer()
        builder = idiopidae.parser.parse('Document', input_text + "\n\0")

        args = self.args().copy()
        lexer = self.create_lexer_instance(args)

        formatters = []
        for formatter_class in get_all_formatters():
            formatters.append(self.create_formatter_instance(args, formatter_class))

        output_dict = OrderedDict()
        lineno = 1

        for i, s in enumerate(builder.sections):
            self.log.debug("In section no. %s name %s" % (i, s))
            lines = builder.statements[i]['lines']
            if len(lines) == 0:
                next
            if not re.match("^\d+$", s):
                # Manually named section, the sectioning comment takes up a
                # line, so account for this to keep line nos in sync.
                lineno += 1

            output_dict[s] = {}
            for formatter in formatters:
                formatter.linenostart = lineno
                formatted_lines = composer.format(lines, lexer, formatter)

                for filename in formatter.filenames:
                    ext = filename.lstrip("*")
                    if not ext in self.IMAGE_OUTPUT_EXTENSIONS:
                        output_dict[s][ext] = formatted_lines

            lineno += len(lines)

        self.output().set_data(json.dumps(output_dict))
