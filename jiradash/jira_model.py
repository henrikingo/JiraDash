#!/usr/bin/python3
"""
Data abstraction layer for jira queries

"""

import dateutil.parser
import dateutil.relativedelta
import datetime
import errno
import json
from requests import HTTPError
import os
import re
import subprocess
import sys
import time

from .jira_client import JiraClient, CUSTOM_FIELD

class JiraModel:
    def __init__(self, my_config):
        self.conf = my_config
        self.jira_client = JiraClient(my_config)
        self.jira_client.conn()
        self.jira = self.jira_client.jira

    def _build_issues_query(self):
        jql = f"type != Epic"
        if self.conf['jira_project']:
            jql += f" AND project IN({', '.join(self.conf['jira_project'])})"
        if self.conf['jira_filter']:
            for filter in self.conf['jira_filter']:
                jql += f" AND {filter}"
        jql += " ORDER BY key"
        print("Jira query: " + jql)
        return jql

    def _query_issues(self):
        jql = self._build_issues_query()
        new_issues = self.jira.jql(jql, start=0, limit=100)
        start_at = 101
        while new_issues['issues']:
            print(len(new_issues['issues']))
            for issue in new_issues['issues']:
                yield issue
            new_issues = self.jira.jql(jql, start=start_at, limit=100)
            start_at += 100

    def issues(self):
        for issue in self._query_issues():
            # Skip issues that are closed as duplicates of other epics or won't fix
            if issue['fields']['resolution'] and (
                issue['fields']['resolution']['name'] == "Duplicate" or 
                issue['fields']['resolution']['name'] == "Won't Fix"):
               continue

            key, obj = self._get_fields(issue)
            epic = issue['fields'][CUSTOM_FIELD['Epic']]
            epic = epic if epic else "No Epic"
            obj['epic'] = epic
            yield key, obj

    def get_issues(self):
        issues = {k:v for k,v in self.issues()}
        issues = self.remove_dead_end_links(issues)
        return issues

    def _build_epics_query(self):
        jql = f"type = Epic"
        if self.conf['jira_project']:
            jql += f" AND project IN({', '.join(self.conf['jira_project'])})"
        if self.conf['jira_filter']:
            for filter in self.conf['jira_filter']:
                jql += f" AND {filter}"
        jql += " ORDER BY key"
        print("Jira query: " + jql)
        return jql

    def _query_epics(self):
        jql = self._build_epics_query()
        new_issues = self.jira.jql(jql, start=0, limit=100)
        start_at = 101
        while new_issues['issues']:
            print(len(new_issues['issues']))
            for epic in new_issues['issues']:
                yield epic
            new_issues = self.jira.jql(jql, start=start_at, limit=100)
            start_at += 100

    def epics(self):
        for epic in self._query_epics():
            # Skip epics that are closed as duplicates of other epics or won't fix
            if epic['fields']['resolution'] and (
                epic['fields']['resolution']['name'] == "Duplicate" or 
                epic['fields']['resolution']['name'] == "Won't Fix"):
               continue

            key, obj = self._get_fields(epic)

            epic_name = epic['fields'][CUSTOM_FIELD['Epic Name']]
            epic_name = _safe_chars(epic_name)
            obj['epic_name'] = epic_name

            yield key, obj

    def get_epics(self):
        epics = {k:v for k, v in self.epics()}
        epics = self.remove_dead_end_links(epics)
        return epics

    def _get_fields(self, issue):
        key = issue['key']
        points = issue['fields'][CUSTOM_FIELD['Story Points']]
        points = points if points else 0.0
        summary = issue['fields']['summary']
        assignee = issue['fields']['assignee']
        assignee = assignee['displayName'] if assignee else ""
        status_category = issue['fields']['status']['statusCategory']['name']
        url = self.conf['jira_server'] + "/browse/" + key
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

        obj = {"url":url, "deps":[], "summary": summary, "statusCategory": status_category, "components":component, "points": points, "fixVersions": fixVersions,
                        "start_date": start_date, "created_date": created, "statuscategorychangedate": statuscategorychangedate, "resolution_date": resolution_date, 
                        "assignee": assignee, "key": key}
        issuelinks = issue['fields']['issuelinks']

        for link in issuelinks:
            if link['type']['outward'] == 'Depends on' and 'outwardIssue' in link:
                dep_key = link['outwardIssue']['key']
                obj['deps'].append(dep_key)

        return key, obj

    def remove_dead_end_links(self, issues):
        all_removed = []
        for key, obj in issues.items():
            to_remove = []
            for dep_key in obj['deps']:
                if not dep_key in issues:
                    to_remove.append(dep_key)
            for dead_key in to_remove:
                obj['deps'].remove(dead_key)
            all_removed += to_remove
        print(f"Ignoring dependencies not in this set: {all_removed}")
        return issues

    def get_issues_per_epic(self):
        by_epic = {}
        count = 0
        for key, obj in self.issues():
            count += 1

            epic = obj['epic']
            if not epic in by_epic:
                by_epic[epic] = []
            by_epic[epic].append(obj)

        print(count)
        return by_epic

def _safe_chars(string):
    return re.sub(r'\W', " ", string)

