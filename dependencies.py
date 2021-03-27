#!/usr/bin/python3
"""
Create a graph using the "depends on" links and draw a SVG using mermaid-cli syntax.

"""

import errno
from jiradash.jira_model import JiraModel
from jiradash.mermaid_wrapper import Mermaid
from requests import HTTPError
import os
import re
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
        self.model = JiraModel(my_config)
        self.mermaid = Mermaid(my_config)
        self.project = self.mermaid.project
        self.base = self.mermaid.base

    def get_and_draw(self):
        epics = self.model.get_epics()

        markup = self.draw_group(epics)
        self.mermaid.exec_mermaid(markup)

    def draw_group(self, graph):
        output = "graph RL;\n"
        groupby = self.conf.args.groupby
        # Mermaid Gantt chart must have sections. Default section name when no grouping used.
        groups = {"Epics"}
        if groupby:
            groups = self.model.get_groups(groupby=groupby)

        urls = ""
        classes = ""
        start_node = "start"

        for component in groups:
            #if component == "*":
                #continue
            output += f"    subgraph {component}\n"

            for key, obj in graph.items():
                if groupby and obj[groupby] != component:
                    continue

                urls += f"    click {key} \"{obj['url']}\" \"{obj['summary']}\"\n"
                classes += f"    class {key} {self._get_css_class(obj)}\n"
                if obj['deps']:
                    for dep in obj['deps']:
                        output += f"    {key}[{key} {obj['epic_name']}]-->{dep}\n"
                else:
                    output += f"    {key}[{key} {obj['epic_name']}]-->{start_node}(({start_node}))\n"

            output += "    end\n"

        output += urls + classes + self.styles
        #print(output)
        return output

    def _get_css_class(self, obj):
        css_class = obj['statusCategory'].replace(" ", "")
        return css_class

