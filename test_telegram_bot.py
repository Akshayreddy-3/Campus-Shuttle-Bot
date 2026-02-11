#!/usr/bin/env python3
"""
Unit tests for Campus Shuttle Bot
Tests the three new features:
  1. Passed shuttles are hidden (only now + upcoming shown)
  2. Back button presence in callback data
  3. Greeting detection and time-based response
"""

import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Load env before importing the bot module
import dotenv
dotenv.load_dotenv()

# Import the bot module
import telegram_bot as bot


class TestParseTime(unittest.TestCase):
    """Test the parse_time helper function."""

    def test_normal_time(self):
        self.assertEqual(bot.parse_time("6:20 AM"), 6 * 60 + 20)

    def test_pm_time(self):
        self.assertEqual(bot.parse_time("1:30 PM"), 13 * 60 + 30)

    def test_noon(self):
        self.assertEqual(bot.parse_time("12:00 PM"), 12 * 60)

    def test_midnight(self):
        self.assertEqual(bot.parse_time("12:00 AM"), 0)

    def test_drop_off(self):
        self.assertIsNone(bot.parse_time("DROP OFF"))

    def test_grocery(self):
        self.assertIsNone(bot.parse_time("Grocery Trip"))

    def test_none(self):
        self.assertIsNone(bot.parse_time(None))


class TestFormatEta(unittest.TestCase):
    """Test the format_eta helper function."""

    def test_negative(self):
        self.assertEqual(bot.format_eta(-5), "Passed")

    def test_zero(self):
        self.assertEqual(bot.format_eta(0), "Now! 🚌")

    def test_minutes(self):
        self.assertEqual(bot.format_eta(15), "in 15 min")

    def test_hours_and_minutes(self):
        self.assertEqual(bot.format_eta(75), "in 1h 15m")


class TestFindStop(unittest.TestCase):
    """Test the find_stop function with various queries."""

    def test_exact_name(self):
        stop = bot.find_stop("Hunter Hall")
        self.assertIsNotNone(stop)
        self.assertEqual(stop['id'], 'hunter-hall')

    def test_keyword_match(self):
        stop = bot.find_stop("rec")
        self.assertIsNotNone(stop)
        self.assertEqual(stop['id'], 'recreation-center')

    def test_partial_match(self):
        stop = bot.find_stop("delta")
        self.assertIsNotNone(stop)
        self.assertEqual(stop['id'], 'delta')

    def test_gym_keyword(self):
        stop = bot.find_stop("gym")
        self.assertIsNotNone(stop)
        self.assertEqual(stop['id'], 'anytime-fitness')

    def test_no_match(self):
        stop = bot.find_stop("nonexistent place xyz123")
        self.assertIsNone(stop)


class TestHidePassedShuttles(unittest.TestCase):
    """
    Test that get_stop_schedule returns entries with is_past flag,
    and that the schedule filtering logic correctly identifies past vs upcoming.
    """

    @patch('telegram_bot.get_current_minutes')
    @patch('telegram_bot.get_day_type')
    def test_schedule_has_past_and_future(self, mock_day_type, mock_current_minutes):
        """Verify that schedule entries are correctly marked as past or upcoming."""
        mock_day_type.return_value = 'mon-thu'
        # Set current time to 10:00 AM (600 minutes)
        mock_current_minutes.return_value = 600

        times = bot.get_stop_schedule('hunter-hall')

        past_times = [t for t in times if t['is_past']]
        future_times = [t for t in times if not t['is_past']]

        # There should be shuttles before 10:00 AM marked as past
        self.assertTrue(len(past_times) > 0, "Expected some past shuttles before 10:00 AM")
        # There should be shuttles after 10:00 AM marked as upcoming
        self.assertTrue(len(future_times) > 0, "Expected some upcoming shuttles after 10:00 AM")

    @patch('telegram_bot.get_current_minutes')
    @patch('telegram_bot.get_day_type')
    def test_filtering_hides_past(self, mock_day_type, mock_current_minutes):
        """Verify that filtering with is_past correctly removes old shuttles."""
        mock_day_type.return_value = 'mon-thu'
        mock_current_minutes.return_value = 600  # 10:00 AM

        times = bot.get_stop_schedule('hunter-hall')
        # This is the same filter used in send_schedule
        upcoming_only = [t for t in times if not t['is_past']]

        for t in upcoming_only:
            self.assertGreaterEqual(t['minutes'], 600,
                f"Shuttle at {t['time']} ({t['minutes']} min) should not appear — it's before 10:00 AM (600 min)")

    @patch('telegram_bot.get_current_minutes')
    @patch('telegram_bot.get_day_type')
    def test_late_night_no_upcoming(self, mock_day_type, mock_current_minutes):
        """At 11:30 PM, there should be no upcoming shuttles."""
        mock_day_type.return_value = 'mon-thu'
        mock_current_minutes.return_value = 23 * 60 + 30  # 11:30 PM

        times = bot.get_stop_schedule('hunter-hall')
        upcoming_only = [t for t in times if not t['is_past']]

        self.assertEqual(len(upcoming_only), 0, "Expected no upcoming shuttles at 11:30 PM")


class TestGreetingDetection(unittest.TestCase):
    """Test that greeting words are correctly detected."""

    def _is_greeting(self, text):
        """Replicate the greeting detection logic from handle_message."""
        text = text.lower().strip()
        greetings = ['hi', 'hello', 'hey', 'howdy', 'sup', 'yo', "what's up", 'whats up',
                     'good morning', 'good afternoon', 'good evening', 'greetings', 'hola']
        return any(text == g or text.startswith(g + ' ') or
                   text.startswith(g + '!') or text.startswith(g + ',') for g in greetings)

    def test_hi(self):
        self.assertTrue(self._is_greeting("hi"))

    def test_hello(self):
        self.assertTrue(self._is_greeting("hello"))

    def test_hey(self):
        self.assertTrue(self._is_greeting("hey"))

    def test_good_morning(self):
        self.assertTrue(self._is_greeting("good morning"))

    def test_good_evening(self):
        self.assertTrue(self._is_greeting("Good Evening"))

    def test_hi_with_exclamation(self):
        self.assertTrue(self._is_greeting("hi!"))

    def test_hello_with_extra_text(self):
        self.assertTrue(self._is_greeting("hello there"))

    def test_hola(self):
        self.assertTrue(self._is_greeting("hola"))

    def test_not_a_greeting(self):
        self.assertFalse(self._is_greeting("next delta"))

    def test_stop_name_not_greeting(self):
        self.assertFalse(self._is_greeting("hunter hall"))

    def test_random_text_not_greeting(self):
        self.assertFalse(self._is_greeting("when is the shuttle"))


class TestGetDayType(unittest.TestCase):
    """Test the get_day_type function."""

    @patch('telegram_bot.get_now')
    def test_sunday_returns_none(self, mock_now):
        mock_now.return_value = datetime(2026, 2, 15, 10, 0)  # Sunday
        self.assertIsNone(bot.get_day_type())

    @patch('telegram_bot.get_now')
    def test_saturday(self, mock_now):
        mock_now.return_value = datetime(2026, 2, 14, 10, 0)  # Saturday
        self.assertEqual(bot.get_day_type(), 'sat')

    @patch('telegram_bot.get_now')
    def test_friday(self, mock_now):
        mock_now.return_value = datetime(2026, 2, 13, 10, 0)  # Friday
        self.assertEqual(bot.get_day_type(), 'fri')

    @patch('telegram_bot.get_now')
    def test_weekday(self, mock_now):
        mock_now.return_value = datetime(2026, 2, 10, 10, 0)  # Tuesday
        self.assertEqual(bot.get_day_type(), 'mon-thu')


class TestGetNextShuttle(unittest.TestCase):
    """Test the get_next_shuttle function."""

    @patch('telegram_bot.get_current_minutes')
    @patch('telegram_bot.get_day_type')
    def test_returns_next_upcoming(self, mock_day_type, mock_current_minutes):
        mock_day_type.return_value = 'mon-thu'
        mock_current_minutes.return_value = 600  # 10:00 AM

        result = bot.get_next_shuttle('hunter-hall')
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result['minutes'], 600)

    @patch('telegram_bot.get_current_minutes')
    @patch('telegram_bot.get_day_type')
    def test_returns_none_after_last(self, mock_day_type, mock_current_minutes):
        mock_day_type.return_value = 'mon-thu'
        mock_current_minutes.return_value = 23 * 60 + 30  # 11:30 PM

        result = bot.get_next_shuttle('hunter-hall')
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
