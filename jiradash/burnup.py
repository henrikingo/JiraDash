#!/usr/bin/python3
"""
Create a burnup chart using nvd3.

"""
import dateutil.parser
import dateutil.relativedelta
import datetime
import errno
from jiradash.jira_model import JiraModel
from jiradash.io import Writer
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
        self.model = JiraModel(my_config)
        self.writer = Writer(my_config)
        self.project = self.writer.project
        self.base = self.writer.base

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

        issues = self.model.get_issues()
        series, date_range = self.generate_series(issues)

        csv = self.burnup_csv(series, date_range, self.project)
        self.writer.csv(csv)

        html = self.burnup_html(series, date_range, self.project)
        self.writer.html(html)

    def get_minmax(self, issues):
        created_dates = [obj['created_date'] for obj in issues.values() if obj['created_date']]
        start_dates = [obj['start_date'] for obj in issues.values() if obj['start_date']]
        resolution_dates = [obj['resolution_date'] for obj in issues.values() if obj['resolution_date']]
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

    def generate_series(self, issues):
        date_range = self.get_minmax(issues)
        days = date_range['max'] - date_range['min']
        days = max(days.days,1)
        date_range['days'] = days

        # 3 arrays that have one element per day in date_range
        series = {'issues': [0]*(days+1), 'inprogress': [0]*(days+1), 'resolved': [0]*(days+1)}
        for obj in issues.values():
            series['issues'][ (obj['created_date']-date_range['min']).days] += 1
            if obj['start_date']:
                series['inprogress'][ (obj['start_date']-date_range['min']).days] += 1
            if obj['resolution_date']:
                series['resolved'][ (obj['resolution_date']-date_range['min']).days] += 1

        # Now recode arrays so that each element includes the sum of previous days
        for i in range(1, days+1):
            series['issues'][i] = series['issues'][i-1] + series['issues'][i]
            series['inprogress'][i] = series['inprogress'][i-1] + series['inprogress'][i]
            series['resolved'][i] = series['resolved'][i-1] + series['resolved'][i]
        # For inprogress, we also want to add already resolved count
        for i in range(1, days+1):
            series['inprogress'][i] = series['inprogress'][i] + series['resolved'][i]

        return series, date_range

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
        for d in range(date_range['days']+1):
            date = date_range['min']+datetime.timedelta(days=d)
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
