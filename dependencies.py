#!/usr/bin/python3
"""
Create a graph using the "depends on" links and draw a SVG using mermaid-cli syntax.

"""

import errno
from jira_client import JiraClient, CUSTOM_FIELD
from requests import HTTPError
import os
import re
import subprocess
import sys

def entry_point(my_config):
    print(f"Creating dependency diagram of Epics in project(s): {my_config['jira_project']}")
    deps = Dependencies(my_config)
    deps.get_and_draw()

class Dependencies:
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
        for project in self.conf['jira_project']:
            graph = self.get_issues(project)

            markup = self.draw_group(graph)
            self.exec_mermaid(markup, "dependencies")
            # Backward compatibility
            self.exec_mermaid(markup, "dependencies")

            csv = self.gantt_csv(graph, project)
            self.write_csv(csv, f"{project}_gantt")

            csv = self.components_csv(graph, project)
            self.write_csv(csv, f"{project}_components")

    def get_issues(self, project):
        jql = f"type = Epic AND project = {project}"
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
            component = component.pop() if component else {'name': "*"}
            component = component['name'].replace(" ", "_")
            fixVersions = epic['fields']['fixVersions']
            fixVersions = [v['name'] for v in fixVersions]

            epic_name = _safe_chars(epic_name)

            graph[key] = {"name":epic_name, "url":epic_url, "deps":[], "summary": summary, "statusCategory": status_category, "component":component, "points": points, "fixVersions": fixVersions}
            issuelinks = epic['fields']['issuelinks']

            for link in issuelinks:
                if link['type']['outward'] == 'Depends on' and 'outwardIssue' in link:
                    dep_key = link['outwardIssue']['key']
                    if self.key_in_set(dep_key):
                        graph[key]['deps'].append(dep_key)

        return graph

    def draw(self, graph):
        output = "graph RL;\n"
        urls = ""
        classes = ""
        start_node = "start"

        for key, obj in graph.items():
            urls += f"    click {key} \"{obj['url']}\" \"{obj['summary']}\"\n"
            classes += f"    class {key} {self._get_css_class(obj)}\n"
            if obj['deps']:
                for dep in obj['deps']:
                    output += f"    {key}[{key} {obj['name']}]-->{dep}\n"
                    #output += f"    {key}[{key}]-->{dep}\n"
            else:
                output += f"    {key}[{key} {obj['name']}]-->{start_node}(({start_node}))\n"
                #output += f"    {key}[{key}]-->{start_node}(({start_node}))\n"
        output += urls + classes + self.styles
        #output += classes + self.styles
        print(output)

    def draw_group(self, graph):
        output = "graph RL;\n"
        subgraphs = set()
        # initialize
        for obj in graph.values():
            subgraphs.add(obj['component'])

        urls = ""
        classes = ""
        start_node = "start"

        output += f"    subgraph *\n"
        output += f"    {start_node}(({start_node}))\n"
        for key, obj in graph.items():
            if obj['component'] != "*":
                continue

            urls += f"    click {key} \"{obj['url']}\" \"{obj['summary']}\"\n"
            classes += f"    class {key} {self._get_css_class(obj)}\n"
            if obj['deps']:
                for dep in obj['deps']:
                    output += f"    {key}[{key} {obj['name']}]-->{dep}\n"
            else:
                output += f"    {key}[{key} {obj['name']}]-->{start_node}(({start_node}))\n"
        output += "    end\n"

        for component in _sort_by_depth(subgraphs, graph):
            if component == "*":
                continue
            output += f"    subgraph {component}\n"

            for key, obj in graph.items():
                if obj['component'] != component:
                    continue

                urls += f"    click {key} \"{obj['url']}\" \"{obj['summary']}\"\n"
                classes += f"    class {key} {self._get_css_class(obj)}\n"
                if obj['deps']:
                    for dep in obj['deps']:
                        output += f"    {key}[{key} {obj['name']}]-->{dep}\n"
                else:
                    output += f"    {key}[{key} {obj['name']}]-->{start_node}(({start_node}))\n"

            output += "    end\n"

        output += urls + classes + self.styles
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
        components = set()
        # initialize
        for obj in graph.values():
            components.add(obj['component'])
        components = _sort_by_depth(components, graph)

        head = f"{project}\nComponent\tEpic\tFix version\tEstimate\tResources allocated\tSprints->\n"
        sprints ="\t\t\t\t\n"  # Add sprints when we know how many there are

        body = ""
        for component in components:
            body += f"\n{component}\n"
            for key in _sort_epics_by_depth(component, graph):
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

    def components_csv(self, graph, project):
        components = set()
        # initialize
        for obj in graph.values():
            components.add(obj['component'])
        components = _sort_by_depth(components, graph)

        head = f"{project}\nComponent\tEstimate\tResources allocated\tSprints->\n"
        sprints ="\t\t\t\t\n"  # Add sprints when we know how many there are

        body = "Totals:\n"
        for component in components:
            points = 0.0
            for key in _sort_epics_by_depth(component, graph):
                points += graph[key]['points']
            body += f"{component}\t{points}\n"

        return head + sprints + body


def _safe_chars(string):
    return re.sub(r'\W', " ", string)

def _depth(graph, epic, d=0):
    if epic['deps']:
        return _depth(graph, graph[epic['deps'][0]], d+1)
    return d

def _component_depth(component, graph):
    depth = 9999
    for key, obj in graph.items():
        if component == obj['component']:
            new_depth = _depth(graph, obj)
            if new_depth < depth:
                depth = new_depth
    return depth

def _sort_epics_by_depth(component, graph):
    pairs = []
    for key, obj in graph.items():
        if obj['component'] != component:
            continue
        pairs.append((key, _depth(graph, obj)))

    pairs.sort(key = lambda x: x[1])
    return [epic[0] for epic in pairs]

def _sort_by_depth(components, graph):
    """
    mermaid with subgraphs sometimes places a node in the wrong subgraph. The same as a dependant's,
    instead of where the node itself is defined. It seems to help to sort the graph such that
    the main graph is first (start and *) and then subgraphs that are closest to start next. When
    there are many paths from a subgraph to start, we count the shortest path.
    """
    pairs = [(component, _component_depth(component, graph)) for component in components]
    pairs.sort(key = lambda x: x[1])
    return [component[0] for component in pairs]

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
