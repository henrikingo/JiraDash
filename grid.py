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
    print(f"Printing a grid grouping of Epics in project(s): {my_config['jira_project']}")
    deps = Grid(my_config)
    deps.get_and_draw()

class Grid:
    def __init__(self, my_config):
        self.conf = my_config
        self.model = JiraModel(my_config)
        self.releases = self.model.get_versions()

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
        by_epic = self.model.get_issues_per_epic()

        grid = self.grid_obj(epics, project)
        csv = self.grid_csv(grid, project)
        self.write_csv(csv, f"{base}_grid")
        html = self.grid_html(grid, by_epic, project)
        self.write_html(html, f"{base}_grid")



    def grid_obj(self, epics, project):
        groups = self.model.get_groups(groupby='components')

        grid = {}
        for group in groups:
            grid[group] = {}
            for rel in self.releases:
                #print(rel)
                grid[group][rel] = {}

        for key, obj in epics.items():
            grid[obj['components']][obj['fixVersions']][key] = obj

        return grid

    def grid_csv(self, grid, project):
        csv = project + "\t" + "\t".join(self.releases) + "\n"

        cells = {}
        for component in grid.keys():
            cells[component] = {}
            for rel in self.releases:
                cells[component][rel] = []
                if rel in grid[component]:
                    for key in sorted(grid[component][rel].keys()):
                        obj = grid[component][rel][key]
                        cells[component][rel].append(obj)


        for component in grid.keys():
            csv += component + "\n"
            done_columns = [False] * len(self.releases)
            while not all(done_columns):
                col = 0
                for rel in self.releases:
                    cell = cells[component][rel]
                    obj = cell.pop() if cell else None
                    if obj:
                        csv += "\t" + obj['key'] + " " + obj['epic_name']
                    else:
                        done_columns[col] = True
                        csv += "\t"
                    col += 1
                csv += "\n"

        return csv

    def write_csv(self, csv, csv_file_base):
        out_dir = self.conf['out_dir']
        mkdir_p(out_dir)

        csv_file = os.path.join(out_dir, f"{csv_file_base}.csv")
        print(f"Writing {csv_file}")
        with open(csv_file, "w") as f:
            f.write(csv)

    def grid_html(self, grid, by_epic, project):
        colwidth = str(int(100/(len(self.releases)+1)))
        head = f"<html>\n<head><title>{project}</title>\n"
        style = """<style type="text/css">
    table td {padding: 5px; font-family: sans-serif; border-top: 1px solid #ddd;}
    td div {overflow: hidden; height: 2em;}
    td div a {overflow: hidden; height: 1.4em; display: inline-block;}
    a.ToDo {text-decoration: none; color: #666;}
    a.InProgress {text-decoration: none; color: #090;}
    a.Done {text-decoration: line-through; color: #333;}

    td div span {width: 5px; height: 5px; margin-left: 1px; margin-right: 1px; display: inline-block;}
    td div span.ToDo {border: solid 1px #666;}
    td div span.InProgress {border: solid 1px #090; background-color: #090;}
    td div span.Done {border: solid 1px #333; background-color: #333;}
</style>
"""

        table = f"<table>\n<tr><th>{project}</th><th>" + "</th><th>".join(self.releases) + "</th></tr>\n"

        for component in grid.keys():
            table += f"<tr><th>{component}</th>"
            for rel in self.releases:
                table += "<td>"
                for key in sorted(grid[component][rel].keys()):
                    obj = grid[component][rel][key]

                    table += "<div>\n"
                    table += f"<a href=\"{obj['url']}\" title=\"{obj['summary']}\" class=\"{obj['statusCategory'].replace(' ','')}\">{obj['key']} {obj['epic_name']}</a><br>\n"
                    table += self._grid_issues(by_epic, key)
                    table += "</div>\n"

                table += "</td>\n"

        return head + style + "</head>\n<body>\n" + table + "</body>\n</html>"

    def _grid_issues(self, by_epic, epic_key):
        html = ""
        if epic_key in by_epic:
            for issue in by_epic[epic_key]:
                title = f"{issue['key']} {issue['summary']} [{issue['assignee']}]"
                html += f"<span class=\"{issue['statusCategory'].replace(' ', '')}\" title=\"{title}\"><a href=\"{issue['url']}\">&nbsp;</a></span>"

        return html

    def write_html(self, html, html_file_base):
        out_dir = self.conf['out_dir']
        mkdir_p(out_dir)

        html_file = os.path.join(out_dir, f"{html_file_base}.html")
        print(f"Writing {html_file}")
        with open(html_file, "w") as f:
            f.write(html)



def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
