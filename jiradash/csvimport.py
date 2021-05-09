#!/usr/bin/python3
"""
Create new tickets from a csv file
TODO:
 * This is very specific and hardcoded to something I needed to do in a Datastax project. Sorry.
"""

import csv
from jiradash.jira_client import JiraClient, CUSTOM_FIELD
from requests import HTTPError
import sys

def entry_point(my_config):
    print(f"Create new issues from csv file {my_config['csvfile']} in {my_config['jira_project']}.")
    csvimport = CsvImport(my_config)
    csvimport.run()

class CsvImport:
    def __init__(self, my_config):
        self.conf = my_config
        self.jira_client = JiraClient(my_config)
        self.jira_client.conn()
        self.jira = self.jira_client.jira

        self.project = self.conf['jira_project'][0]

    def run(self):
        assert len(self.conf['jira_project']) == 1, "csvimport only supports importing to a single Jira project at a time."
        created_keys = []

        csv_dict = self.read_csv()
        for row in csv_dict:
            if row["Needed for Stargazer"] != "Yes":
                created_keys.append("")
                # Print matching nr of lines as is in the input file. This allows the output to be copy pasted back into a spreadsheet.
                print()
                continue

            key = self.create_issue(row)
            created_keys.append(key)
            print(key)

        #print("\n".join(created_keys))

    def read_csv(self):
        file_name = self.conf['csvfile']
        csv_file = open(file_name)
        return csv.DictReader(csv_file)

    def create_issue(self, row):
        issue = self.create_issue_json(row)
        post_return = None
        try:
            post_return = self.jira.create_issue(issue)
            pass
        except HTTPError as e:
            print(e)
            print(e.response.text)

        key = post_return['key']
        DB_issue = f"DB-{row['Issue key']}"
        issue_link = self.create_issuelinks_json(key, DB_issue)

        try:
            post_return = self.jira.create_issue_link(issue_link)
        except HTTPError as e:
            print(e)
            print(e.response.text)

        return key

    def create_issue_json(self, row):
        DB_issue = f"DB-{row['Issue key']}"
        issue = {}
        issue['issuetype'] = {'name': "Bug"}
        issue['project'] = {'key': self.project}
        issue['summary'] = f"Port bug: {DB_issue} - {row['Summary']}"
        issue[CUSTOM_FIELD['Epic']] = "STAR-99"
        issue['labels'] = ['db-stargazer-port', 'db-stargazer-port-bug', 'db-stargazer-bulk-created']
        issue['description'] = """Please port the bug fix from https://datastax.jira.com/browse/""" + DB_issue + """
            
            >> """ + row['Summary'] + """
            
            Preferably it should be ported to OSS Cassandra, to all affected branches. From the cassandra-4.0 branch it will be merged into datastax/cassandra, at which point this ticket can be closed.
        """

        assert "summary" in issue
        assert "project" in issue
        assert "issuetype" in issue
        return issue

    def create_issuelinks_json(self, key, DB_issue):
        issuelinks = {
            'type': {'name': 'Related Issue'},
            'inwardIssue': {'key': DB_issue},
            'outwardIssue': {'key': key}
            }
        return issuelinks
