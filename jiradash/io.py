#!/usr/bin/python3
"""
Read and write files. Mostly write I guess.

"""
import errno
# TODO: Really just using safe_chars(). It could be a utility module?
from jiradash.jira_model import JiraModel
import os

class Writer:
    def __init__(self, my_config):
        self.conf = my_config
        self.model = JiraModel(my_config)

        self.project = "JiraDash"  # default title for a lot of output
        self.command = self.conf['command'][0]
        self.base = self._set_base()

    def _set_base(self):
        projects = self.conf['jira_project'] if self.conf['jira_project'] else []
        if len(projects) >= 1:
            self.project = "_".join(projects)
        self.base = self.project
        for jira_filter in self.conf['jira_filter'] if self.conf['jira_filter'] else []:
            self.base += "_" + self.model.safe_chars(jira_filter).replace(" ", "_")
        if self.conf.args.groupby:
            self.base += "_" + self.conf.args.groupby
        self.base = f"{self.base}_{self.command}"
        return self.base

    def csv(self, csv, base=None):
        self.write_file(csv, extension="csv", base=base)

    def html(self, html, base=None):
        self.write_file(html, extension="html", base=base)

    def write_file(self, content, extension="", base=None):
        if base is None:
            base = self.base

        out_dir = self.conf['out_dir']
        mkdir_p(out_dir)

        file_name = os.path.join(out_dir, f"{base}.{extension}")
        print(f"Writing {file_name}")
        with open(file_name, "w") as f:
            f.write(content)


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
