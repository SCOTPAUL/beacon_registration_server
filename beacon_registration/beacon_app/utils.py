import datetime
from json import JSONEncoder


class Streak:
    def __init__(self, start: datetime.date, end: datetime.date):
        self.start = start
        self.end = end

    def __len__(self) -> int:
        return (self.end - self.start).days

    def __str__(self) -> str:
        # ISO 8601
        return str(self.start) + '/' + str(self.end)

    def __repr__(self):
        return str(self)
