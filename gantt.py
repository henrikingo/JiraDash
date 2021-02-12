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

            markup = self.draw_group(graph, project)
            self.exec_mermaid(markup, f"{base}_gantt")

            csv = self.gantt_csv(graph, project)
            self.write_csv(csv, f"{base}_gantt")

            csv = self.groups_csv(graph, project)
            self.write_csv(csv, f"{base}_components")

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
                          "start_date": start_date, "resolution_date": resolution_date}
            issuelinks = epic['fields']['issuelinks']

            for link in issuelinks:
                if link['type']['outward'] == 'Depends on' and 'outwardIssue' in link:
                    dep_key = link['outwardIssue']['key']
                    if self.key_in_set(dep_key):
                        graph[key]['deps'].append(dep_key)

        return graph

    def draw_group(self, graph, project):
        output = """gantt
    dateFormat  YYYY-MM-DD
    title       """ + project + """

"""
        groupby = self.conf.args.groupby
        groups = set()
        # initialize
        if groupby:
            for obj in graph.values():
                groups.add(obj[groupby])
        else:
            # Mermaid Gantt chart must have sections. Default section name when no grouping used.
            groups = {"Epics"}

        urls = ""
        classes = ""
        start_node = "start"

        for group in _sort_by_depth(groups, groupby, graph):
            output += f"    section {group}\n"

            for key in _sort_epics_by_depth(group, groupby, graph):
                obj = graph[key]
                if groupby and obj[groupby] != group:
                    continue

                line = "    %-50s:" % f"{key} {obj['name']}"
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
        groups = set()
        # initialize
        if groupby:
            for obj in graph.values():
                groups.add(obj[groupby])
        else:
            groups = {"Epics"}

        groups = _sort_by_depth(groups, groupby, graph)

        head = f"{project}\n{groupby}\tEpic\tFix version\tEstimate\tResources allocated\tSprints->\n"
        sprints ="\t\t\t\t\n"  # Add sprints when we know how many there are

        body = ""
        for group in groups:
            body += f"\n{group}\n"
            for key in _sort_epics_by_depth(group, groupby, graph):
                obj = graph[key]
                line = f"\t{key} {obj['name']}\t{str(obj['fixVersions'])}\t{obj['points']}\n"
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
        groups = set()
        # initialize
        if groupby:
            for obj in graph.values():
                groups.add(obj[groupby])
        else:
            groups = {"Epics"}
        groups = _sort_by_depth(groups, groupby, graph)

        head = f"{project}\n{groupby}\tEstimate\tResources allocated\tSprints->\n"
        sprints ="\t\t\t\t\n"  # Add sprints when we know how many there are

        body = "Totals:\n"
        for group in groups:
            points = 0.0
            for key in _sort_epics_by_depth(group, groupby, graph):
                points += graph[key]['points']
            body += f"{group}\t{points}\n"

        return head + sprints + body


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
