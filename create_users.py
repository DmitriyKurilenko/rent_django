#!/usr/bin/env python
"""Backward-compatible wrapper for creating test users."""

import os

import django
from django.core.management import call_command

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "boat_rental.settings")
django.setup()


if __name__ == "__main__":
    call_command("create_test_users", "--show-passwords")
