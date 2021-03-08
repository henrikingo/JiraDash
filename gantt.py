#!/usr/bin/python3
"""
Create a graph using the "depends on" links and draw a SVG using mermaid-cli syntax.

"""
import dateutil.parser
import dateutil.relativedelta
import datetime
import errno
from jiradash.jira_model import JiraModel
from requests import HTTPError
import os
import re
import subprocess
import sys

def entry_point(my_config):
    print(f"Creating gantt chart of Epics in project(s): {my_config['jira_project']}")
    deps = Gantt(my_config)
    deps.get_and_draw()

class Gantt:
    styles = """    classDef ToDo fill:#fff,stroke:#999,stroke-width:1px,color:#777;
    classDef InProgress fill:#7a7,stroke:#060,stroke-width:3px,color:#000;
    classDef Done fill:#999,stroke:#222,stroke-width:3px,color:#000;
    """
    def __init__(self, my_config):
        self.conf = my_config
        self.model = JiraModel(my_config)

    def get_and_draw(self):
        project = "JiraDash"
        projects = self.conf['jira_project'] if self.conf['jira_project'] else []
        if len(projects) >= 1:
            project = "_".join(projects)

        base = project
        for jira_filter in self.conf['jira_filter'] if self.conf['jira_filter'] else []:
            base += "_" + self.model.safe_chars(jira_filter).replace(" ", "_")
        if self.conf.args.groupby:
            base += "_" + self.conf.args.groupby

        epics = self.model.get_epics()

        markup = self.draw_group(epics, project)
        self.exec_mermaid(markup, f"{base}_gantt")

        csv = self.gantt_csv(epics, project)
        self.write_csv(csv, f"{base}_gantt")

        csv = self.groups_csv(epics, project)
        self.write_csv(csv, f"{base}_components")


    def draw_group(self, graph, project):
        output = """gantt
    dateFormat  YYYY-MM-DD
    title       """ + project + """

"""
        groupby = self.conf.args.groupby
        # Mermaid Gantt chart must have sections. Default section name when no grouping used.
        groups = {"Epics"}
        if groupby:
            groups = self.model.get_groups(groupby=groupby)

        urls = ""
        classes = ""
        start_node = "start"

        for group in groups:
            output += f"    section {group}\n"

            for key in self.model.get_epics_by_depth(group, groupby=groupby):
                obj = graph[key]
                if groupby and obj[groupby] != group:
                    continue

                line = "    %-50s:" % f"{key} {obj['epic_name']}"
                status = ""
                if obj['statusCategory'] == "Done":
                    status = "done, "
                elif obj['statusCategory'] == "In Progress":
                    status = "active, "

                line += "%-10s" % status
                line += key + ", "

                deps = ""
                if obj['deps']:
                    deps += "after"
                    for dep in obj['deps']:
                        deps += " " + dep
                    deps += ", "
                line += deps

                if not deps:
                    if obj['start_date']:
                        line += obj['start_date'].strftime("%Y-%m-%d") + ", "
                        #line += datetime.datetime.isoformat(obj['start_date']) + ", "
                        if obj['resolution_date']:
                            line += obj['resolution_date'].strftime("%Y-%m-%d")
                            #line += datetime.datetime.isoformat(obj['resolution_date'])
                        else:
                            line += str(int(obj['points']*30)) + "d"
                    else:
                        line += str(int(obj['points']*30)) + "d"
                else:
                    line += str(int(obj['points']*30)) + "d"

                output += line + "\n"

                urls += f"    click {key} href \"{obj['url']}\"\n"

            output += "\n"

        output += urls
        #print(output)
        return output

    def _get_css_class(self, obj):
        css_class = obj['statusCategory'].replace(" ", "")
        return css_class

    def exec_mermaid(self, markup, markup_file_base):
        out_dir = self.conf['out_dir']
        mkdir_p(out_dir)

        markup_file = os.path.join(out_dir, f"{markup_file_base}.mermaid")
        print(f"Writing {markup_file}")
        with open(markup_file, "w") as f:
            f.write(markup)

        cmd = ["mmdc", "--input", markup_file, "--output", os.path.join(out_dir, f"{markup_file_base}.svg")]
        print(cmd)
        subprocess.run(cmd)

    def gantt_csv(self, graph, project):
        groupby = self.conf.args.groupby
        groups = {"Epics"}
        if groupby:
            groups = self.model.get_groups(groupby=groupby)

        head = f"{project}\n{groupby}\tEpic\tFix version\tEstimate\tResources allocated\tSprints->\n"
        sprints ="\t\t\t\t\n"  # Add sprints when we know how many there are

        body = ""
        for group in groups:
            body += f"\n{group}\n"
            for key in self.model.get_epics_by_depth(group, groupby=groupby):
                obj = graph[key]
                line = f"\t{key} {obj['epic_name']}\t{str(obj['fixVersions'])}\t{obj['points']}\n"
                body += line

        return head + sprints + body

    def write_csv(self, csv, csv_file_base):
        out_dir = self.conf['out_dir']
        mkdir_p(out_dir)

        csv_file = os.path.join(out_dir, f"{csv_file_base}.csv")
        print(f"Writing {csv_file}")
        with open(csv_file, "w") as f:
            f.write(csv)

    def groups_csv(self, graph, project):
        groupby = self.conf.args.groupby
        groups = {"Epics"}
        if groupby:
            groups = self.model.get_groups(groupby=groupby)

        head = f"{project}\n{groupby}\tEstimate\tResources allocated\tSprints->\n"
        sprints ="\t\t\t\t\n"  # Add sprints when we know how many there are

        body = "Totals:\n"
        for group in groups:
            points = 0.0
            for key in self.model.get_epics_by_depth(group, groupby=groupby):
                points += graph[key]['points']
            body += f"{group}\t{points}\n"

        return head + sprints + body


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
