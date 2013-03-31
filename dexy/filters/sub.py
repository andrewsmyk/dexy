from dexy.common import OrderedDict
from dexy.filters.process import SubprocessInputFilter
from dexy.filters.process import SubprocessExtToFormatFilter
from dexy.filters.process import SubprocessFilter
from dexy.filters.process import SubprocessFormatFlagFilter
from dexy.filters.process import SubprocessStdoutFilter
import dexy.exceptions
import json
import os
import shutil

class Pdf2ImgSubprocessFilter(SubprocessExtToFormatFilter):
    """
    Converts a PDF file to an image using ghostscript.

    Returns the image generated by page 1 of the PDF by default, the
    'page' parameter can be used to specify other pages. 
    """
    aliases = ['pdf2img', 'pdftoimg', 'pdf2png']
    _settings = {
            'res' : ("Resolution of image.", 300),
            'page' : ("Which page of the PDF to return as an image", 1),
            'executable' : 'gs',
            'version-command' : 'gs --version',
            'input-extensions' : ['.pdf'],
            'output-extensions' : ['.png'],
            'ext-to-format' : {
                '.png' : 'png16m',
                '.jpg' : 'jpeg'
                },
            'format-specifier' : '-sDEVICE=',
            'command-string' : '%(prog)s -dSAFER -dNOPAUSE -dBATCH %(format)s -r%(res)s -sOutputFile="%%d-%(output_file)s" "%(script_file)s"'
            }

    def process(self):
        self.populate_workspace()

        command = self.command_string()
        proc, stdout = self.run_command(command, self.setup_env())
        self.handle_subprocess_proc_return(command, proc.returncode, stdout)

        page = self.setting('page')
        page_file = "%s-%s" % (page, self.output_data.basename())

        wd = self.parent_work_dir()
        page_path = os.path.join(wd, page_file)
        shutil.copyfile(page_path, self.output_filepath())

class RIntBatchSectionsFilter(SubprocessFilter):
    """
    Experimental filter to run R in sections without using pexpect.
    """
    aliases = ['rintmock']

    _settings = {
            'add-new-files' : True,
            'executable' : 'R CMD BATCH --quiet --no-timing',
            'input-extensions' : ['.txt', '.r', '.R'],
            'output-extensions' : [".Rout", '.txt'],
            'version-command' : "R --version",
            'write-stderr-to-stdout' : False,
            'output-data-type' : 'sectioned',
            'command-string' : """%(prog)s %(args)s "%(script_file)s" %(scriptargs)s "%(output_file)s" """
            }

    def command_string(self, section_name, section_text, wd):
        br = self.input_data.baserootname()

        args = self.default_command_string_args()
        args['script_file'] = "%s-%s%s" % (br, section_name, self.input_data.ext)
        args['output_file'] = "%s-%s-out%s" % (br, section_name, self.output_data.ext)

        work_filepath = os.path.join(wd, args['script_file'])

        with open(work_filepath, "wb") as f:
            f.write(section_text)

        command = self.setting('command-string') %  args
        return command, args['output_file']

    def process(self):
        self.populate_workspace()
        wd = self.parent_work_dir()

        result = OrderedDict()

        for section_name, section_text in self.input_data.as_sectioned().iteritems():
            command, outfile = self.command_string(section_name, section_text, wd)
            proc, stdout = self.run_command(command, self.setup_env())
            self.handle_subprocess_proc_return(command, proc.returncode, stdout)

            with open(os.path.join(wd, outfile), "rb") as f:
                result[section_name] = f.read()

        if self.setting('walk-working-dir'):
            self.walk_working_directory()

        if self.setting('add-new-files'):
            self.add_new_files()

        self.output_data.set_data(result)

class EmbedFonts(SubprocessFilter):
    """
    Use to embed fonts and do other prepress as required for some types of printing.
    """
    aliases = ['embedfonts', 'prepress']
    _settings = {
            'input-extensions' : [".pdf"],
            'output-extensions' : [".pdf"],
            'executable' : 'ps2pdf'
            }

    def preprocess_command_string(self):
        pf = self.work_input_filename()
        af = self.work_output_filename()
        return "%s -dPDFSETTINGS=/prepress %s %s" % (self.setting('executable'), pf, af)

    def pdffonts_command_string(self):
        return "%s %s" % ("pdffonts", self.result().name)

    def process(self):
        env = self.setup_env()

        command = self.preprocess_command_string()
        proc, stdout = self.run_command(command, env)
        self.handle_subprocess_proc_return(command, proc.returncode, stdout)

        command = self.pdffonts_command_string()
        proc, stdout = self.run_command(command, env)
        self.handle_subprocess_proc_return(command, proc.returncode, stdout)

        self.copy_canonical_file()

class AbcFilter(SubprocessFormatFlagFilter):
    """
    Runs abc to convert abc music notation to one of the available output formats.
    """
    aliases = ['abc']
    _settings = {
            'command-string' : '%(prog)s %(args)s %(format)s -O %(output_file)s %(script_file)s',
            'add-new-files' : False,
            'output' : True,
            'examples' : ['abc'],
            'executable' : 'abcm2ps',
            'input-extensions' : ['.abc'],
            'output-extensions': ['.svg', '.html', '.xhtml', '.eps'],
            'ext-to-format': {
                '.eps' : '-E',
                '.svg' : '-g',
                '.svg1' : '-v', # dummy entry so we know -v is a format flag
                '.html' : '-X',
                '.xhtml' : '-X'
                }
            }

    def process(self):
        command = self.command_string()
        proc, stdout = self.run_command(command, self.setup_env())
        self.handle_subprocess_proc_return(command, proc.returncode, stdout)

        if self.ext in ('.svg', '.eps'):
            # Fix for abcm2ps adding 001 to file name.
            nameparts = os.path.splitext(self.output_data.name)
            output_filename = "%s001%s" % (nameparts[0], nameparts[1])
            output_filepath = os.path.join(self.workspace(), output_filename)
            self.output_data.copy_from_file(output_filepath)
        else:
            self.copy_canonical_file()

        if self.setting('add-new-files'):
            self.add_new_files()

class AbcMultipleFormatsFilter(SubprocessFilter):
    """
    Runs abc to convert abc music notation to all of the available output formats.
    """
    aliases = ['abcm']
    _settings = {
            'input-extensions' : ['.abc'],
            'output-extensions' : ['.json'],
            'executable' : 'abcm2ps',
            'add-new-files' : False
            }

    def command_string(self, ext):
        clargs = self.command_line_args() or ''

        if any(x in clargs for x in ['-E', '-g', '-v', '-X']):
            raise dexy.exceptions.UserFeedback("Please do not pass any output format flags!")

        if ext in ('.eps'):
            output_flag = '-E'
        elif ext in ('.svg'):
            output_flag = '-g'
        elif ext in ('.html', '.xhtml'):
            output_flag = '-X'
        else:
            raise dexy.exceptions.InternalDexyProblem("bad ext '%s'" % ext)

        args = {
            'prog' : self.setting('executable'),
            'args' : clargs,
            'output_flag' : output_flag,
            'script_file' : self.work_input_filename(),
            'output_file' : self.output_workfile(ext)
        }
        return "%(prog)s %(args)s %(output_flag)s -O %(output_file)s %(script_file)s" % args

    def output_workfile(self, ext):
        return "%s%s" % (self.output_data.baserootname(), ext)

    def process(self):
        output = {}

        wd = self.parent_work_dir()

        for ext in ('.eps', '.svg', '.html', '.xhtml'):
            command = self.command_string(ext)
            proc, stdout = self.run_command(command, self.setup_env())
            self.handle_subprocess_proc_return(command, proc.returncode, stdout)

            if ext in ('.svg', '.eps'):
                # Fix for abcm2ps adding 001 to file name.
                nameparts = os.path.splitext(self.output_workfile(ext))
                output_filename = "%s001%s" % (nameparts[0], nameparts[1])
                output_filepath = os.path.join(wd, output_filename)
            else:
                output_filename = self.output_workfile(ext)
                output_filepath = os.path.join(wd, output_filename)

            with open(output_filepath, "r") as f:
                output[ext] = f.read()

        self.output_data.set_data(json.dumps(output))

class ManPage(SubprocessStdoutFilter):
    """
    Read command names from a file and fetch man pages for each.

    Returns a JSON dict whose keys are the program names and values are man
    pages.
    """
    aliases = ['man']

    _settings = {
            'executable' : 'man',
            'version-command' : 'man --version',
            'input-extensions' : [".txt"],
            'output-extensions' : [".json"]
    }

    def command_string(self, prog_name):
        # Use bash rather than the default of sh (dash) so we can set pipefail.
        return "bash -c \"set -e; set -o pipefail; man %s | col -b | strings\"" % (prog_name)

    def process(self):
        man_info = {}
        for prog_name in str(self.input_data).split():
            command = self.command_string(prog_name)
            proc, stdout = self.run_command(command, self.setup_env())
            self.handle_subprocess_proc_return(command, proc.returncode, stdout)
            man_info[prog_name] = stdout

        self.output_data.set_data(json.dumps(man_info))

class ApplySed(SubprocessInputFilter):
    """
    A filter which runs on a text file and applies a sed file (specified as an
    input) to that text file. Output is the modified text file.
    """
    aliases = ['used']
    _settings = {
            'executable' : 'sed',
            'output-data-type' : 'generic',
            }

    def process(self):
        for doc in self.doc.walk_input_docs():
            if doc.output_data().ext == ".sed":
                command = "%s -f %s" % (self.setting('executable'), doc.name)

        if not command:
            raise dexy.exceptions.UserFeedback("A .sed file must be passed as an input to %s" % self.key)

        proc, stdout = self.run_command(command, self.setup_env(), unicode(self.input_data))
        self.handle_subprocess_proc_return(command, proc.returncode, stdout)
        self.output_data.set_data(stdout)

class Sed(SubprocessInputFilter):
    """
    A filter which runs on a sed file and applies this sed file to text files
    passed as inputs. Output is a dict of filenames and output text from each
    input file. If there is only a single input file, output is a dict of
    section names and output text from each section in that input file.
    """
    aliases = ['sed']
    _settings = {
            'executable' : 'sed',
            'input-extensions' : ['.sed'],
            'output-extensions' : ['.sed', '.txt'],
            }

    def command_string(self):
        return "%s -f %s" % (self.setting('executable'), self.work_input_filename())
