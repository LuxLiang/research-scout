"""Run after installing research-scout; stores all demo data outside the repo."""
from pathlib import Path
from tempfile import TemporaryDirectory

from research_scout.storage import Archive
from research_scout.workflows.demo import run_demo

if __name__ == '__main__':
    with TemporaryDirectory(prefix='research-scout-example-') as workspace:
        root=Path(workspace)
        print(run_demo(Archive(root/'knowledge'),root/'proposal.md'))
        print((root/'proposal.md').read_text())
