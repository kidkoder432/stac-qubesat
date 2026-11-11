import time

# this is a very general class that will represent the type of every "action" during the mission


class Task:
    """
    name           : human-readable label
    priority       : lower number = higher priority (1 is highest)
    period         : seconds between runs; None = one-shot (runs once, then never again)
    schedule_later : False -> first run happens right away (after `delay`)
                     True  -> first run waits one full `period` (after `delay`)
    func           : the callable that does the work
    delay          : extra seconds to wait before the first run (e.g. 30 min burn wire)
    """

    def __init__(self, name, priority, period, schedule_later, func, delay=0.0):
        self.name = name
        self.priority = priority
        self.period = period
        self.schedule_later = schedule_later
        self.func = func
        self.delay = delay
        self.last_run_time = None  # None until the task has run once
        self.done = False  # True once a one-shot task has run
        self._ready_at = None  # time of first run, fixed the first time is_due is called

    def is_due(self, now: float) -> bool:
        if self.done:
            return False

        if self.last_run_time is None:
            if self._ready_at is None:
                self._ready_at = now + self.delay
                if self.schedule_later and self.period is not None:
                    self._ready_at += self.period
            return now >= self._ready_at

        if self.period is None:
            return False
        return (now - self.last_run_time) >= self.period

    def run(self):
        try:
            return self.func()
        finally:
            # set even if func raises, so a failing task doesn't spin every loop
            self.last_run_time = time.monotonic()
            if self.period is None:
                self.done = True
