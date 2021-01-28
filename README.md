# JiraDash

Tools to automate repetitive Jira work and to report more meaningful statistics than story points.

## Background

The tragedy of the Agile software movement is that we ended up using Jira for it. Every day I
keep asking WTH happened to my simple cards and post it notes??? It's like Jira is the
"Empire strikes back" episode of the Agile saga. It's primary purpose is to keep all those
waterfall project managers full time employed...

I created JiraDash to avoid and bypass unnecessary Jira work so that the team can focus on
designing features and writing code. The tools fall into two main categories, detailed below: 1.
automating redundant work, 2. reporting and forecasting based on introspection of statistical
facts rather than story pointing or other methods based on the opinion of the loudest team member.

## Quick start

    git clone https://github.com/henrikingo/JiraDash.git
    cd JiraDash
    pip install -r requirements.txt
    ./JiraDash.py -h

Create following configuration file in `~/.config/JiraDash`:

    [DEFAULT]
    jira-server=https://example.jira.com
    jira-user=firstname.lastname@example.com
    jira-token=XXXXXXXXXXXXXXXX
    jira-project=WIDGET

To plot various graphs, you need to install [mermaid-cli](https://github.com/mermaid-js/mermaid-cli).

## Automation tools

`./JiraDash.py fixversion`

Set fixVersions field for all (not closed) issues from the epic they belong to. The idea is that
project manager can manage the fixVersions field purely on the epic level, and individual issues
get automatically set.


## Dashboards

`./JiraDash dependencies --out-dir`

List all epics, group by component and create a dependency graph by following the "Depends on" links.
