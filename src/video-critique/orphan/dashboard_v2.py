"""
Simplified Dashboard API v2 - Just send raw database data
Frontend does all the processing
"""

import json
import sqlite3
from datetime import datetime
from typing import Dict, Any, List

from config import HISTORY_DB_PATH
from logger import logger
from utils import add_working_days


async def get_dashboard_raw_data(mode: str, period: str) -> Dict[str, Any]:
    """
    Get raw database data and send it to frontend
    Frontend will do all the processing
    """
    try:
        # Get all tasks from both live and completed tables (both in same DB file)
        live_tasks = []
        completed_tasks = []

        with sqlite3.connect(HISTORY_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            # Get live tasks
            cursor = conn.execute(
                """SELECT * FROM live_tasks"""
            )
            live_rows = cursor.fetchall()

            for row in live_rows:
                task = dict(row)
                # Parse version history JSON
                if task.get('Version History'):
                    try:
                        task['version_history'] = json.loads(task['Version History'])
                    except:
                        task['version_history'] = []
                else:
                    task['version_history'] = []

                # Calculate submission date (3 working days after filming date)
                task['submission_date'] = calculate_submission_date(task)

                live_tasks.append(task)

            # Get completed tasks
            cursor = conn.execute(
                """SELECT * FROM completed_tasks WHERE status != 'Archived'"""
            )
            completed_rows = cursor.fetchall()

            for row in completed_rows:
                task = dict(row)
                # Parse version history JSON
                if task.get('version_history'):
                    try:
                        task['version_history'] = json.loads(task['version_history'])
                    except:
                        task['version_history'] = []

                # Calculate submission date if not present (3 working days after filming date)
                if not task.get('submission_date'):
                    task['submission_date'] = calculate_submission_date(task)

                completed_tasks.append(task)

        # Filter tasks by period
        filtered_live = filter_tasks_by_period(live_tasks, mode, period)
        filtered_completed = filter_tasks_by_period(completed_tasks, mode, period)

        return {
            "live_tasks": filtered_live,
            "completed_tasks": filtered_completed
        }

    except Exception as e:
        logger.error(f"Error getting dashboard raw data: {e}")
        return {
            "live_tasks": [],
            "completed_tasks": [],
            "error": str(e)
        }


def calculate_submission_date(task: Dict) -> str:
    """Calculate submission date: filming date + 3 working days"""
    try:
        # Try both column name formats
        filming_date_str = task.get('Filming Date') or task.get('filming_date', '')
        if not filming_date_str or filming_date_str == 'NA':
            return 'NA'

        # Parse filming date (DD-MM-YYYY)
        filming_date = datetime.strptime(filming_date_str, '%d-%m-%Y').date()

        # Add 3 working days
        submission_date = add_working_days(filming_date, 3)

        # Return in DD-MM-YYYY format
        return submission_date.strftime('%d-%m-%Y')
    except Exception as e:
        logger.warning(f"Could not calculate submission date: {e}")
        return 'NA'


def filter_tasks_by_period(tasks: List[Dict], mode: str, period: str) -> List[Dict]:
    """Filter tasks based on mode and period"""
    try:
        if mode == 'month':
            # Period format: YYYY-MM
            year, month = period.split('-')
            return [t for t in tasks if is_task_in_month(t, int(year), int(month))]

        elif mode == 'year':
            # Period format: YYYY
            year = int(period)
            return [t for t in tasks if is_task_in_year(t, year)]

        elif mode == 'range':
            # Period format: YYYY-MM-DD,YYYY-MM-DD
            start_str, end_str = period.split(',')
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
            return [t for t in tasks if is_task_in_range(t, start_date, end_date)]

        else:
            return tasks

    except Exception as e:
        logger.error(f"Error filtering tasks: {e}")
        return tasks


def is_task_in_month(task: Dict, year: int, month: int) -> bool:
    """Check if task filming date is in the given month"""
    try:
        # Try both column name formats (live_tasks use "Filming Date", completed_tasks use "filming_date")
        filming_date_str = task.get('Filming Date') or task.get('filming_date', '')
        if not filming_date_str or filming_date_str == 'NA':
            return False

        # Parse date (format: DD-MM-YYYY)
        date = datetime.strptime(filming_date_str, '%d-%m-%Y')
        return date.year == year and date.month == month
    except:
        return False


def is_task_in_year(task: Dict, year: int) -> bool:
    """Check if task filming date is in the given year"""
    try:
        # Try both column name formats (live_tasks use "Filming Date", completed_tasks use "filming_date")
        filming_date_str = task.get('Filming Date') or task.get('filming_date', '')
        if not filming_date_str or filming_date_str == 'NA':
            return False

        # Parse date (format: DD-MM-YYYY)
        date = datetime.strptime(filming_date_str, '%d-%m-%Y')
        return date.year == year
    except:
        return False


def is_task_in_range(task: Dict, start_date: datetime, end_date: datetime) -> bool:
    """Check if task filming date is in the given range"""
    try:
        # Try both column name formats (live_tasks use "Filming Date", completed_tasks use "filming_date")
        filming_date_str = task.get('Filming Date') or task.get('filming_date', '')
        if not filming_date_str or filming_date_str == 'NA':
            return False

        # Parse date (format: DD-MM-YYYY)
        date = datetime.strptime(filming_date_str, '%d-%m-%Y')
        return start_date <= date <= end_date
    except:
        return False
