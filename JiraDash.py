#!/usr/bin/python3
import configargparse
import sys
import os.path
from requests import HTTPError
from jiradash.loader import run_command

COMMANDS = [
    "fixversion",
    "dependencies",
    "gantt",
    "grid",
    "burnup",
]



class MyConfig:
    """
    Allows to provide config both as cli options and ConfigParser file.
    """
    description = "Export all tickets from a Jira project"

    def __init__(self, argv):
        """
        From https://stackoverflow.com/questions/3609852/which-is-the-best-way-to-allow-configuration-options-be-overridden-at-the-comman

        After instantiation, read config options from `my_config.args.some_option` or just `my_config['option']`.
        """
        self._argv = argv
        # This is where args end up
        self.args = None

        self.define_options()
        self.parse_options()

    def __getitem__(self, key):
        return vars(self.args)[key]

    def define_options(self):
        p = configargparse.getArgumentParser(default_config_files=['/etc/JiraDash/conf.d/*.conf', '~/.config/JiraDash'])
        p.add('-c', '--config', is_config_file=True, help='Config file.')

        p.add('--jira-user', help="Jira username", required=True)
        p.add('--jira-token', help="Jira API token", required=True)
        p.add('--jira-server', help="Jira server URL", required=True)
        p.add('--jira-project', help="Jira project", required=True, action='append')
        p.add('--jira-filter', help="Filter conditions to add to Jira query. Ex: '--jira-filter fixVersions = alpha1'", action='append')
        p.add('--groupby', help="Group epics or issues by this field in mermaid or csv output. Ex: '--groupby components'", choices=['fixVersions', 'components'])

        p.add('--out-dir', '-o', help="Directory where to output graphs", default="mermaid_out")

        p.add('command', help="command to execute", nargs=1, choices=COMMANDS)

        self._parser = p

    def parse_options(self):
        self.args = configargparse.getArgumentParser().parse_args()

def main(argv):
    my_config = MyConfig(argv)
    run_command(my_config)

if __name__ == "__main__":
    main(sys.argv[1:])
