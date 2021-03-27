"""
Utility to execute mermaid-cli.
"""

from .io import Writer, mkdir_p
import os
import subprocess


class Mermaid(Writer):
    def exec_mermaid(self, markup):
        markup_file = self.write_file(markup, extension="mermaid")

        svg_file = os.path.splitext(markup_file)[0] + ".svg"
        cmd = ["mmdc", "--input", markup_file, "--output", svg_file]
        print(cmd)
        subprocess.run(cmd)
