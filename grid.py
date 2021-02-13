#!/usr/bin/python3
"""
Create a graph using the "depends on" links and draw a SVG using mermaid-cli syntax.

"""
import dateutil.parser
import dateutil.relativedelta
import datetime
import errno
from jira_client import JiraClient, CUSTOM_FIELD
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
    # TODO: configurable
    releases = [
        "stargazer-alpha",
        "stargazer-alpha2",
        "stargazer-alpha3",
        "stargazer-alpha4",
        "stargazer-beta",
        "0.0",
        ]

    def __init__(self, my_config):
        self.conf = my_config
        self.jira_client = JiraClient(my_config)
        self.jira_client.conn()
        self.jira = self.jira_client.jira

        self._keys = []

    def get_and_draw(self):
        for project in self.conf['jira_project'] if self.conf['jira_project'] else []:
            base = project
            for jira_filter in self.conf['jira_filter'] if self.conf['jira_filter'] else []:
                base += "_" + _safe_chars(jira_filter).replace(" ", "_")
            if self.conf.args.groupby:
                base += "_" + self.conf.args.groupby

            graph = self.get_issues(project)

            grid = self.grid_obj(graph, project)
            csv = self.grid_csv(grid, project)
            self.write_csv(csv, f"{base}_grid")
            html = self.grid_html(grid, project)
            self.write_html(html, f"{base}_grid")

    def get_issues(self, project):
        jql = f"type = Epic AND project = {project}"
        if self.conf['jira_filter']:
            for filter in self.conf['jira_filter']:
                jql += f" AND {filter}"
        print("Jira query: " + jql)
        epics = self.jira.jql(jql, limit=10000)
        graph = {}
        self.get_keys(epics['issues'])

        for epic in epics['issues']:
            # Skip epics that are closed as duplicates of other epics or won't fix
            if epic['fields']['resolution'] and (
                epic['fields']['resolution']['name'] == "Duplicate" or 
                epic['fields']['resolution']['name'] == "Won't Fix"):
               continue

            key = epic['key']
            epic_name = epic['fields'][CUSTOM_FIELD['Epic Name']]
            points = epic['fields'][CUSTOM_FIELD['Story Points']]
            points = points if points else 0.0
            summary = epic['fields']['summary']
            status_category = epic['fields']['status']['statusCategory']['name']
            epic_url = self.conf['jira_server'] + "/browse/" + key
            component = epic['fields']['components']
            component = component.pop() if component else {'name': "General"}
            component = component['name'].replace(" ", "_")
            fixVersions = epic['fields']['fixVersions']
            fixVersions = [v['name'] for v in fixVersions]
            fixVersions = fixVersions.pop() if fixVersions else "0.0"

            epic_name = _safe_chars(epic_name)

            start_date = None
            if status_category == "In Progress":
                start_date = dateutil.parser.parse(epic['fields']['statuscategorychangedate'])

            resolution_date = epic['fields']['resolutiondate']
            if resolution_date:
                resolution_date = dateutil.parser.parse(resolution_date)
                # TODO: Jira can also track actual time spent. Now we just use the estimate as the duration.
                start_date = resolution_date - dateutil.relativedelta.relativedelta(months=points)
            else:
                if start_date:
                    resolution_date = start_date + dateutil.relativedelta.relativedelta(months=int(points))

            graph[key] = {"name":epic_name, "url":epic_url, "deps":[], "summary": summary, "statusCategory": status_category, "components":component, "points": points, "fixVersions": fixVersions,
                          "start_date": start_date, "resolution_date": resolution_date, "key": key}
            issuelinks = epic['fields']['issuelinks']

            for link in issuelinks:
                if link['type']['outward'] == 'Depends on' and 'outwardIssue' in link:
                    dep_key = link['outwardIssue']['key']
                    if self.key_in_set(dep_key):
                        graph[key]['deps'].append(dep_key)

        return graph

    def grid_obj(self, graph, project):
        groups = set()
        for obj in graph.values():
            groups.add(obj['components'])
        groups = _sort_by_depth(groups, 'components', graph)

        grid = {}
        for group in groups:
            grid[group] = {}
            for rel in self.releases:
                grid[group][rel] = {}

        for key, obj in graph.items():
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
                        csv += "\t" + obj['key'] + " " + obj['name']
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

    def grid_html(self, grid, project):
        head = f"<html>\n<head><title>{project}</title>\n"
        style = """<style type="text/css">
    table td {padding: 5px; font-family: sans-serif;}
    table td {border-top: 1px solid #ddd;}
    a.ToDo {text-decoration: none; color: #666;}
    a.InProgress {text-decoration: none; color: #090;}
    a.Done {text-decoration: line-through; color: #333;}
</style>
"""

        table = f"<table>\n<tr><th>{project}</th><th>" + "</th><th>".join(self.releases) + "</th></tr>\n"

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
            table += f"<tr><th>{component}</th>"
            for rel in self.releases:
                table += "<td>"
                for key in sorted(grid[component][rel].keys()):
                    obj = grid[component][rel][key]

                    table += f"<a href=\"{obj['url']}\" class=\"{obj['statusCategory'].replace(' ','')}\">{obj['key']} {obj['name']}</a><br>\n"

                table += "</td>\n"

        return head + style + "</head>\n<body>\n" + table + "</body>\n</html>"

    def write_html(self, html, html_file_base):
        out_dir = self.conf['out_dir']
        mkdir_p(out_dir)

        html_file = os.path.join(out_dir, f"{html_file_base}.html")
        print(f"Writing {html_file}")
        with open(html_file, "w") as f:
            f.write(html)

    def get_keys(self, epics):
        for epic in epics:
            # Skip epics that are closed as duplicates of other epics or won't fix
            if epic['fields']['resolution'] and (
                epic['fields']['resolution']['name'] == "Duplicate" or 
                epic['fields']['resolution']['name'] == "Won't Fix"):
               continue

            self._keys.append(epic['key'])

    def key_in_set(self, key):
        return key in self._keys

def _safe_chars(string):
    return re.sub(r'\W', " ", string)

def _depth(graph, epic, d=0):
    if epic['deps']:
        return _depth(graph, graph[epic['deps'][0]], d+1)
    return d

def _group_depth(group, groupby, graph):
    use_shortest = True if groupby != "fixVersions" else False
    depth = 9999 if use_shortest else -9999
    for key, obj in graph.items():
        if (not groupby) or group == obj[groupby]:
            new_depth = _depth(graph, obj)
            if new_depth < depth and use_shortest:
                depth = new_depth
            elif new_depth > depth and not use_shortest:
                depth = new_depth
    return depth

def _sort_epics_by_depth(group, groupby, graph):
    pairs = []
    for key, obj in graph.items():
        if groupby and obj[groupby] != group:
            continue
        pairs.append((key, _depth(graph, obj)))

    pairs.sort(key = lambda x: x[1])
    return [epic[0] for epic in pairs]

def _sort_by_depth(groups, groupby, graph):
    pairs = [(group, _group_depth(group, groupby, graph)) for group in groups]
    pairs.sort(key = lambda x: x[1])
    return [group[0] for group in pairs]

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
