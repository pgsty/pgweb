"""Shared book and training catalogue for the index and homepage."""

from pgweb.util.yamldataloader import YamlDataLoader


class TutorialsData(YamlDataLoader):
    DATAFILE = "tutorials.yaml"


tutorialsdata = TutorialsData()
