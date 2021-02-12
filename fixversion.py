#!/usr/bin/python3
"""
Set fix version for issues from the Epic they belong to.

This will not touch statusCategory=Done issues at all.

The purpose of this command is to facilitate a workflow where a project manager can set fixVersions
only for Epics, and the version is then populated down to all tickets that are part of that epic.

TODO:
 * Doesn't unset any existing fix versions. What if an Epic changes fix version? Now issues will have
   both the old and new version.
"""

from jira_client import JiraClient, CUSTOM_FIELD
from requests import HTTPError
import sys

def entry_point(my_config):
    print(f"Setting fixversion on all issues in {my_config['jira_project']} to match Epic fixversion.")
    setfix = SetFixVersion(my_config)
    setfix.set_fixversion()

class SetFixVersion:
    def __init__(self, my_config):
        self.conf = my_config
        self.jira_client = JiraClient(my_config)
        self.jira_client.conn()
        self.jira = self.jira_client.jira

    def set_fixversion(self):
        for project in self.conf['jira_project']:
            self.set_project_fixversion(project)

    def set_project_fixversion(self, project):
        jql = f"type = Epic AND project = {project} AND statusCategory != Done"
        epics = self.jira.jql(jql, limit=10000)
        for epic in epics['issues']:
            epic_name = epic['fields'][CUSTOM_FIELD['Epic Name']]
            epic_fixversions = epic['fields']['fixVersions']
            jql = f"type != Epic AND project = {project} AND 'Epic Link' = '{epic_name}' AND statusCategory != Done"
            issues_in_epic = self.jira.jql(jql, limit=100000)
            print(f"Setting fixVersions for {len(issues_in_epic['issues'])} issues in '{epic_name}' epic.")
            for issue in issues_in_epic['issues']:
                key = issue['key']
                # It's a list
                fixversions = issue['fields']['fixVersions']
                # It doesn't matter that the same version now may appear twice. Jira is fine and de-duplicates them.
                new_fixversions = epic_fixversions
                # new_fixversions = epic_fixversions + fixversions
                set_fields = {"fixVersions": new_fixversions}
                try:
                    self.jira.update_issue_field(key, set_fields)
                except HTTPError as e:
                    print(e)
                    print(e.response.text)
