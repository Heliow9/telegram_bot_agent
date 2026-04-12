import subprocess
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger


def run_script(script_name: str):
    print(f"Executando: {script_name}")
    subprocess.run([sys.executable, script_name], check=False)


def start_scheduler():
    scheduler = BlockingScheduler(timezone="America/Recife")

    scheduler.add_job(
        lambda: run_script("send_morning_multi.py"),
        CronTrigger(hour=8, minute=0),
        id="send_morning_multi",
        replace_existing=True,
    )

    scheduler.add_job(
        lambda: run_script("send_afternoon_multi.py"),
        CronTrigger(hour=12, minute=30),
        id="send_afternoon_multi",
        replace_existing=True,
    )

    scheduler.add_job(
        lambda: run_script("send_30min_multi.py"),
        CronTrigger(minute="*/5"),
        id="send_30min_multi",
        replace_existing=True,
    )

    print("Scheduler iniciado.")
    scheduler.start()


if __name__ == "__main__":
    start_scheduler()