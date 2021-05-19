#!/usr/bin/python3
"""
Query and process Jira tickets based on a list.
TODO:
 * This is very specific and hardcoded to something I needed to do in a Datastax project. Sorry.
"""
import csv
from jiradash.jira_client import JiraClient, CUSTOM_FIELD
from requests import HTTPError
import semver
import sys

def entry_point(my_config):
    print(f"Process tickets from list file {my_config['csvfile']} in {my_config['jira_project']}.")
    listinput = ListInput(my_config)
    listinput.run()

class ListInput:
    def __init__(self, my_config):
        self.conf = my_config
        self.jira_client = JiraClient(my_config)
        self.jira_client.conn()
        self.jira = self.jira_client.jira

        self.project = self.conf['jira_project'][0]

        self.output_rows= []
        self.not_found_list = []
        self.all_components = set()

    def run(self):
        assert len(self.conf['jira_project']) == 1, "listinput only supports querying a single Jira project at a time."

        row_count = 0
        csv = self.read_csv()
        for row in csv:
            row_count += 1

            #if row_count%100 != 0:
                #continue

            dsp_ticket = row[0]
            issue = self.get_dsp_ticket(dsp_ticket)
            if issue:
                if row_count % 100 == 0:
                    print("Progress: " + dsp_ticket, flush=True)
                    sys.stdout.flush()
                components = issue['fields']['components']
                components = [c['name'] for c in components]
                for c in components:
                    self.all_components.add(c)

                if not ("Cassandra" in components or "Core" in components or "Security" in components or "CQL" in components):
                    continue
                status_category = issue['fields']['status']['statusCategory']['name']
                if not status_category == "Done":
                    continue
                resolution = issue['fields']['resolution']['name']
                if not resolution in ["Done", "Fixed"]:
                    continue
                issue_type = issue['fields']['issuetype']['name']
                if not issue_type == "Bug":
                    continue

                fixVersions = issue['fields']['fixVersions']
                versions = [v['name'] for v in fixVersions]
                max_ver = _max_semver(versions)
                if not _51_or_6(max_ver):
                    continue

                summary = issue['fields']['summary']
                new_row = [dsp_ticket, '"'+summary+'"', str(versions)]
                self.output_rows.append(new_row)
                #import pprint
                #pprint.pprint(issue)
                print(",".join(new_row))


        #rows = [",".join(r) for r in self.output_rows]
        #print("\n".join(rows))
        print("All components found: " + str(self.all_components))
        print("The following tickets weren't found in Jira:" + str(self.not_found_list))

    def read_csv(self):
        file_name = self.conf['csvfile']
        csv_file = open(file_name)
        return csv.reader(csv_file)

    def get_dsp_ticket(self, key):
        issue = None
        try:
            issue = self.jira.get_issue(key)
        except HTTPError as e:
            if e.response.status_code == 404:
                self.not_found_list.append(key)
            else:
                print(e)
                print(e.response.text)
                sys.exit(1)
        return issue

def _max_semver(versions):
    ver = '0.0.0'
    for ver2 in versions:
        try:
            if semver.compare(ver, ver2) < 0:
                ver = ver2
        except ValueError:
            continue
    return ver

def _51_or_6(version):
    return semver.compare('5.0.99', version) < 0
