#!/usr/bin/python3
"""
Create a graph using the "depends on" links and draw a SVG using mermaid-cli syntax.

"""
import dateutil.parser
import dateutil.relativedelta
import datetime
import errno
from jira_client import JiraClient, CUSTOM_FIELD
import json
from requests import HTTPError
import os
import re
import subprocess
import sys
import time

def entry_point(my_config):
    print(f"Printing a grid grouping of Epics in project(s): {my_config['jira_project']}")
    b = Burnup(my_config)
    b.get_and_draw()

class Burnup:
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
            series, date_range = self.generate_series(graph)

            csv = self.burnup_csv(series, date_range, project)
            self.write_csv(csv, f"{base}_burnup")

            html = self.burnup_html(series, date_range, project)
            self.write_html(html, f"{base}_burnup")

    def get_issues(self, project):
        jql = f"type != Epic AND project = {project}"
        if self.conf['jira_filter']:
            for filter in self.conf['jira_filter']:
                jql += f" AND {filter}"
        jql += " ORDER BY key"
        print("Jira query: " + jql)
        issues = []
        new_issues = self.jira.jql(jql, start=0, limit=100)
        #new_issues = self.jira.get_all_project_issues(project, limit=100, start=0)
        start_at = 101
        while new_issues['issues']:
            issues.extend(new_issues['issues'])
            new_issues = self.jira.jql(jql, start=start_at, limit=100)
            start_at += 100
            print(len(issues))

        graph = {}
        for issue in issues:
            ## Skip epics that are closed as duplicates of other epics or won't fix
            #if issue['fields']['resolution'] and (
                #issue['fields']['resolution']['name'] == "Duplicate" or 
                #issue['fields']['resolution']['name'] == "Won't Fix"):
               #continue

            key = issue['key']
            #epic_name = issue['fields'][CUSTOM_FIELD['Epic Name']]
            points = issue['fields'][CUSTOM_FIELD['Story Points']]
            points = points if points else 0.0
            summary = issue['fields']['summary']
            status_category = issue['fields']['status']['statusCategory']['name']
            epic_url = self.conf['jira_server'] + "/browse/" + key
            component = issue['fields']['components']
            component = component.pop() if component else {'name': "General"}
            component = component['name'].replace(" ", "_")
            fixVersions = issue['fields']['fixVersions']
            fixVersions = [v['name'] for v in fixVersions]
            fixVersions = fixVersions.pop() if fixVersions else "0.0"

            created = issue['fields']['created']
            created = dateutil.parser.parse(created) if created else None
            statuscategorychangedate = issue['fields']['statuscategorychangedate']
            statuscategorychangedate = dateutil.parser.parse(statuscategorychangedate) if statuscategorychangedate else None
            resolution_date = issue['fields']['resolutiondate']
            resolution_date = dateutil.parser.parse(resolution_date) if resolution_date else None
            start_date = None
            if status_category == "In Progress":
                start_date = dateutil.parser.parse(issue['fields']['statuscategorychangedate'])

            graph[key] = {"url":epic_url, "deps":[], "summary": summary, "statusCategory": status_category, "components":component, "points": points, "fixVersions": fixVersions,
                         "start_date": start_date, "created_date": created, "statuscategorychangedate": statuscategorychangedate, "resolution_date": resolution_date, "key": key}
            issuelinks = issue['fields']['issuelinks']

            for link in issuelinks:
                if link['type']['outward'] == 'Depends on' and 'outwardIssue' in link:
                    dep_key = link['outwardIssue']['key']
                    if self.key_in_set(dep_key):
                        graph[key]['deps'].append(dep_key)

        return graph

    def get_minmax(self, graph):
        created_dates = [obj['created_date'] for obj in graph.values() if obj['created_date']]
        start_dates = [obj['start_date'] for obj in graph.values() if obj['start_date']]
        resolution_dates = [obj['resolution_date'] for obj in graph.values() if obj['resolution_date']]
        min_date = min(created_dates + start_dates + resolution_dates)
        max_date = max(created_dates + start_dates + resolution_dates)
        return {'max': max_date, 'min': min_date}

    def burnup_csv(self, series, date_range, project):
        days = date_range['days']

        title = " AND ".join(self.conf.args.jira_filter) if self.conf.args.jira_filter else project

        csv = title
        for day in (date_range['min'] + datetime.timedelta(d+1) for d in range(days)):
            day_str = day.strftime("%Y-%m-%d")
            csv += f"\t{day_str}"
        csv += "\n"

        csv += "Resolved\t" + "\t".join([str(d) for d in series['resolved']]) + "\n"
        csv += "In Progress\t" + "\t".join([str(d) for d in series['inprogress']]) + "\n"
        csv += "Issues\t" + "\t".join([str(d) for d in series['issues']]) + "\n"

        return csv

    def generate_series(self, graph):
        date_range = self.get_minmax(graph)
        days = date_range['max'] - date_range['min']
        days = days.days
        date_range['days'] = days

        # 3 arrays that have one element per day in date_range
        series = {'issues': [0]*days, 'inprogress': [0]*days, 'resolved': [0]*days}
        for obj in graph.values():
            series['issues'][ (obj['created_date']-date_range['min']).days - 1] += 1
            if obj['start_date']:
                series['inprogress'][ (obj['start_date']-date_range['min']).days - 1] += 1
            if obj['resolution_date']:
                series['resolved'][ (obj['resolution_date']-date_range['min']).days - 1] += 1

        # Now recode arrays so that each element includes the sum of previous days
        for i in range(1, days):
            series['issues'][i] = series['issues'][i-1] + series['issues'][i]
            series['inprogress'][i] = series['inprogress'][i-1] + series['inprogress'][i]
            series['resolved'][i] = series['resolved'][i-1] + series['resolved'][i]
        # For inprogress, we also want to add already resolved count
        for i in range(1, days):
            series['inprogress'][i] = series['inprogress'][i] + series['resolved'][i]

        return series, date_range

    def write_csv(self, csv, csv_file_base):
        out_dir = self.conf['out_dir']
        mkdir_p(out_dir)

        csv_file = os.path.join(out_dir, f"{csv_file_base}.csv")
        print(f"Writing {csv_file}")
        with open(csv_file, "w") as f:
            f.write(csv)

    def burnup_html(self, series, date_range, project):
        days = date_range['days']
        title = " AND ".join(self.conf.args.jira_filter) if self.conf.args.jira_filter else project

        head = f"<html>\n<head><title>{title}</title>\n"
        style = """<script src="https://nvd3.org/assets/lib/d3.v3.js"></script>
<script src="https://nvd3.org//assets/js/nv.d3.js"></script>

<link rel="stylesheet" href="https://cdn.rawgit.com/novus/nvd3/v1.8.1/build/nv.d3.css">
"""
        input_data = self.format_nvd3_data(series, date_range)
        d3graph = """
<div id='chart'>
<svg width="960" height="500" id="chart"></svg>
</div>
<script>
generateGraph = function() {
  var chart = nv.models.lineChart()
                .margin({left: 100})  //Adjust chart margins to give the x-axis some breathing room.
                .useInteractiveGuideline(true)  //We want nice looking tooltips and a guideline!
                .showLegend(true)       //Show the legend, allowing users to turn on/off line series.
                .showYAxis(true)        //Show the y-axis
                .showXAxis(true)        //Show the x-axis
  ;

  chart.xAxis     //Chart x-axis settings
      .axisLabel('Day')
      .tickFormat(function(d) { return d3.time.format('%b %d')(new Date(d)); });

  chart.yAxis     //Chart y-axis settings
      .axisLabel('Issues')
      .tickFormat(d3.format('.02f'));

  var myData = """ + input_data + """

  d3.select('#chart svg')    //Select the <svg> element you want to render the chart in.   
      .datum(myData)         //Populate the <svg> element with chart data...
      .call(chart);          //Finally, render the chart!

  //Update the chart when window resizes.
  //nv.utils.windowResize(function() { chart.update() });
  return chart;
};

nv.addGraph(generateGraph);
</script>
"""

        return head + style + "</head>\n<body>\n" + d3graph + "</body>\n</html>"

    def format_nvd3_data(self, series, date_range):
        issues = []
        inprogress = []
        resolved = []
        for d in range(date_range['days']):
            date = date_range['min']+datetime.timedelta(days=d+1)
            #date = date.strftime("%Y-%m-%d")
            date = int(time.mktime(date.timetuple())) * 1000

            issues.append({'x': date, 'y': series['issues'][d]})
            inprogress.append({'x': date, 'y': series['inprogress'][d]})
            resolved.append({'x': date, 'y': series['resolved'][d]})

        data = [
            {'values': issues, 'key': 'Issues', 'color': '#ffff00', 'area': 'true'},
            {'values': inprogress, 'key': 'In progress', 'color': '#00aa00', 'area': 'true'},
            {'values': resolved, 'key': 'Resolved', 'color': '#111111', 'area': 'true'},
        ]
        return json.dumps(data)

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
