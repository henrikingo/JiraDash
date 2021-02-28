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

        self._keys = []

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

            obj = {"url":epic_url, "deps":[], "summary": summary, "statusCategory": status_category, "components":component, "points": points, "fixVersions": fixVersions,
                         "start_date": start_date, "created_date": created, "statuscategorychangedate": statuscategorychangedate, "resolution_date": resolution_date, "key": key}
            issuelinks = issue['fields']['issuelinks']

            for link in issuelinks:
                if link['type']['outward'] == 'Depends on' and 'outwardIssue' in link:
                    dep_key = link['outwardIssue']['key']
                    if self.key_in_set(dep_key):
                        obj['deps'].append(dep_key)

            yield key, obj

    def get_issues(self):
        issues = {}
        for key, obj in self.issues():
            issues[key] = obj
        return issues

    def key_in_set(self, key):
        return key in self._keys
