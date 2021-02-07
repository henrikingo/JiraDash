#!/bin/python3

from atlassian import Jira
from requests import HTTPError

# Probably I can query these from Jira somehow, but for now it is easiest to just hard code the ones we use:
CUSTOM_FIELD = {
    "Epic Name": "customfield_10841",
    "Story Points": "customfield_10013",
}



class JiraClient:
    def __init__(self, my_config):
        self.conf = my_config
        self.jira = None

    def conn(self):
        print("connecting jira...")
        self.jira = Jira(
            url=self.conf['jira_server'],
            username=self.conf['jira_user'],
            password=self.conf['jira_token'],
            cloud=True
        )
        # Test query to ensure login succeeded
        try:
            jql = f"project = {self.conf['jira_project'][0]}"
            results = self.jira.jql(jql, limit=1)
        except HTTPError as e:
            print("Error connecting to Jira. Please check username and token before anything else.")
            print(e)
            print(e.response.text)

    def get_all_issues(self):
        for project in self.conf['jira_project']:
            jql = f"project = {project}"
            print(jql)
            try:
                results = self.jira.jql(jql)
                print(results)
            except HTTPError as e:
                print(e)
                print(e.response.text)
